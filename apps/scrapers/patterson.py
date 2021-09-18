import asyncio
from typing import List

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product
from apps.types.orders import CartProduct
from apps.types.scraper import LoginInformation, ProductSearch

LOGIN_HEADERS = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "Origin": "https://pcsts.pattersoncompanies.com",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Accept-Language": "en-US,en;q=0.9",
}

LOGIN_HOOK_HEADER = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "Origin": "https://pcsts.pattersoncompanies.com",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://pcsts.pattersoncompanies.com/",
    "Accept-Language": "en-US,en;q=0.9",
}

LOGIN_HOOK_HEADER2 = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}

SEARCH_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
    "sec-ch-ua-mobile": "?0",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://www.pattersondental.com/",
    "Accept-Language": "en-US,en;q=0.9",
}


class PattersonScraper(Scraper):
    BASE_URL = "https://www.pattersondental.com"

    async def _get_login_data(self) -> LoginInformation:
        headers = {
            "Connection": "keep-alive",
            "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Accept-Language": "en-US,en;q=0.9",
        }
        params = {
            "returnUrl": "/",
            "signIn": "userSignIn",
        }
        async with self.session.get(f"{self.BASE_URL}/Account", headers=headers, params=params) as resp:
            url = str(resp.url)

            headers = LOGIN_HEADERS.copy()
            headers["Referer"] = url
            return {
                "url": url,
                "headers": headers,
                "data": {
                    "userName": self.username,
                    "password": self.password,
                    "AuthMethod": "FormsAuthentication",
                },
            }

    async def _check_authenticated(self, resp: ClientResponse) -> bool:
        dom = Selector(text=await resp.text())
        return False if dom.xpath(".//div[@id='error']") else True

    async def _after_login_hook(self, response: ClientResponse):
        response_dom = Selector(text=await response.text())
        data = {
            "wa": response_dom.xpath("//input[@name='wa']/@value").get(),
            "wresult": response_dom.xpath("//input[@name='wresult']/@value").get(),
            "wctx": response_dom.xpath("//input[@name='wctx']/@value").get(),
        }
        await self.session.post(self.BASE_URL, headers=LOGIN_HOOK_HEADER, data=data)
        async with self.session.get(self.BASE_URL, headers=LOGIN_HOOK_HEADER2) as resp:
            text = await resp.text()
            return text

    async def get_orders(self, perform_login=False) -> List[Order]:
        pass

    async def get_product(self, product_dom):
        product_description_dom = product_dom.xpath(".//div[contains(@class, 'listViewDescriptionWrapper')]")
        product_link = product_description_dom.xpath(".//a[@class='itemTitleDescription']")
        product_id = product_link.attrib["data-objectid"]
        async with self.session.get(
            f"{self.BASE_URL}/Supplies/ProductFamilyPricing?productFamilyKey={product_id}&getLastDateOrdered=false"
        ) as resp:
            res = await resp.json()
            price_high = res["PriceHigh"]
            # price_low = res["PriceLow"]

        return {
            "product_id": product_id,
            "name": self.extract_first(
                product_description_dom,
                ".//a[@class='itemTitleDescription']//text()",
            ),
            "description": "",
            "url": self.BASE_URL
            + self.extract_first(
                product_description_dom,
                ".//a[@class='itemTitleDescription']/@href",
            ),
            "image": self.extract_first(product_dom, ".//div[contains(@class, 'listViewImageWrapper')]/img/@src"),
            "price": price_high,
            "retail_price": "",
            "vendor_id": self.vendor_id,
        }

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        await self.login()
        page_size = 24
        url = f"{self.BASE_URL}/Search/SearchResults"
        params = {
            "F.MYCATALOG": "false",
            "q": query,
            "p": page,
        }
        async with self.session.get(url, headers=SEARCH_HEADERS, params=params) as resp:
            response_dom = Selector(text=await resp.text())
            total_size = (
                response_dom.xpath(
                    "//div[contains(@class, 'productItemFamilyListHeader')]\
                  //h1//text()"
                )
                .get()
                .split("results", 1)[0]
                .split("Found")[1]
                .strip()
            )
            products_dom = response_dom.xpath(
                "//div[@class='container-fluid']//table//tr//div[@ng-controller='SearchResultsController']"
            )
            tasks = (self.get_product(product_dom) for product_dom in products_dom)
            products = await asyncio.gather(*tasks, return_exceptions=True)
            return {
                "total_size": total_size,
                "page": page,
                "page_size": page_size,
                "products": [Product.from_dict(product) for product in products if isinstance(product, dict)],
                "last_page": page_size * page >= total_size,
            }

    async def checkout(self, products: List[CartProduct]):
        pass