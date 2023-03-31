import asyncio
import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from aiohttp import ClientResponse
from scrapy import Selector

from apps.common import messages as msgs
from apps.scrapers.base import Scraper
from apps.scrapers.headers.safco import (
    HOME_HEADER,
    LOGIN_HEADER,
    LOGIN_HOOK_HEADER,
    ORDER_HISTORY_HEADER,
)
from apps.scrapers.schema import Order, VendorOrderDetail
from apps.scrapers.utils import semaphore_coroutine
from apps.types.orders import CartProduct
from apps.types.scraper import InvoiceFormat, InvoiceType, LoginInformation
from apps.vendor_clients import errors

logger = logging.getLogger(__name__)


def clean_text(xpath, dom):
    try:
        text = re.sub(r"\s+", " ", " ".join(dom.xpath(xpath).extract())).strip()
        return text
    except Exception:
        return None


class SafcoScraper(Scraper):
    BASE_URL = "https://www.safcodental.com/"
    INVOICE_TYPE = InvoiceType.PDF_INVOICE
    INVOICE_FORMAT = InvoiceFormat.USE_VENDOR_FORMAT

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

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        async with self.session.get(url=f"{self.BASE_URL}/?ref=sir", headers=HOME_HEADER):
            return {
                "url": f"{self.BASE_URL}/ajax/fn_signInJs.html",
                "headers": LOGIN_HEADER,
                "data": {
                    "si_an": self.username,
                    "si_ph": self.password,
                    "lform_title": "Welcome!",
                    "showCreateAccount": "",
                    "signInId": "rSi",
                    "showSiFormHeading": "Y",
                    "showNewDesign": "Y",
                    "redirect": "/",
                    "requestType": "json",
                    "sourcePage": "https://www.safcodental.com/",
                },
            }

    async def check_authenticated(self, resp: ClientResponse) -> bool:
        text = await resp.text()
        dom = Selector(text=text)

        return True if dom.xpath("//a[@href='/shopping-cart']") else False

    async def login(self, username: Optional[str] = None, password: Optional[str] = None):
        login_info = await self._get_login_data()
        logger.debug("Got logger data: %s", login_info)
        if login_info:
            async with self.session.post(
                url=login_info["url"], headers=login_info["headers"], data=login_info["data"]
            ) as resp:
                data = {
                    "contactFields": {
                        "email": login_info["data"]["si_an"],
                    },
                    "formSelectorClasses": ".login-form",
                    "formSelectorId": "",
                    "formValues": {},
                    "labelToNameMap": {},
                    "pageTitle": "Dental Supplies and Products | Safco Dental Supply",
                    "pageUrl": "https://www.safcodental.com/?ref=sir&ref=sor",
                    "portalId": 21944014,
                    "type": "SCRAPED",
                    "version": "collected-forms-embed-js-static-1.315",
                    "collectedFormClasses": "login-form",
                    "collectedFormAction": "ajax/fn_signInJs.html",
                }
                async with self.session.post(
                    url="https://forms.hubspot.com/collected-forms/submit/form", headers=LOGIN_HOOK_HEADER, json=data
                ) as resp:
                    async with self.session.get(url=f"{self.BASE_URL}", headers=HOME_HEADER) as resp:
                        is_authenticated = await self.check_authenticated(resp)
                        if not is_authenticated:
                            logger.debug("Still not authenticated")
                            raise errors.VendorAuthenticationFailed()

                        if hasattr(self, "after_login_hook"):
                            await self.after_login_hook(resp)

                        logger.info("Successfully logged in")

                    return resp.cookies

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

        url = f"{self.BASE_URL}/my-account/my-orders.html?ref=h"
        async with self.session.get(url, headers=ORDER_HISTORY_HEADER) as resp:
            response_dom = Selector(text=await resp.text())
            orders_doms = response_dom.xpath('//div[@class="order-info orderInfoTable"]')
            tasks = (self.get_order(sem, order_dom, office) for order_dom in orders_doms)
            orders = await asyncio.gather(*tasks, return_exceptions=True)

        return [Order.from_dict(order) for order in orders if isinstance(order, dict)]

    @semaphore_coroutine
    async def get_order(self, sem, order_dom, office=None, **kwargs):
        order_item = {
            "currency": "USD",
            "products": [],
        }
        order_header_ele = order_dom.xpath('.//div[@class="orderHeaderInfo"]')
        order_value_ele = order_dom.xpath('.//div[@class="right-side-shipments"]')
        order_id = self.extract_first(
            order_header_ele,
            './/li/span[@class="attribute-txt"][contains(text(), "Order number")]/following-sibling::'
            'span[@class="attribute-value"]//text()',
        )
        order_item["order_id"] = order_id

        order_date = self.extract_first(order_header_ele, './/div[contains(@class, "order-date")]//text()')
        order_date = datetime.strptime(order_date, "%B %d, %Y")
        order_item["order_date"] = datetime.strftime(order_date, "%Y-%m-%d")

        order_total = self.extract_first(
            order_header_ele,
            './/li/span[@class="attribute-txt"][contains(text(), "Order total")]/following-sibling::'
            'span[@class="attribute-value"]//text()',
        )
        order_item["total_amount"] = order_total

        payment_method = self.extract_first(
            order_header_ele,
            './/li/span[@class="attribute-txt"][contains(text(), "Payment method")]/following-sibling::'
            'span[@class="attribute-value"]//text()',
        )
        order_item["payment_method"] = payment_method

        order_status = self.extract_first(
            order_value_ele, './/div[@class="shipmentInfo"]//div[contains(@class, "delivered")]//text()'
        )
        order_item["status"] = order_status

        invoice_link = order_value_ele.xpath('.//a[contains(text(), "View invoice")]/@href').get()
        if invoice_link:
            invoice_link = f"https://www.safcodental.com/{invoice_link}"
        order_item["invoice_link"] = invoice_link

        track_link = order_value_ele.xpath('.//a[contains(text(), "Track this shipment")]/@href').get()
        if track_link:
            track_link = f"https://www.safcodental.com/{track_link}"
        order_item["track_link"] = track_link

        prim = order_value_ele.xpath('.//div[@class="shipmentItems"][@id]/@id').get()
        prim = prim.split("-")[-1].strip() if prim else ""
        if prim:
            async with self.session.get(
                f"https://www.safcodental.com/ajax/fn_getShipmentItems.html?ordn={order_id}&prim={prim}",
                headers=ORDER_HISTORY_HEADER,
            ) as resp:
                order_detail_dom = Selector(text=await resp.text())
                for order_product in order_detail_dom.xpath('//div[contains(@class, "shipmentItemTable")]/div'):
                    order_product_item = {
                        "product": {
                            "product_id": "",
                            "sku": "",
                            "name": "",
                            "description": "",
                            "url": "",
                            "images": [],
                            "category": "",
                            "price": "",
                            "vendor": {},
                        },
                        "quantity": 0,
                        "unit_price": 0,
                        "status": "",
                    }

                    product_sku = clean_text('.//div[@class="itemNumber"]/a//text()', order_product)
                    if not product_sku:
                        continue
                    order_product_item["product"]["sku"] = product_sku
                    order_product_item["product"]["product_id"] = product_sku

                    product_title = clean_text('.//div[@class="description"]//text()', order_product)
                    order_product_item["product"]["name"] = product_title

                    product_qty = clean_text('.//div[@class="qty"]//text()', order_product)
                    order_product_item["qty"] = int(product_qty)

                    order_item["products"].append(order_product_item)
        if office:
            await self.save_order_to_db(office, order=Order.from_dict(order_item))
        return order_item
