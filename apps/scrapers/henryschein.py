import asyncio
import datetime
import json
import re
import uuid
from decimal import Decimal
from typing import Dict, List, Optional, Union

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product, ProductCategory, VendorOrderDetail
from apps.scrapers.utils import catch_network
from apps.types.orders import CartProduct, VendorCartProduct
from apps.types.scraper import LoginInformation, ProductSearch

HEADERS = {
    "authority": "www.henryschein.com",
    "sec-ch-ua": '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
    "n": "pikP/UtnnyEIsCZl3cphEgyUhacC9CnLZqSaDcvfufM=",
    "iscallingfromcms": "False",
    "sec-ch-ua-mobile": "?0",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",
    # noqa
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "origin": "https://www.henryschein.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.henryschein.com/us-en/Profiles/Logout.aspx?redirdone=1",
    "accept-language": "en-US,en;q=0.9",
}
SEARCH_HEADERS = {
    "authority": "www.henryschein.com",
    "cache-control": "max-age=0",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/92.0.4515.159 Safari/537.36",
    "accept": "text/html,application/xhtml+xml, application/xml;q=0.9, "
    "image/avif,image/webp,image/apng, */*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-ch-ua": '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
    "sec-ch-ua-mobile": "?0",
    "sec-fetch-site": "none",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "accept-language": "en-US,en;q=0.9",
}
REMOVE_PRODUCT_FROM_CART_HEADERS = {
    "authority": "www.henryschein.com",
    "sec-ch-ua": '"Chromium";v="94", "Google Chrome";v="94", ";Not A Brand";v="99"',
    "n": "faMC175siE4Ji7eGjyxEnEahdp30gAd6F12KILNn68E=",
    "sec-ch-ua-mobile": "?0",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.71 Safari/537.36",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua-platform": '"Windows"',
    "origin": "https://www.henryschein.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8",
}
CHECKOUT_HEADER = {
    "authority": "www.henryschein.com",
    "cache-control": "max-age=0",
    "sec-ch-ua": '"Chromium";v="94", "Google Chrome";v="94", ";Not A Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1",
    "origin": "https://www.henryschein.com",
    "content-type": "application/x-www-form-urlencoded",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.71 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8",
}


