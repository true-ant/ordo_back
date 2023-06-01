import asyncio
import datetime
import json
import logging
import re
import time
import uuid
from decimal import Decimal
from typing import Dict, List, Optional
from urllib.parse import urlparse

from aiohttp import ClientResponse
from dateutil.relativedelta import relativedelta
from scrapy import Selector

from apps.common import messages as msgs
from apps.scrapers.base import Scraper
from apps.scrapers.headers.base import HTTP_HEADERS
from apps.scrapers.headers.henryschein import (
    ADD_CART_HEADERS,
    CHECKOUT_HEADER,
    CLEAR_CART_HEADERS,
    LOGIN_HEADERS,
    SEARCH_HEADERS,
)
from apps.scrapers.schema import Order, Product, ProductCategory, VendorOrderDetail
from apps.scrapers.utils import catch_network, semaphore_coroutine
from apps.types.orders import CartProduct, VendorCartProduct
from apps.types.scraper import (
    InvoiceFormat,
    InvoiceType,
    LoginInformation,
    ProductSearch,
    SmartProductID,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

SHIPPING_METHOD_MAPPING = {
    "UPS Standard Delivery": "5ef38968-cec2-4a92-9bf5-eec83f515601",
    "Next Day Delivery (extra charge)": "1dee35c6-bd47-4a26-b1c0-57b9865c1f62",
    "Saturday Delivery (extra charge)": "37f3017d-c881-4c5d-bc7c-463b2379ee58",
    "Next Day 10:30 (extra charge)": "6100e1b6-d1d4-4f3a-afec-ca085f0ab9a0",
    "2nd Day Air (extra charge)": "ebf5a034-4e0a-4e70-b8ba-f8ae79ee533c",
}


def extract_text(element):
    if element:
        text = re.sub(r"\s+", " ", " ".join(element.xpath(".//text()").extract()))
        return text.strip() if text else ""
    return ""


class HenryScheinScraper(Scraper):
    BASE_URL = "https://www.henryschein.com"
    CATEGORY_URL = "https://www.henryschein.com/us-en/dental/c/browsesupplies"
    TRACKING_BASE_URL = "https://narvar.com/tracking/itemvisibility/v1/henryschein-dental/orders"
    INVOICE_TYPE = InvoiceType.PDF_INVOICE
    INVOICE_FORMAT = InvoiceFormat.USE_VENDOR_FORMAT

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        res = await response.json()
        return res.get("IsAuthenticated", False)

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        async with self.session.get(
            "https://www.henryschein.com/us-en/dental/Default.aspx", headers=HTTP_HEADERS
        ) as resp:
            text = await resp.text()
            n = text.split("var _n =")[1].split(";")[0].strip(" '")
        self.session.headers.update({"n": n})
        return {
            "url": f"{self.BASE_URL}/webservices/LoginRequestHandler.ashx",
            "headers": LOGIN_HEADERS,
            "data": {
                "username": self.username,
                "password": self.password,
                "did": "dental",
                "searchType": "authenticateuser",
                "culture": "us-en",
            },
        }

    @semaphore_coroutine
    async def get_order(self, sem, order_dom, office=None):
        print("henryschein/get_order")
        if len(order_dom.xpath("./td")) == 8:
            total_amount_table_index = 6
            order_date_table_index = 4
            status_table_index = 7
        else:
            total_amount_table_index = 4
            order_date_table_index = 2
            status_table_index = 5
        link = order_dom.xpath("./td[last()]/a/@href").extract_first().strip()
        logger.debug(f"Getting order from {link}")
        order = {
            "total_amount": self.extract_amount(
                order_dom.xpath(f"./td[{total_amount_table_index}]//text()").extract_first()
            ),
            "currency": "USD",
            "order_date": datetime.datetime.strptime(
                order_dom.xpath(f"./td[{order_date_table_index}]//text()").extract_first(), "%m/%d/%Y"
            ).date(),
            "status": order_dom.xpath(f"./td[{status_table_index}]//text()").extract_first(),
            "products": [],
        }
        async with self.session.get(link) as resp:
            print("===== henryschein/get_order 1 =====")
            order_detail_response = Selector(text=await resp.text())
            order["vendor_order_reference"] = (
                order_detail_response.xpath("//span[@id='ctl00_cphMainContent_referenceNbLbl']//text()").get().strip()
            )
            order_id = order_detail_response.xpath("//span[@id='ctl00_cphMainContent_orderNbLbl']//text()").get()
            order["order_id"] = order_id if order_id else order["vendor_order_reference"]

            print("===== henryschein/get_order 2 =====")
            logger.debug(f"Got order which id is {order['order_id']}")
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
            print("===== henryschein/get_order 3 =====")

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
                quantity = quantity_price.split(";")[0].strip("-")
                product_price = re.search(r"\$(.*)/", quantity_price)
                product_price = product_price.group(1)
                product_status = self.extract_first(
                    order_product_dom, "./td[@colspan='4' or @colspan='5']//table//tr[1]//td[3]//text()"
                )

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

                # get product tracking link
                tracking_link = self.extract_first(
                    order_product_dom, "./td[@colspan='4' or @colspan='5']//table//tr[1]//td[4]/a/@href"
                )

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
                            "status": product_status,
                            "vendor": self.vendor.to_dict(),
                        },
                        "quantity": quantity,
                        "unit_price": product_price,
                        "status": status,
                        "tracking_link": tracking_link,
                    }
                )

        await self.get_missing_products_fields(
            order["products"],
            fields=(
                "description",
                "images",
                "category",
                "product_unit",
                "manufacturer_number",
            ),
        )
        if office:
            print("===== henryschein/get_order 10 =====")
            logger.debug(f"storing order {order['order_id']} to db")
            await self.save_order_to_db(office, order=Order.from_dict(order))
            logger.debug(f"stored order {order['order_id']} to db")
        return order

    def parse_manufacturer_number(self, manufacturer_data):
        if manufacturer_data:
            parts = manufacturer_data.split("-")
            if parts:
                return parts[-1].strip()
        else:
            return None

    async def get_product_as_dict(self, product_id, product_url, perform_login=False) -> dict:
        print("henryschein/get_product_as_dict")
        if perform_login:
            await self.login()

        async with self.session.get(product_url) as resp:
            res = Selector(text=await resp.text())
            product_detail = res.xpath(".//ul[@id='ctl00_cphMainContentHarmony_ucProductSummary_ulProductSummary']")
            product_name = self.extract_first(product_detail, ".//h2[contains(@class, 'product-title')]/text()")
            manufacturer_data = self.extract_first(
                product_detail, ".//h2[contains(@class, 'product-title')]/small/text()"
            )
            manufacturer_number = self.parse_manufacturer_number(manufacturer_data)
            product_description = self.extract_first(res, ".//li[@class='customer-notes']/div[@class='value']/text()")
            product_images = res.xpath(
                ".//div[@id='ctl00_cphMainContentHarmony_ucProductAssets_divImgProduct']/img/@src"
            ).extract()
            product_price = self.extract_first(
                res,
                ".//li[@id='ctl00_cphMainContentHarmony_ucProductSummary_ucPackagingOptions"
                "_rptProductList_ctl00_liProductAction']//span[contains(@class, 'amount')]/text()",
            )
            product_price = self.extract_amount(product_price) if product_price else None
            product_category = res.xpath(
                ".//div[contains(@class, 'product-image')]/ul/li/div[@class='value']/span/text()"
            ).extract()
            product_unit = self.extract_first(
                res,
                ".//li[@id='ctl00_cphMainContentHarmony_ucProductSummary_ucPackagingOptions"
                "_rptProductList_ctl00_liProductAction']//div[contains(@class, 'uom-opts')]/span/text()",
            )

            return {
                "product_id": product_id,
                "name": product_name,
                "description": product_description,
                "url": product_url,
                "images": [{"image": f"{self.BASE_URL}{product_image}"} for product_image in product_images],
                "category": product_category,
                "price": product_price,
                "product_unit": product_unit,
                "vendor": self.vendor.to_dict(),
                "manufacturer_number": manufacturer_number,
            }

    @catch_network
    async def get_orders(
        self,
        office=None,
        perform_login=False,
        from_date: Optional[datetime.date] = None,
        to_date: Optional[datetime.date] = None,
        completed_order_ids: Optional[List[str]] = None,
    ) -> List[Order]:
        print("henryschein/get_orders")

        params = {}
        if from_date and to_date:
            from_date = from_date.strftime("%m/%d/%Y")
            to_date = to_date.strftime("%m/%d/%Y")
        else:
            from_date = (datetime.datetime.now() - relativedelta(years=2)).date().strftime("%m/%d/%Y")
            to_date = datetime.datetime.today().date().strftime("%m/%d/%Y")

        params["Search"] = f"dateRangeSF|{from_date}|{to_date}"

        url = f"{self.BASE_URL}/us-en/Orders/OrderStatus.aspx"

        if perform_login:
            await self.login()

        sem = asyncio.Semaphore(value=2)
        async with self.session.get(url, params=params) as resp:
            text = await resp.text()
            response_dom = Selector(text=text)
            orders_dom = response_dom.xpath(
                "//table[@class='SimpleList']//tr[@class='ItemRow' or @class='AlternateItemRow']"
            )
            tasks = (
                self.get_order(sem, order_dom, office)
                for order_dom in orders_dom
                if completed_order_ids is None
                or self.extract_first(order_dom, "./td[1]/text()") not in completed_order_ids
            )
            orders = await asyncio.gather(*tasks, return_exceptions=True)

        return [Order.from_dict(order) for order in orders if isinstance(order, dict)]

    async def get_product_prices(self, product_ids, perform_login=False, **kwargs) -> Dict[str, Decimal]:
        print("henryschein/get_product_prices")

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
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0, sort_by="price", office_id=None
    ) -> ProductSearch:
        print("henryschein/_search_products")
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
                    "vendor": self.vendor.to_dict(),
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
            "vendor_slug": self.vendor.slug,
            "total_size": total_size,
            "page": page,
            "page_size": page_size,
            "products": [Product.from_dict(product) for product in res_products],
            "last_page": page_size * page >= total_size,
        }

    def _get_vendor_categories(self, response) -> List[ProductCategory]:
        print("henryschein/_get_vendor_categories")
        return [
            ProductCategory(
                name=category.attrib["title"],
                slug=category.attrib["href"].split("/")[-1],
            )
            for category in response.xpath("//ul[contains(@class, 'hs-categories')]/li/a")
        ]

    async def get_cart(self):
        print("henryschein/get_cart")
        async with self.session.get("https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx") as resp:
            dom = Selector(text=await resp.text())
            return dom

    async def remove_product_from_cart(
        self, product_id: SmartProductID, perform_login: bool = False, use_bulk: bool = True
    ):
        if perform_login:
            await self.login()

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
            headers=CLEAR_CART_HEADERS,
            data=data,
        )
        return True

    async def clear_cart(self):
        cart_dom = await self.get_cart()
        data = {
            "__LASTFOCUS": "",
            "ctl00_ScriptManager_TSM": ";;System.Web.Extensions, Version=4.0.0.0, Culture=neutral, "
            "PublicKeyToken=31bf3856ad364e35:en-US:f319b152-218f-4c14-829d-050a68bb1a61:ea597d4b:b25378d2",
            "__EVENTTARGET": "ctl00$cphMainContentHarmony$ucOrderActionBarBottomShop$btnClearOrder",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": cart_dom.xpath("//input[@name='__VIEWSTATE']/@value").get(),
            "__VIEWSTATEGENERATOR": cart_dom.xpath("//input[@name='__VIEWSTATEGENERATOR']/@value").get(),
            "ctl00$ucHeader$ucSearchBarHeaderbar$txtSearch": "",
            "ctl00$ucHeader$ucSearchBarHeaderbar$hdnKeywordText": "Keywords",
            "ctl00$ucHeader$ucSearchBarHeaderbar$hdnCategoryText": "Category",
            "ctl00$ucHeader$ucSearchBarHeaderbar$hdnManufacturerText": "Manufacturer",
            "ctl00$ucHeader$ucSearchBarHeaderbar$hdnContentResultsText": "Content Result",
            "ctl00$ucHeader$ucSearchBarHeaderbar$hdnRecommendedProducts": "Recommended products for",
            "ctl00$ucHeader$ucSearchBarHeaderbar$hdnAddText": "Add",
            "ctl00$cphMainContentHarmony$ucOrderTopBarShop$txtItemCode": "",
            "ctl00$cphMainContentHarmony$ucOrderTopBarShop$txtQty": "",
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtPurchaseOrder": cart_dom.xpath(
                '//input[@name="ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtPurchaseOrder"]/@value'
            ).get(),
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtPromoCode": cart_dom.xpath(
                '//input[@name="ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtPromoCode"]/@value'
            ).get(),
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtSpecialInstructions": "",
            "dest": "",
        }
        data.update(self.get_checkout_products_sensitive_data(cart_dom))
        await self.session.post(
            "https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx", headers=CLEAR_CART_HEADERS, data=data
        )

    async def add_products_to_cart(self, products: List[CartProduct]) -> List[VendorCartProduct]:
        ItemDataToAdd = []
        for product in products:
            product_data = (
                f'"ProductId":{product["product_id"]},'
                f'"Qty":"{product["quantity"]}",'
                f'"Uom":"{product["product_unit"]}",'
                f'"CheckProductIdForPromoCode":"False",'
                f'"CheckExternalMapping":"False",'
                f'"CheckBackOrderStatus":"False",'
                f'"IsProductInventoryStatusLoaded":"True",'
                f'"LineItemId":""'
            )
            product_data = "{" + product_data + "}"
            ItemDataToAdd.append(product_data)
        data = {
            "ItemArray": '{"ItemDataToAdd":[' + ",".join(ItemDataToAdd) + "]}",
            "searchType": "5",
            "did": "dental",
            "catalogName": "B_DENTAL",
            "endecaCatalogName": "DENTAL",
            "culture": "us-en",
        }
        await self.session.post(
            "https://www.henryschein.com/webservices/JSONRequestHandler.ashx", headers=ADD_CART_HEADERS, data=data
        )

    async def add_product_to_cart(self, product: CartProduct, perform_login=False) -> VendorCartProduct:
        if perform_login:
            await self.login()

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

        response_dom = await self.get_cart()
        data = {
            "__LASTFOCUS": "",
            "ctl00_ScriptManager_TSM": ";;System.Web.Extensions, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf"
            "3856ad364e35:en-US:f319b152-218f-4c14-829d-050a68bb1a61:ea597d4b:b25378d2",
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": response_dom.xpath("//input[@name='__VIEWSTATE']/@value").get(),
            "__VIEWSTATEGENERATOR": response_dom.xpath("//input[@name='__VIEWSTATEGENERATOR']/@value").get(),
            "ctl00$ucHeader$ucSearchBarHeaderbar$txtSearch": "",
            "ctl00$cphMainContentHarmony$ucOrderActionBarBottomShop$btnCheckout": response_dom.xpath(
                "//input[@name='ctl00$cphMainContentHarmony$ucOrderActionBarBottomShop$btnCheckout']/@value"
            ).get(),
            "layout": "on",
            "ctl00$cphMainContentHarmony$ucOrderTopBarShop$txtItemCode": "",
            "ctl00$cphMainContentHarmony$ucOrderTopBarShop$txtQty": "",
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtPurchaseOrder": f'{time.strftime("%m/%d/%Y")} - Ordo Or'
            "der",
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtPromoCode": "",
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtSpecialInstructions": "",
            "dest": "",
        }
        for index, product_row in enumerate(
            response_dom.xpath("//div[@id='ctl00_cphMainContentHarmony_ucOrderCartShop_pnlCartDetails']/ol/li")
        ):
            key1 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$ucProductDetailsForEnhance"
            "dView$hiddenProductId"
            data[key1] = product_row.xpath(f'.//input[@name="{key1}"]/@value').get()

            key2 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$ucProductDetailsForEnhance"
            "dView$hiddenProductAvailabilityCode"
            data[key2] = product_row.xpath(f'.//input[@name="{key2}"]/@value').get()

            key3 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$ucProductDetailsForEnhance"
            "dView$hiddenInventoryAvailabilityCode"
            data[key3] = product_row.xpath(f'.//input[@name="{key3}"]/@value').get()

            key4 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$ucProductDetailsForEnhance"
            "dView$hiddenImgProduct"
            data[key4] = product_row.xpath(f'.//input[@name="{key4}"]/@value').get()

            key5 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$hdnPriceLabel1"
            data[key5] = product_row.xpath(f'.//input[@name="{key5}"]/@value').get()

            key6 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$hdnPriceLabel2"
            data[key6] = product_row.xpath(f'.//input[@name="{key6}"]/@value').get()

            key7 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$oldQty"
            data[key7] = product_row.xpath(f'.//input[@name="{key7}"]/@value').get()

            key8 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$txtQuantity"
            data[key8] = product_row.xpath(f'.//input[@name="{key8}"]/@value').get()

            key9 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$hdnItemId"
            data[key9] = product_row.xpath(f'.//input[@name="{key9}"]/@value').get()

            key10 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$ucProductDetailsForEnhanc"
            "edView$hiddenUom"
            data[key10] = product_row.xpath(f'.//input[@name="{key10}"]/@value').get()

        headers = CHECKOUT_HEADER.copy()
        headers["referer"] = "https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx"
        async with self.session.post(
            "https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx", headers=headers, data=data
        ) as resp:
            response_dom = Selector(text=await resp.text())
            return response_dom

    async def review_checkout(self, response_dom, shipping_method=None):
        if len(response_dom.xpath("//div[@id='MessagePanel']/div[contains(@class, 'informational')]")):
            print("Found Notification.. Re-requesting...")
            response = await self.checkout()
            response_dom = Selector(text=await response.text())

        headers = CHECKOUT_HEADER.copy()
        headers["referer"] = "https://www.henryschein.com/us-en/Checkout/BillingShipping.aspx?PaymentIndex=0"

        data = {
            "ctl00_ScriptManager_TSM": ";;System.Web.Extensions, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf"
            "3856ad364e35:en-US:f319b152-218f-4c14-829d-050a68bb1a61:ea597d4b:b25378d2",
            "__EVENTTARGET": "ctl00$cphMainContentHarmony$hylNext",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": response_dom.xpath("//input[@name='__VIEWSTATE']/@value").get(),
            "__VIEWSTATEGENERATOR": response_dom.xpath("//input[@name='__VIEWSTATEGENERATOR']/@value").get(),
            "SideMenuControl1000txtItemCodeId": "",
            "SideMenuControl1000txtItemQtyId": "",
            "ctl00$ucHeader$ucSearchBarHeaderbar$txtSearch": "",
            "SideMenuControl1000txtItemCodeId9": "",
            "SideMenuControl1000txtItemQtyId9": "",
            "ctl00_cpAsideMenu_AsideMenu_SideMenuControl1000txtItemCodeId": "",
            "ctl00_cpAsideMenu_AsideMenu_SideMenuControl1000txtItemQtyId": "",
            "layout": "on",
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ddlShippingMethod": SHIPPING_METHOD_MAPPING[
                shipping_method if shipping_method else "UPS Standard Delivery"
            ],
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ddlPaymentMethod": "1|{a62154f0-a1cc-47e4-b78b-8"
            "05ed7890527}",
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$hiddenModifyLink": "https://www.henryschein.com/"
            "us-en/checkout/CheckoutCreditCard.aspx?action=0&ccid={0}&overlay=true",
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$txtPo": response_dom.xpath(
                "//input[@id='ctl00_cphMainContentHarmony_ucOrderPaymentAndOptionsShop_txtPo']/@value"
            ).get(),
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$": "rbnNoDelayNoRecurring",
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSc"
            "hedulingOptions$dpStartDate": response_dom.xpath(
                "//input[@name='ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$dpStartD"
                "ate']/@value"
            ).get(),
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$ddlFrequency": "Weekly",
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSc"
            "hedulingOptions$dpEndDate": response_dom.xpath(
                "//input[@name='ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$dpEndDate"
                "']/@value"
            ).get(),
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$ddlTotal": "Select One",
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$checkoutType": "Normal",
            "dest": "",
        }

        params = (("PaymentIndex", "0"),)
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
                "reduction_amount": total_amount.strip("$") if isinstance(total_amount, str) else total_amount,
                "payment_method": payment_method,
                "shipping_address": shipping_address,
            }
        )

    async def track_product(self, order_id, product_id, tracking_link, tracking_number, perform_login=False):
        parsed_url = urlparse(tracking_link)
        if parsed_url.netloc == "www.henryschein.com":
            if perform_login:
                await self.login()

            async with self.session.post(tracking_link) as resp:
                tracking_link = str(resp.url)
                parsed_url = urlparse(tracking_link)

            tracking_link = f"{self.TRACKING_BASE_URL}/{order_id}?{parsed_url.query}&tracking_url={tracking_link}"

        async with self.session.get(tracking_link) as resp:
            res = await resp.json()

        for shipment in res["order_info"]["shipments"]:
            for item in shipment["items_info"]:
                if item["sku"] == product_id:
                    return self.normalize_product_status(shipment["status"])

    async def confirm_order(self, products: List[CartProduct], shipping_method="UPS Standard Delivery", fake=False):
        print("confirm_order")
        await self.clear_cart()
        await self.add_products_to_cart(products)
        checkout_dom = await self.checkout(products)
        review_checkout_dom = await self.review_checkout(checkout_dom, shipping_method)
        vendor_order_detail = await self.review_order(review_checkout_dom)
        if fake:
            print("henryschein/confirm_order DONE")
            return {
                **vendor_order_detail.to_dict(),
                "order_id": f"{uuid.uuid4()}",
                "order_type": msgs.ORDER_TYPE_ORDO,
            }
        headers = CHECKOUT_HEADER.copy()
        headers["referer"] = "https://www.henryschein.com/us-en/Checkout/OrderReview.aspx"

        data = [
            (
                "ctl00_ScriptManager_TSM",
                ";;System.Web.Extensions, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35:en-US:"
                "f319b152-218f-4c14-829d-050a68bb1a61:ea597d4b:b25378d2",
            ),
            ("__EVENTTARGET", "ctl00$cphMainContentHarmony$lnkNextShop"),
            ("__EVENTARGUMENT", ""),
            ("__VIEWSTATE", review_checkout_dom.xpath("//input[@name='__VIEWSTATE']/@value").get()),
            (
                "__VIEWSTATEGENERATOR",
                review_checkout_dom.xpath("//input[@name='__VIEWSTATEGENERATOR']/@value").get(),
            ),
            ("ctl00_cpAsideMenu_AsideMenu_SideMenuControl1000txtItemCodeId", ""),
            ("ctl00_cpAsideMenu_AsideMenu_SideMenuControl1000txtItemQtyId", ""),
            ("layout", "on"),
            ("dest", ""),
        ]

        for index, product_row in enumerate(
            review_checkout_dom.xpath("//div[@id='ctl00_cphMainContentHarmony_ucOrderCartShop_pnlCartDetails']/ol/li")
        ):
            key1 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$ucProductDetailsForEnh"
            "ancedView$hiddenProductId"
            data.append((key1, product_row.xpath(f'.//input[@name="{key1}"]/@value').get()))

            key2 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$ucProductDetailsForEnh"
            "ancedView$hiddenProductAvailabilityCode"
            data.append((key2, product_row.xpath(f'.//input[@name="{key2}"]/@value').get()))

            key3 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$ucProductDetailsForEnh"
            "ancedView$hiddenInventoryAvailabilityCode"
            data.append((key3, product_row.xpath(f'.//input[@name="{key3}"]/@value').get()))

            key4 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$ucProductDetailsForEnh"
            "ancedView$hiddenImgProduct"
            data.append((key4, product_row.xpath(f'.//input[@name="{key4}"]/@value').get()))

            key5 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$hdnPriceLabel1"
            data.append((key5, product_row.xpath(f'.//input[@name="{key5}"]/@value').get()))

            key6 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$hdnPriceLabel2"
            data.append((key6, product_row.xpath(f'.//input[@name="{key6}"]/@value').get()))

            key7 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$oldQty"
            data.append((key7, product_row.xpath(f'.//input[@name="{key7}"]/@value').get()))

            key8 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$ucProductDetailsForEnh"
            "ancedView$hiddenUom"
            data.append((key8, product_row.xpath(f'.//input[@name="{key8}"]/@value').get()))

            key9 = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{index+1:02d}$hdnItemId"
            data.append((key9, product_row.xpath(f'.//input[@name="{key9}"]/@value').get()))

        async with self.session.post(
            "https://www.henryschein.com/us-en/Checkout/OrderReview.aspx", headers=headers, data=data
        ) as resp:
            response_text = await resp.text()
        logger.debug("Got response from order review: %s", response_text)
        res_data = response_text.split("dataLayer.push(", 1)[1].split(");")[0]
        res_data = res_data.replace("'", '"')
        res_data = json.loads(res_data)
        return {
            **vendor_order_detail.to_dict(),
            "order_id": res_data["ecommerce"]["purchase"]["actionField"]["id"],
            "order_type": msgs.ORDER_TYPE_ORDO,
        }

    def get_shipping_options(self, response_dom):
        shipping_options = {}
        shipping_option_eles = response_dom.xpath(
            '//select[@name="ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ddlShippingMethod"]/option'
        )
        checkout_info = {}
        for shipping_option_ele in shipping_option_eles:
            _label = extract_text(shipping_option_ele)
            _val = shipping_option_ele.xpath("./@value").get()
            _selected = shipping_option_ele.xpath("./@selected").get()
            if _selected:
                checkout_info["default_shipping_method"] = _label
            shipping_options[_label] = _val
        checkout_info["shipping_options"] = {}

        return shipping_options, response_dom, checkout_info

    def get_shipping_option_detail(self, response_dom):
        review_data = {}

        SHIPPING_OPTIONS_DETAIL_XPATHS = [
            ("shipping", "//div[@id='ctl00_cphMainContentHarmony_divOrderSummaryShipping']/strong"),
            ("shipping_method", "//div[@id='ctl00_cphMainContentHarmony_divOrderSummaryShippingMethod']/strong"),
            (
                "shipping_address",
                "//section[contains(@class, 'order-details')]//section[contains(@class, 'half')]/"
                "div[@class='half'][1]//address//text()",
            ),
        ]

        for key, xpath in SHIPPING_OPTIONS_DETAIL_XPATHS:
            if key == "shipping_address":
                review_data[key] = "\n".join(
                    [item.strip() for item in response_dom.xpath(xpath).extract() if item.strip()]
                ).strip()
            else:
                review_data[key] = extract_text(response_dom.xpath(xpath))

        return review_data

    async def fetch_shipping_options(self, products: List[CartProduct]):
        await self.clear_cart()
        await self.add_products_to_cart(products)
        checkout_dom = await self.checkout(products)

        shipping_options, checkout_response, checkout_info = self.get_shipping_options(checkout_dom)
        for shipping_option_label, shipping_option_val in shipping_options.items():
            review_checkout_response = await self.review_checkout(checkout_response, shipping_option_label)

            review_data = self.get_shipping_option_detail(review_checkout_response)
            review_data["shipping_value"] = shipping_option_val
            checkout_info["shipping_options"][shipping_option_label] = review_data

        return checkout_info
