import asyncio
import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product
from apps.scrapers.utils import catch_network
from apps.types.orders import CartProduct
from apps.types.scraper import LoginInformation, ProductSearch

PRE_LOGIN_HEADERS = {
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

ORDER_HISTORY_HEADERS = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="96", "Google Chrome";v="96"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

ORDER_HISTORY_POST_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="96", "Google Chrome";v="96"',
    "sec-ch-ua-mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36",
    "Accept": "*/*",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "sec-ch-ua-platform": '"Windows"',
    "Origin": "https://www.pattersondental.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://www.pattersondental.com/OrderHistory/Search",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}


class PattersonScraper(Scraper):
    BASE_URL = "https://www.pattersondental.com"

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        params = {
            "returnUrl": "/",
            "signIn": "userSignIn",
        }
        async with self.session.get(f"{self.BASE_URL}/Account", headers=PRE_LOGIN_HEADERS, params=params) as resp:
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

    async def get_order(self, order_dom, office=None):
        order = {
            "order_id": self.merge_strip_values(order_dom, "./td[3]//text()"),
            "total_amount": self.remove_thousands_separator(self.merge_strip_values(order_dom, "./td[5]//text()")),
            "currency": "USD",
            "order_date": datetime.datetime.strptime(
                self.extract_first(order_dom, "./td[1]//text()"), "%m/%d/%Y"
            ).date(),
            "status": self.extract_first(order_dom, "./td[2]//text()"),
            "products": [],
        }
        order_link = self.extract_first(order_dom, "./td[3]/a/@href")

        async with self.session.get(f"{self.BASE_URL}{order_link}") as resp:
            order_detail_response = Selector(text=await resp.text())
            # addresses = order_detail_response.xpath(
            #     "//span[@id='ctl00_cphMainContent_ucShippingAddr_lblAddress']//text()"
            # ).extract()
            # _, codes = addresses[-2].split(",")
            # region_code, postal_code = codes.strip().split(" ")
            # order["shipping_address"] = {
            #     "address": addresses[1],
            #     "region_code": region_code,
            #     "postal_code": postal_code,
            # }

            for order_product_dom in order_detail_response.xpath('//div[contains(@class, "itemRecord")]'):
                product_id = self.merge_strip_values(
                    order_product_dom, ".//div[contains(@class, 'orderHistoryOrderDetailItemText')]//text()"
                )
                # product_name = self.extract_first(product_name_url_dom, ".//a/text()")
                product_url = self.extract_first(
                    order_product_dom, ".//div[contains(@class, 'orderHistoryOrderDetailItemText')]//@href"
                )
                product_url = f"{self.BASE_URL}{product_url}"
                product_price = self.remove_thousands_separator(
                    self.extract_first(
                        order_product_dom, ".//div[contains(@class, 'orderHistoryOrderDetailPriceText')]//text()"
                    )
                )
                quantity = self.extract_first(
                    order_product_dom, ".//div[contains(@class, 'orderHistoryOrderDetailQuantityText')]/input/@value"
                )

                if "invoice_link" not in order:
                    invoice_number = self.extract_first(
                        order_product_dom,
                        ".//div[contains(@class, 'orderHistoryOrderDetailInvoiceOrRejectReasonText')]//text()",
                    )

                    order["invoice_link"] = f"{invoice_number}"

                order["products"].append(
                    {
                        "product": {
                            "product_id": product_id,
                            "name": "",
                            "description": "",
                            "url": product_url,
                            "images": [],
                            "category": "",
                            "price": product_price,
                            "vendor": self.vendor.to_dict(),
                        },
                        "quantity": quantity,
                        "unit_price": product_price,
                        "status": "",
                    }
                )

        await self.get_missing_products_fields(
            order["products"],
            fields=(
                "name",
                "description",
                "images",
                "category",
            ),
        )
        if office:
            await self.save_order_to_db(office, order=Order.from_dict(order))
        return order

    async def get_orders(
        self,
        office=None,
        perform_login=False,
        from_date: Optional[datetime.date] = None,
        to_date: Optional[datetime.date] = None,
    ) -> List[Order]:
        if perform_login:
            await self.login()

        url = "https://www.pattersondental.com/OrderHistory/Search"
        async with self.session.get(url, headers=ORDER_HISTORY_HEADERS) as resp:
            response_dom = Selector(text=await resp.text())
            verification_token = response_dom.xpath(
                '//form[@id="orderHistorySearchForm"]/input[@name="__RequestVerificationToken"]/@value'
            ).get()

        search_params = {
            "usePartial": "true",
        }
        search_data = {
            "__RequestVerificationToken": verification_token,
            "FromDate": "",
            "ToDate": "",
            "ItemNumber": "",
            "ItemDescription": "",
            "ManufacturerName": "",
            "PurchaseOrderNumber": "",
            "OrderNumber": "",
            "ManufacturerOrNdcNumber": "",
            "ViewSortByValue": "",
            "ViewSortDirection": "",
        }
        if from_date and to_date:
            search_data["FromDate"] = from_date.strftime("%m/%d/%Y")
            search_data["ToDate"] = to_date.strftime("%m/%d/%Y")

        async with self.session.post(
            url, headers=ORDER_HISTORY_POST_HEADERS, params=search_params, data=search_data
        ) as resp:
            response_dom = Selector(text=await resp.text())
            orders_dom = response_dom.xpath('.//table[@id="orderHistory"]/tbody/tr')
            tasks = (self.get_order(order_dom) for order_dom in orders_dom)
            orders = await asyncio.gather(*tasks, return_exceptions=True)

        return [Order.from_dict(order) for order in orders if isinstance(order, dict)]

    async def get_product_as_dict(self, product_id, product_url, perform_login=False) -> dict:
        # if perform_login:
        #     await self.login()

        async with self.session.get(product_url) as resp:
            res = Selector(text=await resp.text())
            product_images = res.xpath(".//div[@id='productFamilyCarouselItem']//img/@src").extract()
            ret = {
                "product_id": product_id,
                "name": "",
                "url": product_url,
                "images": [{"image": product_image} for product_image in product_images],
                "category": "",
                "price": "",
                "vendor": self.vendor.to_dict(),
            }

        product_description_detail = res.xpath(
            "//div[@id='ItemDetailsProductDetailsRow']//asyncdiv/@src"
        ).extract_first()
        if product_description_detail:
            async with self.session.get(f"{self.BASE_URL}{product_description_detail}") as resp:
                res = Selector(text=await resp.text())
                product_description = self.merge_strip_values(res, "//div[@class='itemDetailBody']//text()")
        else:
            product_description = self.merge_strip_values(res, ".//div[@class='viewMoreDescriptionContainer']/text()")
        ret["description"] = product_description
        return ret

    async def get_product_prices(self, product_ids, perform_login=False, **kwargs) -> Dict[str, Decimal]:
        # TODO: perform_login, this can be handle in decorator in the future
        if perform_login:
            await self.login()

        tasks = (self.get_product_price(product_id) for product_id in product_ids)
        product_prices = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            product_id: product_price
            for product_id, product_price in zip(product_ids, product_prices)
            if isinstance(product_price, Decimal)
        }

    async def get_product_price(self, product_id) -> Decimal:
        async with self.session.get(
            f"{self.BASE_URL}/Supplies/ProductFamilyPricing?productFamilyKey={product_id}&getLastDateOrdered=false"
        ) as resp:
            res = await resp.json()
            return Decimal(str(res["PriceHigh"]))

    @catch_network
    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        page_size = 24
        url = f"{self.BASE_URL}/Search/SearchResults"
        params = {
            "F.MYCATALOG": "false",
            "q": query,
            "p": page,
        }
        products = []
        async with self.session.get(url, headers=SEARCH_HEADERS, params=params) as resp:
            response_dom = Selector(text=await resp.text())
            try:
                total_size = int(
                    response_dom.xpath(
                        "//div[contains(@class, 'productItemFamilyListHeader')]\
                      //h1//text()"
                    )
                    .get()
                    .split("results", 1)[0]
                    .split("Found")[1]
                    .strip(" +")
                )
            except (IndexError, AttributeError, ValueError):
                total_size = 0
            products_dom = response_dom.xpath(
                "//div[@class='container-fluid']//table//tr//div[@ng-controller='SearchResultsController']"
            )
        for product_dom in products_dom:
            product_description_dom = product_dom.xpath(".//div[contains(@class, 'listViewDescriptionWrapper')]")
            product_link = product_description_dom.xpath(".//a[@class='itemTitleDescription']")
            product_id = product_link.attrib["data-objectid"]
            product_name = self.extract_first(
                product_description_dom,
                ".//a[@class='itemTitleDescription']//text()",
            )
            product_url = self.BASE_URL + self.extract_first(
                product_description_dom,
                ".//a[@class='itemTitleDescription']/@href",
            )
            product_image = (
                self.extract_first(product_dom, ".//div[contains(@class, 'listViewImageWrapper')]/img/@src"),
            )

            products.append(
                {
                    "product_id": product_id,
                    "name": product_name,
                    "description": "",
                    "url": product_url,
                    "images": [{"image": product_image}],
                    "price": Decimal(0),
                    "vendor": self.vendor.to_dict(),
                    "category": "",
                }
            )

        product_prices = await self.get_product_prices([product["product_id"] for product in products])

        for product in products:
            product["price"] = product_prices[product["product_id"]]

        return {
            "vendor_slug": self.vendor.slug,
            "total_size": total_size,
            "page": page,
            "page_size": page_size,
            "products": [Product.from_dict(product) for product in products if isinstance(product, dict)],
            "last_page": page_size * page >= total_size,
        }

    async def checkout(self, products: List[CartProduct]):
        pass