class HenryScheinScraper(Scraper):
    BASE_URL = "https://www.henryschein.com"
    CATEGORY_URL = "https://www.henryschein.com/us-en/dental/c/browsesupplies"

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        res = await response.json()
        return res.get("IsAuthenticated", False)

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        async with self.session.get("https://www.henryschein.com/us-en/dental/Default.aspx") as resp:
            text = await resp.text()
            n = text.split("var _n =")[1].split(";")[0].strip(" '")
        self.session.headers.update({"n": n})
        return {
            "url": f"{self.BASE_URL}/webservices/LoginRequestHandler.ashx",
            "headers": HEADERS,
            "data": {
                "username": self.username,
                "password": self.password,
                "did": "dental",
                "searchType": "authenticateuser",
                "culture": "us-en",
            },
        }

    async def get_order(self, order_dom):
        link = order_dom.xpath("./td[8]/a/@href").extract_first().strip()
        order = {
            "total_amount": order_dom.xpath("./td[6]//text()").extract_first()[1:],
            "currency": "USD",
            "order_date": datetime.datetime.strptime(
                order_dom.xpath("./td[4]//text()").extract_first(), "%m/%d/%Y"
            ).date(),
            "status": order_dom.xpath("./td[7]//text()").extract_first(),
            "products": [],
        }
        async with self.session.get(link) as resp:
            order_detail_response = Selector(text=await resp.text())
            order["order_id"] = (
                order_detail_response.xpath("//span[@id='ctl00_cphMainContent_referenceNbLbl']//text()").get().strip()
            )
            addresses = order_detail_response.xpath(
                "//span[@id='ctl00_cphMainContent_ucShippingAddr_lblAddress']//text()"
            ).extract()
            _, codes = addresses[-2].split(",")
            region_code, postal_code = codes.strip().split(" ")
            order["shipping_address"] = {
                "address": addresses[1],
                "region_code": region_code,
                "postal_code": postal_code,
            }

            for order_product_dom in order_detail_response.xpath(
                "//table[contains(@class, 'tblOrderableProducts')]//tr"
                "//table[@class='SimpleList']//tr[@class='ItemRow' or @class='AlternateItemRow']"
            ):
                product_name_url_dom = order_product_dom.xpath(
                    "./td[1]//table[@id='tblProduct']//span[@class='ProductDisplayName']"
                )
                product_id = self.extract_first(order_product_dom, ".//b/text()")
                product_name = self.extract_first(product_name_url_dom, ".//a/text()")
                product_url = self.merge_strip_values(product_name_url_dom, xpath=".//a/@href")
                quantity_price = self.merge_strip_values(
                    dom=order_product_dom, xpath=".//td[@id='QtyRow']//text()", delimeter=";"
                )
                quantity, _, product_price = quantity_price.split(";")
                product_price = re.search(r"\$(.*)/", product_price)
                product_price = product_price.group(1)

                if "invoice_link" not in order:
                    invoice_link = self.extract_first(
                        order_product_dom, "./td[@colspan='4' or @colspan='5']//table//tr[1]//td[2]/a/@href"
                    )

                    try:
                        invoice_link = (
                            invoice_link.split("javascript:checkInvoice")[1].strip("()'\"")
                            if invoice_link and "javascript:checkInvoice" in invoice_link
                            else ""
                        )
                        invoice_link = (
                            "https://www.henryschein.com/us-en/olp/"
                            f"invoiceloading.aspx?type=inv&invoice_num={invoice_link}"
                            if invoice_link
                            else ""
                        )
                    except (ValueError, AttributeError, KeyError):
                        invoice_link = ""
                    order["invoice_link"] = invoice_link

                status = self.merge_strip_values(
                    dom=order_product_dom, xpath=".//span[contains(@id, 'itemStatusLbl')]//text()"
                )
                order["products"].append(
                    {
                        "product": {
                            "product_id": product_id,
                            "name": product_name,
                            "description": "",
                            "url": product_url,
                            "images": [],
                            "category": "",
                            "price": product_price,
                            "vendor": self.vendor,
                        },
                        "quantity": quantity,
                        "unit_price": product_price,
                        "status": status,
                    }
                )

        await self.get_missing_products_fields(
            order["products"],
            fields=(
                "description",
                "images",
                "category",
            ),
        )
        return order

    async def get_product_as_dict(self, product_id, product_url, perform_login=False) -> dict:
        if perform_login:
            await self.login()

        async with self.session.get(product_url) as resp:
            res = Selector(text=await resp.text())
            product_detail = res.xpath(".//ul[@id='ctl00_cphMainContentHarmony_ucProductSummary_ulProductSummary']")
            product_name = self.extract_first(product_detail, ".//h2[contains(@class, 'product-title')]/text()")
            product_description = self.extract_first(res, ".//li[@class='customer-notes']/div[@class='value']/text()")
            product_images = res.xpath(
                ".//div[@id='ctl00_cphMainContentHarmony_ucProductAssets_divImgProduct']/img/@src"
            ).extract()
            product_price = self.extract_first(
                res,
                ".//li[@id='ctl00_cphMainContentHarmony_ucProductSummary_ucPackagingOptions"
                "_rptProductList_ctl00_liProductAction']//span[contains(@class, 'amount')]/text()",
            )
            product_price = re.findall("\\d+\\.\\d+", product_price)
            product_price = product_price[0] if isinstance(product_price, list) else None
            product_category = res.xpath(
                ".//div[contains(@class, 'product-image')]/ul/li/div[@class='value']/span/text()"
            ).extract()

            return {
                "product_id": product_id,
                "name": product_name,
                "description": product_description,
                "url": product_url,
                "images": [{"image": f"{self.BASE_URL}{product_image}"} for product_image in product_images],
                "category": product_category,
                "price": product_price,
                "vendor": self.vendor,
            }

    @catch_network
    async def get_orders(self, perform_login=False):
        url = f"{self.BASE_URL}/us-en/Orders/OrderStatus.aspx"

        if perform_login:
            await self.login()

        async with self.session.get(url) as resp:
            text = await resp.text()
            response_dom = Selector(text=text)
            orders_dom = response_dom.xpath(
                "//table[@class='SimpleList']//tr[@class='ItemRow' or @class='AlternateItemRow']"
            )
            tasks = (self.get_order(order_dom) for order_dom in orders_dom[6:7])
            orders = await asyncio.gather(*tasks, return_exceptions=True)

        return [Order.from_dict(order) for order in orders if isinstance(order, dict)]

    async def get_product_prices(self, product_ids, perform_login=False, **kwargs) -> Dict[str, Decimal]:
        if perform_login:
            await self.login()

        product_units = kwargs.get("product_units")
        products_price_data = [
            {
                "ProductId": int(product_id),
                "Qty": "1",
                "Uom": product_unit,
                "PromoCode": "",
                "CatalogName": "B_DENTAL",
                "ForceUpdateInventoryStatus": False,
                "AvailabilityCode": "01",
            }
            for product_id, product_unit in zip(product_ids, product_units)
        ]

        products_price_data = {
            "ItemArray": json.dumps(
                {
                    "ItemDataToPrice": products_price_data,
                }
            ),
            "searchType": "6",
            "did": "dental",
            "catalogName": "B_DENTAL",
            "endecaCatalogName": "DENTAL",
            "culture": "us-en",
            "showPriceToAnonymousUserFromCMS": "False",
            "isCallingFromCMS": "False",
        }

        headers = SEARCH_HEADERS.copy()
        headers["referer"] = kwargs.get("Referer")
        product_prices = {}
        async with self.session.post(
            "https://www.henryschein.com/webservices/JSONRequestHandler.ashx",
            data=products_price_data,
            headers=headers,
        ) as resp:
            res = await resp.json()
            for product_price in res["ItemDataToPrice"]:
                if product_price["InventoryStatus"] in ["Unavailable", "Error", "Discontinued", "Unknown"]:
                    continue
                product_prices[product_price["ProductId"]] = product_price["CustomerPrice"]
        return product_prices

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        url = f"{self.BASE_URL}/us-en/Search.aspx"
        page_size = 25
        params = {"searchkeyWord": query, "pagenumber": page}

        async with self.session.get(url, headers=SEARCH_HEADERS, params=params) as resp:
            response_dom = Selector(text=await resp.text())

        total_size_str = response_dom.xpath(".//span[@class='result-count']/text()").extract_first()
        try:
            total_size = int(total_size_str)
        except ValueError:
            total_size = 0
        products = []
        for product_dom in response_dom.css("section.product-listing ol.products > li.product > .title"):
            product_detail = product_dom.xpath(".//script[@type='application/ld+json']//text()").extract_first()
            product_unit = self.merge_strip_values(
                product_dom,
                "./ul[@class='product-actions']"
                "//div[contains(@class, 'color-label-gray')]/span[contains(@class, 'block')]//text()",
            )
            product_detail = json.loads(product_detail)
            products.append(
                {
                    "product_id": product_detail["sku"],
                    "product_unit": product_unit,
                    "name": product_detail["name"],
                    "description": product_detail["description"],
                    "url": product_detail["url"],
                    "images": [
                        {
                            "image": product_detail["image"],
                        }
                    ],
                    "price": Decimal(0),
                    "vendor": self.vendor,
                }
            )

        kwargs = {
            "Referer": f"https://www.henryschein.com/us-en/Search.aspx?searchkeyWord={query}",
            "product_units": [product["product_unit"] for product in products],
        }
        product_prices = await self.get_product_prices([product["product_id"] for product in products], **kwargs)
        res_products = []
        for product in products:
            if product["product_id"] not in product_prices:
                continue
            product["price"] = product_prices[product["product_id"]]
            res_products.append(product)

        return {
            "vendor_slug": self.vendor["slug"],
            "total_size": total_size,
            "page": page,
            "page_size": page_size,
            "products": [Product.from_dict(product) for product in res_products],
            "last_page": page_size * page >= total_size,
        }

    def _get_vendor_categories(self, response) -> List[ProductCategory]:
        return [
            ProductCategory(
                name=category.attrib["title"],
                slug=category.attrib["href"].split("/")[-1],
            )
            for category in response.xpath("//ul[contains(@class, 'hs-categories')]/li/a")
        ]

    async def get_cart(self):
        async with self.session.get("https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx") as resp:
            dom = Selector(text=await resp.text())
            return dom

    async def remove_product_from_cart(self, product_id: Union[str, int], use_bulk: bool = True):
        if not use_bulk:
            cart_dom = await self.get_cart()
            for i, product_dom in enumerate(
                cart_dom.xpath("//div[@id='ctl00_cphMainContentHarmony_ucOrderCartShop_pnlCartDetails']/ol/li")
            ):
                key = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{i + 1:02d}$txtQuantity"
                cart_product_id = product_dom.xpath(f'.//input[@name="{key}"]/@data-item-code-cart').get()
                if cart_product_id == product_id:
                    key = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{i + 1:02d}$hdnItemId"
                    product_id = product_dom.xpath(f'.//input[@name="{key}"]/@value').get()
                    break

        data = {
            "lineItemId": product_id,
            "cartId": "",
            "userId": "",
            "did": "dental",
            "catalogName": "B_DENTAL",
            "endecaCatalogName": "DENTAL",
            "searchType": "12",
            "culture": "us-en",
        }
        await self.session.post(
            "https://www.henryschein.com/webservices/JSONRequestHandler.ashx",
            headers=REMOVE_PRODUCT_FROM_CART_HEADERS,
            data=data,
        )
        return True

    async def clear_cart(self):
        cart_dom = await self.get_cart()
        product_ids = []
        for i, product_dom in enumerate(
            cart_dom.xpath("//div[@id='ctl00_cphMainContentHarmony_ucOrderCartShop_pnlCartDetails']/ol/li")
        ):
            key = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{i + 1:02d}$hdnItemId"
            product_ids.append(product_dom.xpath(f'.//input[@name="{key}"]/@value').get())

        tasks = (self.remove_product_from_cart(product_id) for product_id in product_ids)
        await asyncio.gather(*tasks)

    async def add_products_to_cart(self, products: List[CartProduct]) -> List[VendorCartProduct]:
        tasks = (self.add_product_to_cart(product) for product in products)
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def add_product_to_cart(self, product: CartProduct) -> VendorCartProduct:
        params = {
            "addproductid": product["product_id"],
            "addproductqty": product["quantity"],
            "allowRedirect": "false",
        }
        async with self.session.get(
            "https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx", params=params
        ) as resp:
            response_text = await resp.text()
            # TODO: Error handling
            ecommerce_data = response_text.split("dataLayer.push(", 1)[1].split(");")[0]
            ecommerce_data = ecommerce_data.replace("'", '"')
            ecommerce_data = json.loads(ecommerce_data)
            products = ecommerce_data["ecommerce"]["checkout"]["products"]
            vendor_cart_product = [p for p in products if str(p["id"]) == str(product["product_id"])][0]
            return {"product_id": product["product_id"], "unit_price": vendor_cart_product["price"]}

    @staticmethod
    def get_checkout_products_sensitive_data(dom):
        data = {}
        for i, product_dom in enumerate(
            dom.xpath("//div[@id='ctl00_cphMainContentHarmony_ucOrderCartShop_pnlCartDetails']/ol/li")
        ):
            product_index = f"{i + 1:02d}"
            for key in [
                "$ucProductDetailsForEnhancedView$hiddenProductId",
                "$ucProductDetailsForEnhancedView$hiddenProductAvailabilityCode",
                "$ucProductDetailsForEnhancedView$hiddenInventoryAvailabilityCode",
                "$ucProductDetailsForEnhancedView$hiddenImgProduct",
                "$hdnPriceLabel1",
                "$hdnPriceLabel2",
                "$oldQty",
                "$txtQuantity",
                "$hdnItemId",
                "$ucProductDetailsForEnhancedView$hiddenUom",
            ]:
                key = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{product_index}{key}"
                data[key] = product_dom.xpath(f'.//input[@name="{key}"]/@value').get()
        return data

    def get_product_checkout_prices(self, dom):
        data = {}
        for i, product_dom in enumerate(
            dom.xpath("//div[@id='ctl00_cphMainContentHarmony_ucOrderCartShop_pnlCartDetails']/ol/li")
        ):
            product_index = f"{i + 1:02d}"
            product_id = self.extract_first(dom, ".//h2[@class='product-name']/small/strong/text()")
            unit_price = self.extract_first(
                dom,
                ".//div[@id='ctl00_cphMainContentHarmony_ucOrderCartShop_rptBasket_ctl"
                f"{product_index}_divPrice']/span[1]/text()",
            ).strip("$")
            data[product_id] = unit_price
        return data

    async def checkout(self, products: List[CartProduct], checkout_time: Optional[datetime.date] = None):
        if not checkout_time:
            checkout_time = datetime.date.today()

        cart_dom = await self.get_cart()
        data = {
            "__LASTFOCUS": "",
            "ctl00_ScriptManager_TSM": ";;System.Web.Extensions, Version=4.0.0.0, Culture=neutral, "
            "PublicKeyToken=31bf3856ad364e35:en-US:f319b152-218f-4c14-829d-050a68bb1a61:ea597d4b:b25378d2",
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": cart_dom.xpath("//input[@name='__VIEWSTATE']/@value").get(),
            "__VIEWSTATEGENERATOR": cart_dom.xpath("//input[@name='__VIEWSTATEGENERATOR']/@value").get(),
            "ctl00$ucHeader$ucSearchBarHeaderbar$txtSearch": "",
            "ctl00$cphMainContentHarmony$ucOrderActionBarBottomShop$btnCheckout": cart_dom.xpath(
                "//input[@name='ctl00$cphMainContentHarmony$ucOrderActionBarBottomShop$btnCheckout']/@value"
            ).get(),
            "layout": "on",
            "ctl00$cphMainContentHarmony$ucOrderTopBarShop$txtItemCode": "",
            "ctl00$cphMainContentHarmony$ucOrderTopBarShop$txtQty": "",
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtPurchaseOrder": (
                f'{checkout_time.strftime("%m/%d/%Y")} - Ordo Order'
            ),
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtPromoCode": "",
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtSpecialInstructions": "",
            "dest": "",
        }

        data.update(self.get_checkout_products_sensitive_data(cart_dom))

        headers = CHECKOUT_HEADER.copy()
        headers["referer"] = "https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx"
        async with self.session.post(
            "https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx", headers=headers, data=data
        ) as resp:
            response_dom = Selector(text=await resp.text())
            if len(response_dom.xpath("//div[@id='MessagePanel']/div[contains(@class, 'informational')]")):
                return await self.checkout(products)
            else:
                return response_dom

    async def review_checkout(self, checkout_dom):
        data = {
            "ctl00_ScriptManager_TSM": ";;System.Web.Extensions, Version=4.0.0.0, Culture=neutral, "
            "PublicKeyToken=31bf3856ad364e35:en-US:f319b152-218f-4c14-829d-050a68bb1a61:ea597d4b:b25378d2",
            "__EVENTTARGET": "ctl00$cphMainContentHarmony$hylNext",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": checkout_dom.xpath("//input[@name='__VIEWSTATE']/@value").get(),
            "__VIEWSTATEGENERATOR": checkout_dom.xpath("//input[@name='__VIEWSTATEGENERATOR']/@value").get(),
            "SideMenuControl1000txtItemCodeId": "",
            "SideMenuControl1000txtItemQtyId": "",
            "ctl00$ucHeader$ucSearchBarHeaderbar$txtSearch": "",
            "SideMenuControl1000txtItemCodeId9": "",
            "SideMenuControl1000txtItemQtyId9": "",
            "ctl00_cpAsideMenu_AsideMenu_SideMenuControl1000txtItemCodeId": "",
            "ctl00_cpAsideMenu_AsideMenu_SideMenuControl1000txtItemQtyId": "",
            "layout": "on",
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ddlShippingMethod": checkout_dom.xpath(
                "//select[@name='ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ddlShippingMethod']"
                "/option[@selected]/@value"
            ).get(),
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ddlPaymentMethod": (
                "1|{a62154f0-a1cc-47e4-b78b-805ed7890527}"
            ),
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$hiddenModifyLink": (
                "https://www.henryschein.com/us-en/checkout/CheckoutCreditCard.aspx?action=0&ccid={0}&overlay=true"
            ),
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$txtPo": checkout_dom.xpath(
                "//input[@id='ctl00_cphMainContentHarmony_ucOrderPaymentAndOptionsShop_txtPo']/@value"
            ).get(),
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$": "rbnNoDelayNoRecurring",
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$dpStartDate": (
                checkout_dom.xpath(
                    "//input[@name='ctl00$cphMainContentHarmony"
                    "$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$dpStartDate']/@value"
                ).get()
            ),
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$ddlFrequency": "Weekly",
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$dpEndDate": (
                checkout_dom.xpath(
                    "//input[@name='ctl00$cphMainContentHarmony"
                    "$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$dpEndDate']/@value"
                ).get()
            ),
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$ddlTotal": "Select One",
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$checkoutType": "Normal",
            "dest": "",
        }

        params = {
            "PaymentIndex": "0",
        }

        headers = CHECKOUT_HEADER.copy()
        headers["referer"] = "https://www.henryschein.com/us-en/Checkout/BillingShipping.aspx"
        async with self.session.post(
            "https://www.henryschein.com/us-en/Checkout/BillingShipping.aspx",
            headers=headers,
            params=params,
            data=data,
        ) as resp:
            return Selector(text=await resp.text())

    async def review_order(self, review_checkout_dom):
        subtotal_amount = self.extract_first(
            review_checkout_dom,
            "//div[@id='ctl00_cphMainContentHarmony_divOrderSummarySubTotal']/strong//text()",
        )
        tax_amount = self.extract_first(
            review_checkout_dom, "//div[@id='ctl00_cphMainContentHarmony_divOrderSummaryTax']/strong//text()"
        )
        shipping_amount = self.extract_first(
            review_checkout_dom, "//div[@id='ctl00_cphMainContentHarmony_divOrderSummaryShipping']/strong//text()"
        )
        total_amount = self.extract_first(
            review_checkout_dom, "//div[@id='ctl00_cphMainContentHarmony_divOrderSummaryTotal']/strong//text()"
        )
        savings_amount = self.extract_first(
            review_checkout_dom, "//div[@id='ctl00_cphMainContentHarmony_divOrderSummarySaving']/strong//text()"
        )
        # shipping_method = self.extract_first(
        #     review_checkout_dom,
        #     "//div[@id='ctl00_cphMainContentHarmony_divOrderSummaryShippingMethod']/strong//text()",
        # )
        payment_method = self.extract_first(
            review_checkout_dom, "//div[@id='ctl00_cphMainContentHarmony_divOrderSummaryPaymentMethod']/strong//text()"
        )
        shipping_address = self.merge_strip_values(
            review_checkout_dom,
            "//section[contains(@class, 'order-details')]"
            "//section[contains(@class, 'half')]/div[@class='half'][1]//address/p/span[2]/text()",
        )
        # billing_address = self.merge_strip_values(
        #     review_checkout_dom,
        #     "//section[contains(@class, 'order-details')]"
        #     "//section[contains(@class, 'half')]/div[@class='half'][2]//address/p/span[2]/text()",
        # )
        # product_prices = self.get_product_checkout_prices(review_checkout_dom)
        return VendorOrderDetail.from_dict(
            {
                "retail_amount": 0,
                "savings_amount": savings_amount.strip("$") if isinstance(savings_amount, str) else savings_amount,
                "subtotal_amount": subtotal_amount.strip("$") if isinstance(subtotal_amount, str) else subtotal_amount,
                "shipping_amount": shipping_amount.strip("$") if isinstance(shipping_amount, str) else shipping_amount,
                "tax_amount": tax_amount.strip("$") if isinstance(tax_amount, str) else tax_amount,
                "total_amount": total_amount.strip("$") if isinstance(total_amount, str) else total_amount,
                "payment_method": payment_method,
                "shipping_address": shipping_address,
            }
        )

    async def create_order(self, products: List[CartProduct]) -> Dict[str, VendorOrderDetail]:
        await self.login()
        await self.clear_cart()
        await self.add_products_to_cart(products)
        checkout_dom = await self.checkout(products)
        review_checkout_dom = await self.review_checkout(checkout_dom)
        vendor_order_detail = await self.review_order(review_checkout_dom)
        return {
            self.vendor["slug"]: {
                **vendor_order_detail.to_dict(),
                **self.vendor,
            },
        }

    async def confirm_order(self, products: List[CartProduct], fake=False):
        await self.login()
        await self.clear_cart()
        await self.add_products_to_cart(products)
        checkout_dom = await self.checkout(products)
        review_checkout_dom = await self.review_checkout(checkout_dom)
        vendor_order_detail = await self.review_order(review_checkout_dom)

        if fake:
            return {
                **vendor_order_detail.to_dict(),
                "order_id": f"{uuid.uuid4()}",
            }
        else:
            headers = CHECKOUT_HEADER.copy()
            headers["referer"] = "https://www.henryschein.com/us-en/Checkout/OrderReview.aspx"

            data = {
                "ctl00_ScriptManager_TSM": ";;System.Web.Extensions, Version=4.0.0.0, Culture=neutral, "
                "PublicKeyToken=31bf3856ad364e35:en-US:f319b152-218f-4c14-829d-050a68bb1a61:ea597d4b:b25378d2",
                "__EVENTTARGET": "ctl00$cphMainContentHarmony$lnkNextShop",
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": review_checkout_dom.xpath("//input[@name='__VIEWSTATE']/@value").get(),
                "__VIEWSTATEGENERATOR": review_checkout_dom.xpath(
                    "//input[@name='__VIEWSTATEGENERATOR']/@value"
                ).get(),
                "ctl00_cpAsideMenu_AsideMenu_SideMenuControl1000txtItemCodeId": "",
                "ctl00_cpAsideMenu_AsideMenu_SideMenuControl1000txtItemQtyId": "",
                "layout": "on",
                "dest": "",
            }
            data.update(self.get_checkout_products_sensitive_data(review_checkout_dom))

            async with self.session.post(
                "https://www.henryschein.com/us-en/Checkout/OrderReview.aspx", headers=headers, data=data
            ) as resp:
                response = await resp.text()
                res_data = response.split("dataLayer.push(", 1)[1].split(");")[0]
                res_data = res_data.replace("'", '"')
                res_data = json.loads(res_data)
                return {
                    **vendor_order_detail.to_dict(),
                    "order_id": res_data["ecommerce"]["purchase"]["actionField"]["id"],
                }
