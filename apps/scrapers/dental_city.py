from typing import Dict, List

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import VendorOrderDetail
from apps.types.orders import CartProduct
from apps.types.scraper import LoginInformation, ProductSearch

LOGIN_PAGE_HEADERS = {
    "authority": "www.dentalcity.com",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "referer": "https://www.dentalcity.com/",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

LOGIN_HEADERS = {
    "authority": "www.dentalcity.com",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "accept": "*/*",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua-mobile": "?0",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
    "sec-ch-ua-platform": '"Windows"',
    "origin": "https://www.dentalcity.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.dentalcity.com/account/login",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}


class DentalCityScraper(Scraper):
    BASE_URL = "https://www.dentalcity.com"
    CATEGORY_URL = "https://www.henryschein.com/us-en/dental/c/browsesupplies"
    TRACKING_BASE_URL = "https://narvar.com/tracking/itemvisibility/v1/henryschein-dental/orders"

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        text = await response.text()
        dom = Selector(text=text)
        login_success = dom.xpath("//input[@id='Message']/@value").get()
        return login_success == "success"

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        await self.session.get("https://www.dentalcity.com/account/login", headers=LOGIN_PAGE_HEADERS)
        return {
            "url": "https://www.dentalcity.com/account/login/",
            "headers": LOGIN_HEADERS,
            "data": {
                "UserName": self.username,
                "Password": self.password,
                "ReturnUrl": "",
                "Message": "",
                "Name": "",
                "DashboardURL": "https://www.dentalcity.com/profile/dashboard",
            },
        }

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0, sort_by="price", office_id=None
    ) -> ProductSearch:
        return await self._search_products_from_table(query, page, min_price, max_price, sort_by, office_id)

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        vendor_order_detail = {
            "retail_amount": "",
            "savings_amount": "",
            "subtotal_amount": "",
            "shipping_amount": "",
            "tax_amount": "",
            "total_amount": "",
            "payment_method": "",
            "shipping_address": "",
        }
        vendor_slug: str = self.vendor.slug
        return {
            vendor_slug: {
                **vendor_order_detail,
                **self.vendor.to_dict(),
            },
        }
