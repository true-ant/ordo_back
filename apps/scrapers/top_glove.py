import logging
from decimal import Decimal
from typing import Dict, List

from aiohttp import ClientResponse
from scrapy import Selector

from apps.common import messages as msgs
from apps.scrapers.base import Scraper
from apps.scrapers.headers.top_glove import HTTP_HEADER, LOGIN_HEADER
from apps.scrapers.schema import VendorOrderDetail
from apps.types.orders import CartProduct

logger = logging.getLogger(__name__)


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
