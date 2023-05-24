import asyncio
import datetime
import logging
import re
from decimal import Decimal
from typing import Dict, List, Optional

from aiohttp import ClientResponse
from scrapy import Selector

from apps.common import messages as msgs
from apps.scrapers.base import Scraper
from apps.scrapers.headers.top_glove import (
    HTTP_HEADER,
    LOGIN_HEADER,
    ORDER_DETAIL_HEADER,
    ORDER_HISTORY_HEADER,
)
from apps.scrapers.schema import Order, VendorOrderDetail
from apps.scrapers.utils import catch_network, semaphore_coroutine
from apps.types.orders import CartProduct

logger = logging.getLogger(__name__)


def textParser(dom):
    try:
        text = re.sub(r"\s+", " ", " ".join(dom.xpath(".//text()").extract())).strip()
        return text
    except Exception:
        return None


class TopGloveScraper(Scraper):
    BASE_URL = "https://www.topqualitygloves.com"

    async def _get_login_data(self, *args, **kwargs):
        async with self.session.get(f"{self.BASE_URL}/index.php?main_page=login", headers=HTTP_HEADER) as resp:
            text = Selector(text=await resp.text())
            security_token = text.xpath("//form[@name='login']//input[@name='securityToken']/@value").get()
            data = [
                ("email_address", self.username),
                ("password", self.password),
                ("securityToken", security_token),
                ("x", "27"),
                ("y", "3"),
            ]
            return {
                "url": f"{self.BASE_URL}/index.php?main_page=login&action=process",
                "headers": LOGIN_HEADER,
                "data": data,
            }

    async def _check_authenticated(self, resp: ClientResponse):
        text = await resp.text()
        dom = Selector(text=text)
        return "logged in" in dom.xpath("//li[@class='headerNavLoginButton']//text()").get()

    @semaphore_coroutine
    async def get_order(
        self,
        sem,
        order_dom,
        office=None,
        from_date: Optional[datetime.date] = None,
        to_date: Optional[datetime.date] = None,
        completed_order_ids: Optional[List[str]] = None,
    ) -> dict:
        order_item = {"products": [], "currency": "USD"}

        order_id = textParser(order_dom.xpath("./legend"))
        order_item["order_id"] = order_id.split(":")[1].strip()

        order_status = textParser(order_dom.xpath('./div[contains(@class, "notice")]'))
        order_item["status"] = order_status.split(":")[1].strip()

        order_detail_link = order_dom.xpath('.//a[contains(@href, "account_history_info")]/@href').get()
        order_item["order_detail_link"] = order_detail_link

        async with self.session.get(order_detail_link, headers=ORDER_DETAIL_HEADER) as resp:
            resp_dom = Selector(text=await resp.text())
            order_date = textParser(
                resp_dom.xpath('//div[@id="accountHistInfo"]/div[@class="forward"][contains(text(), "Order Date")]')
            )
            if order_date and ":" in order_date:
                order_item["order_date"] = datetime.datetime.strptime(
                    order_date.split(":")[1].strip(), "%A %d %B, %Y"
                ).date()

            import pdb

            pdb.set_trace()
            if completed_order_ids and str(order_item["order_id"]) in completed_order_ids:
                return
            if from_date and to_date and (order_item["order_date"] < from_date or order_item["order_date"] > to_date):
                return

            total = textParser(resp_dom.xpath('//div[@id="orderTotals"]/div[contains(@class, "amount")][last()]'))
            order_item["total_amount"] = total

            product_rows = resp_dom.xpath('//table[@id="orderHistoryHeading"]//tr')

            for product_line in product_rows:
                product_name = textParser(product_line.xpath('./td[@class="accountProductDisplay"]'))

                skus = product_line.xpath('./td[@class="accountProductCodeDisplay"]//text()').extract()
                if not skus:
                    continue
                descriptions = product_line.xpath('./td[@class="accountProductDescDisplay"]//text()').extract()
                qtys = product_line.xpath('./td[@class="accountQuantityDisplay"]//text()').extract()
                unit_prices = product_line.xpath('./td[@class="cartUnitDisplay"]//text()').extract()
                prices = product_line.xpath('./td[@class="cartTotalDisplay"]//text()').extract()

                for index, sku in enumerate(skus):
                    if len(descriptions) > index:
                        description = descriptions[index].strip()
                    else:
                        description = descriptions[0].strip()

                    if len(qtys) > index:
                        qty = qtys[index].strip()
                    else:
                        qty = qtys[0].strip()

                    if len(unit_prices) > index:
                        unit_price = unit_prices[index].strip()
                    else:
                        unit_price = unit_prices[0].strip()

                    if len(prices) > index:
                        product_price = prices[index].strip()
                    else:
                        product_price = prices[0].strip()

                    order_item["products"].append(
                        {
                            "product": {
                                "product_id": sku,
                                "sky": sku,
                                "name": product_name,
                                "description": description,
                                "url": "",
                                "images": [],
                                "category": "",
                                "price": product_price,
                                "status": "",
                                "vendor": self.vendor.to_dict(),
                            },
                            "quantity": qty,
                            "unit_price": unit_price,
                            "status": "",
                        }
                    )

            if office:
                await self.save_order_to_db(office, order=Order.from_dict(order_item))
            return order_item

    @catch_network
    async def get_orders(
        self,
        office=None,
        perform_login=False,
        from_date: Optional[datetime.date] = None,
        to_date: Optional[datetime.date] = None,
        completed_order_ids: Optional[List[str]] = None,
    ) -> List[Order]:
        sem = asyncio.Semaphore(value=2)
        if perform_login:
            await self.login()

        tasks = []
        page = 1
        while True:
            async with self.session.get(
                f"{self.BASE_URL}/index.php?main_page=account_history&page={page}", headers=ORDER_HISTORY_HEADER
            ) as resp:
                order_history_resp_dom = Selector(text=await resp.text())

                order_history_doms = order_history_resp_dom.xpath('//div[@id="accountHistoryDefault"]/fieldset')
                for order_dom in order_history_doms:
                    order_detail_link = order_dom.xpath('.//a[contains(@href, "account_history_info")]/@href').get()
                    if not order_detail_link:
                        continue

                    tasks.append(
                        self.get_order(
                            sem,
                            order_dom,
                            office,
                            from_date=from_date,
                            to_date=to_date,
                            completed_order_ids=completed_order_ids,
                        )
                    )

                if len(order_history_doms) < 10:
                    break
                else:
                    page += 1

        if tasks:
            orders = await asyncio.gather(*tasks)
            return [Order.from_dict(order) for order in orders if isinstance(order, dict)]
        else:
            return []

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        subtotal_manual = sum([prod["price"] * prod["quantity"] for prod in products])
        vendor_order_detail = VendorOrderDetail(
            retail_amount=(0),
            savings_amount=(0),
            subtotal_amount=Decimal(subtotal_manual),
            shipping_amount=(0),
            tax_amount=(0),
            total_amount=Decimal(subtotal_manual),
            payment_method="",
            shipping_address="",
            reduction_amount=Decimal(subtotal_manual),
        )
        vendor_slug: str = self.vendor.slug
        return {
            vendor_slug: {
                **vendor_order_detail.to_dict(),
                **self.vendor.to_dict(),
            },
        }

    async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False, redundancy=False):
        subtotal_manual = sum([prod["price"] * prod["quantity"] for prod in products])
        vendor_order_detail = VendorOrderDetail(
            retail_amount=(0),
            savings_amount=(0),
            subtotal_amount=Decimal(subtotal_manual),
            shipping_amount=(0),
            tax_amount=(0),
            total_amount=Decimal(subtotal_manual),
            reduction_amount=Decimal(subtotal_manual),
            payment_method="",
            shipping_address="",
        )
        return {
            **vendor_order_detail.to_dict(),
            **self.vendor.to_dict(),
            "order_id": "invalid",
            "order_type": msgs.ORDER_TYPE_REDUNDANCY,
        }
