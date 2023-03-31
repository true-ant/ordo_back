import asyncio
import datetime
import json
import logging
import re
import uuid
from decimal import Decimal
from typing import Dict, List, Optional
from urllib.parse import urlencode

from aiohttp import ClientResponse
from scrapy import Selector

from apps.common import messages as msgs
from apps.scrapers.base import Scraper
from apps.scrapers.headers.patterson import (
    ADD_CART_HEADERS,
    CLEAR_CART_HEADER,
    GET_CART_ITEMS_HEADER,
    HOME_HEADERS,
    LOGIN_HEADERS,
    LOGIN_HOOK_HEADER,
    LOGIN_HOOK_HEADER2,
    ORDER_HISTORY_HEADERS,
    ORDER_HISTORY_POST_HEADERS,
    PLACE_ORDER_HEADERS,
    PRE_LOGIN_HEADERS,
    SEARCH_HEADERS,
    SHIP_HEADERS,
    SHIP_PAYMENT_HEADERS,
    VALIDATE_CART_HEADERS,
)
from apps.scrapers.schema import Order, Product, VendorOrderDetail
from apps.scrapers.utils import semaphore_coroutine
from apps.types.orders import CartProduct
from apps.types.scraper import (
    InvoiceFormat,
    InvoiceType,
    LoginInformation,
    ProductSearch,
)
from apps.vendor_clients import errors

logger = logging.getLogger(__name__)


class PattersonScraper(Scraper):
    BASE_URL = "https://www.pattersondental.com"
    INVOICE_TYPE = InvoiceType.PDF_INVOICE
    INVOICE_FORMAT = InvoiceFormat.USE_VENDOR_FORMAT

    async def extract_content(self, ele):
        text = re.sub(r"\s+", " ", " ".join(ele.xpath(".//text()").extract()))
        return text.strip() if text else ""

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        async with self.session.get(url="https://www.pattersondental.com/", headers=HOME_HEADERS) as resp:
            params = {
                "returnUrl": "/",
                "signIn": "userSignIn",
            }
            async with self.session.get(
                url="https://www.pattersondental.com/Account", headers=PRE_LOGIN_HEADERS, params=params
            ) as resp:
                login_url = str(resp.url)
                text = await resp.text()
                settings_content = text.split("var SETTINGS")[1].split(";")[0].strip(" =")
                settings = json.loads(settings_content)
                csrf = settings.get("csrf", "")
                transId = settings.get("transId", "")
                policy = settings.get("hosts", {}).get("policy", "")
                diag = {"pageViewId": settings.get("pageViewId", ""), "pageId": "CombinedSigninAndSignup", "trace": []}

                headers = LOGIN_HEADERS.copy()
                headers["Referer"] = login_url
                headers["X-CSRF-TOKEN"] = csrf

                params = (
                    ("tx", transId),
                    ("p", policy),
                )
                url = (
                    "https://pattersonb2c.b2clogin.com/pattersonb2c.onmicrosoft.com/"
                    "B2C_1A_PRODUCTION_Dental_SignInWithPwReset/SelfAsserted?" + urlencode(params)
                )

                data = {
                    "signInName": self.username,
                    "password": self.password,
                    "request_type": "RESPONSE",
                    "diag": diag,
                    "login_page_link": login_url,
                    "transId": transId,
                    "csrf": csrf,
                    "policy": policy,
                }

                return {
                    "url": url,
                    "headers": headers,
                    "data": data,
                }

    async def check_authenticated(self, resp: ClientResponse) -> bool:
        text = await resp.text()
        dom = Selector(text=text)
        return True if dom.xpath("//a[@href='/Account/LogOff']") else False

    async def login(self, username: Optional[str] = None, password: Optional[str] = None):
        login_info = await self._get_login_data()
        logger.debug("Got logger data: %s", login_info)
        if login_info:
            async with self.session.post(
                url=login_info["url"], headers=login_info["headers"], data=login_info["data"]
            ) as resp:
                transId = login_info["data"]["transId"]
                policy = login_info["data"]["policy"]
                csrf = login_info["data"]["csrf"]
                diag = login_info["data"]["diag"]

                headers = LOGIN_HOOK_HEADER.copy()
                headers["Referer"] = login_info["data"]["login_page_link"]

                params = (
                    ("tx", transId),
                    ("p", policy),
                    ("rememberMe", "false"),
                    ("csrf_token", csrf),
                    ("diags", urlencode(diag)),
                )
                url = (
                    "https://pattersonb2c.b2clogin.com/pattersonb2c.onmicrosoft.com/"
                    "B2C_1A_PRODUCTION_Dental_SignInWithPwReset/api/CombinedSigninAndSignup/confirmed?"
                    + urlencode(params)
                )

                logger.debug("Logging in...")
                async with self.session.get(url, headers=headers) as resp:
                    print("Login Confirmed: ", resp.status)
                    text = await resp.text()
                    dom = Selector(text=text)
                    state = dom.xpath('//input[@name="state"]/@value').get()
                    code = dom.xpath('//input[@name="code"]/@value').get()
                    id_token = dom.xpath('//input[@name="id_token"]/@value').get()

                    headers = LOGIN_HOOK_HEADER2.copy()

                    data = {
                        "state": state,
                        "code": code,
                        "id_token": id_token,
                    }

                    async with self.session.post(
                        url="https://www.pattersondental.com/Account/LogOnPostProcessing/",
                        headers=headers,
                        data=data,
                    ) as resp:
                        async with self.session.get(
                            url="https://www.pattersondental.com/supplies/deals",
                            headers=HOME_HEADERS,
                            data=data,
                        ) as resp:
                            if resp.status != 200:
                                content = await resp.read()
                                logger.debug("Got %s status, content = %s", resp.status, content)
                                raise errors.VendorAuthenticationFailed()

                            is_authenticated = await self.check_authenticated(resp)
                            if not is_authenticated:
                                logger.debug("Still not authenticated")
                                raise errors.VendorAuthenticationFailed()

                            if hasattr(self, "after_login_hook"):
                                await self.after_login_hook(resp)

                            logger.info("Successfully logged in")

            return resp.cookies

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

    @semaphore_coroutine
    async def get_order(self, sem, order_dom, office=None, **kwargs):
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

            for i, order_product_dom in enumerate(
                order_detail_response.xpath('//div[contains(@class, "itemRecord")]')
            ):
                product_id = order_product_dom.xpath(
                    f".//input[@name='itemSkuDetails[{i}].PublicItemNumber']/@value"
                ).get()
                # product_name = self.extract_first(product_name_url_dom, ".//a/text()")
                product_url = self.extract_first(
                    order_product_dom, ".//div[contains(@class, 'orderHistoryOrderDetailItemText')]//@href"
                )
                if product_url:
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

                    account_id = kwargs.get("account_id")
                    order["invoice_link"] = (
                        "https://www.pattersondental.com/DocumentLibrary/Invoice"
                        f"?invoiceNumber={invoice_number}&customerNumber={account_id}"
                    )

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
                # "description",
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
        completed_order_ids: Optional[List[str]] = None,
    ) -> List[Order]:
        sem = asyncio.Semaphore(value=2)
        if perform_login:
            await self.login()

        url = "https://www.pattersondental.com/OrderHistory/Search"
        async with self.session.get(url, headers=ORDER_HISTORY_HEADERS) as resp:
            response_html = await resp.text()
            response_dom = Selector(text=response_html)
            verification_token = response_dom.xpath(
                '//form[@id="orderHistorySearchForm"]/input[@name="__RequestVerificationToken"]/@value'
            ).get()

        data_layer = json.loads(response_html.split("dataLayer =")[1].split(";")[0].strip())
        account_id = data_layer[0]["accountid"]

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
        else:
            search_data["FromDate"] = (datetime.datetime.now() - datetime.timedelta(days=2 * 365)).strftime("%m/%d/%Y")
            search_data["ToDate"] = datetime.datetime.today().strftime("%m/%d/%Y")

        async with self.session.post(
            url, headers=ORDER_HISTORY_POST_HEADERS, params=search_params, data=search_data
        ) as resp:
            response_dom = Selector(text=await resp.text())
            orders_dom = response_dom.xpath('.//table[@id="orderHistory"]/tbody/tr')
            tasks = (self.get_order(sem, order_dom, office, **{"account_id": account_id}) for order_dom in orders_dom)
            orders = await asyncio.gather(*tasks, return_exceptions=True)

        return [Order.from_dict(order) for order in orders if isinstance(order, dict)]

    async def get_product_as_dict(self, product_id, product_url, perform_login=False) -> dict:
        # if perform_login:
        #     await self.login()

        async with self.session.get(product_url) as resp:
            res = Selector(text=await resp.text())
            product_category_and_name = self.merge_strip_values(res, "//div[@class='catalogBreadcrumb']/span//text()")
            categories = product_category_and_name.split(":")
            product_name = categories[-1]
            product_images = res.xpath("//div[contains(@class, 'itemDetailCarousel')]//a/img/@src").extract()
            product_price = self.extract_first(res, ".//div[@class='priceText']//text()")
            product_price = self.remove_thousands_separator(self.extract_price(product_price))
            ret = {
                "product_id": product_id,
                "name": product_name,
                "url": product_url,
                "images": [{"image": product_image} for product_image in product_images],
                "category": categories[1],
                "price": product_price,
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

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0, sort_by="price", office_id=None
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
        products_dom = response_dom.xpath(
            "//div[@class='container-fluid']//table//tr//div[@ng-controller='SearchResultsController']"
        )
        if products_dom:
            try:
                total_size = int(
                    response_dom.xpath("//div[contains(@class, 'productItemFamilyListHeader')]//h1//text()")
                    .get()
                    .split("results", 1)[0]
                    .split("Found")[1]
                    .strip(" +")
                )
            except (IndexError, AttributeError, ValueError):
                total_size = 0

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
                product_image = self.extract_first(
                    product_dom, ".//div[contains(@class, 'listViewImageWrapper')]/img/@src"
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
        else:
            products_dom = response_dom.xpath(
                "//div[@id='productFamilyDetailsRow']//div[contains(@class, 'productFamilyGridBody')]"
            )
            total_size = len(products_dom)
            product_name = self.extract_first(response_dom, ".//div[@id='productFamilyDescriptionHeader']/h1//text()")

            for product_dom in products_dom:
                product_title = self.extract_first(
                    product_dom,
                    ".//div[@id='productFamilyDetailsGridBodyColumnOneInnerRowDescription']"
                    "//a[@class='itemTitleDescription']//text()",
                )
                product_url = self.BASE_URL + self.extract_first(
                    product_dom,
                    ".//div[@id='productFamilyDetailsGridBodyColumnOneInnerRowDescription']"
                    "//a[@class='itemTitleDescription']/@href",
                )
                product_id = self.extract_first(
                    product_dom, ".//div[@id='productFamilyDetailsGridBodyColumnTwoInnerRowItemNumber']/text()"
                )
                product_image = self.extract_first(
                    product_dom, ".//div[@id='productFamilyDetailsGridBodyColumnOneInnerRowImages']//img/@src"
                )
                product_price = self.extract_first(
                    product_dom, ".//div[contains(@class, 'productFamilyDetailsPriceBreak')]/text()"
                )
                product_price = self.extract_price(product_price)

                products.append(
                    {
                        "product_id": product_id,
                        "name": product_name + product_title,
                        "description": "",
                        "url": product_url,
                        "images": [{"image": product_image}],
                        "price": Decimal(product_price),
                        "vendor": self.vendor.to_dict(),
                        "category": "",
                    }
                )

        return {
            "vendor_slug": self.vendor.slug,
            "total_size": total_size,
            "page": page,
            "page_size": page_size,
            "products": [Product.from_dict(product) for product in products if isinstance(product, dict)],
            "last_page": page_size * page >= total_size,
        }

    async def get_cart_items(self):
        async with self.session.get(
            "https://www.pattersondental.com/ShoppingCart/CartItemQuantities", headers=GET_CART_ITEMS_HEADER
        ) as resp:
            return await resp.json()

    async def clear_cart(self):
        data = list()
        cart_items = await self.get_cart_items()
        for cart_item in cart_items:
            item = {
                "OrderItemId": cart_item["OrderItemId"],
                "ParentItemId": None,
                "PublicItemNumber": cart_item["PublicItemNumber"],
                "PersistentItemNumber": "",
                "ItemQuantity": cart_item["ItemQuantity"],
                "BasePrice": None,
                "ItemPriceBreaks": None,
                "UnitPriceOverride": None,
                "IsLabelItem": False,
                "IsTagItem": False,
                "ItemDescription": "",
                "UseMyCatalogQuantity": False,
                "UnitPrice": cart_item["UnitPrice"],
                "ItemSubstitutionReasonModel": None,
                "NavInkConfigurationId": None,
                "CanBePersonalized": False,
                "HasBeenPersonalized": False,
                "Manufacturer": False,
            }
            data.append(item)

        async with self.session.post(
            "https://www.pattersondental.com/ShoppingCart/RemoveItemsFromShoppingCart",
            headers=CLEAR_CART_HEADER,
            json=data,
        ) as resp:
            print("Clear Cart:", resp.status)

    async def add_to_cart(self, products):
        for product in products:
            product_id = product["product_id"]
            quantity = product["quantity"]
            data = {"itemNumbers": product_id, "loadItemType": "ShoppingCart"}
            await self.session.post(
                "https://www.pattersondental.com/Item/ValidateItems",
                headers=VALIDATE_CART_HEADERS,
                data=json.dumps(data),
            )

            data = [
                {
                    "OrderItemId": None,
                    "ParentItemId": None,
                    "PublicItemNumber": product_id,
                    "PersistentItemNumber": None,
                    "ItemQuantity": quantity,
                    "BasePrice": None,
                    "ItemPriceBreaks": None,
                    "UnitPriceOverride": None,
                    "IsLabelItem": False,
                    "IsTagItem": False,
                    "ItemDescription": None,
                    "UseMyCatalogQuantity": False,
                    "UnitPrice": 0,
                    "ItemSubstitutionReasonModel": None,
                    "NavInkConfigurationId": None,
                    "CanBePersonalized": False,
                    "HasBeenPersonalized": False,
                    "Manufacturer": False,
                }
            ]

            await self.session.post(
                "https://www.pattersondental.com/ShoppingCart/AddItemsToCart",
                headers=ADD_CART_HEADERS,
                data=json.dumps(data),
            )

    async def shipping_payment(self):
        response = await self.session.get(
            "https://www.pattersondental.com/Order/ShippingPayment", headers=SHIP_HEADERS
        )
        response_text = await response.text()
        response_dom = Selector(text=response_text)
        return response_dom

    async def review_checkout(self, response_dom):
        shipping_address = "\n".join(
            [
                await self.extract_content(it)
                for it in response_dom.xpath('//div[@class="shippingPayment__address"]/div[@class="columns"]/div')
            ]
        )
        print("Shipping Address:\n", shipping_address)

        __RequestVerificationToken = response_dom.xpath("//input[@name='__RequestVerificationToken']/@value").get()
        shippingMethod = response_dom.xpath("//input[@name='shippingMethod'][@checked='checked']/@value").get()
        SpecialInstructions = response_dom.xpath("//input[@name='SpecialInstructions']/@value").get()
        shippingAddressNumber = response_dom.xpath("//input[@name='shippingAddressNumber']/@value").get()
        paymentMethod = response_dom.xpath("//input[@name='paymentMethod'][@checked='checked']/@value").get()
        CardTypeId = response_dom.xpath("//select[@name='CardTypeId']/option[@selected='selected']/@value").get()
        CardNumber = response_dom.xpath("//input[@name='CardNumber']/@value").get()
        ExpirationMonth = response_dom.xpath(
            "//select[@name='ExpirationMonth']/option[@selected='selected']/@value"
        ).get()
        ExpirationYear = response_dom.xpath(
            "//select[@name='ExpirationYear']/option[@selected='selected']/@value"
        ).get()
        CardHolderName = response_dom.xpath("//input[@name='CardHolderName']/@value").get()
        StatementPostalCode = response_dom.xpath("//input[@name='StatementPostalCode']/@value").get()
        Token = response_dom.xpath("//input[@name='Token']/@value").get()
        poNumber = response_dom.xpath("//input[@name='poNumber']/@value").get()
        purchaseOrderRequired = response_dom.xpath("//input[@name='purchaseOrderRequired']/@value").get()
        isZeroOrderTotal = response_dom.xpath("//input[@name='isZeroOrderTotal']/@value").get()
        cardNumberLastFour = response_dom.xpath("//input[@name='cardNumberLastFour']/@value").get()
        encryptedCardNumber = response_dom.xpath("//input[@name='encryptedCardNumber']/@value").get()
        ShippingInfo = response_dom.xpath("//input[@name='ShippingInfo.DefaultCharges']/@value").get()
        UserIsTerritoryRep = response_dom.xpath("//input[@name='UserIsTerritoryRep']/@value").get()
        CustomerRefNumber = response_dom.xpath("//input[@name='CustomerRefNumber']/@value").get()
        shoppingCartButton = response_dom.xpath("//input[@name='shoppingCartButton']/@value").get()

        data = {
            "__RequestVerificationToken": __RequestVerificationToken,
            "shippingMethod": shippingMethod,
            "SpecialInstructions": SpecialInstructions,
            "shippingAddressNumber": shippingAddressNumber,
            "paymentMethod": paymentMethod,
            "CardTypeId": CardTypeId,
            "CardNumber": CardNumber,
            "ExpirationMonth": ExpirationMonth,
            "ExpirationYear": ExpirationYear,
            "CardHolderName": CardHolderName,
            "StatementPostalCode": StatementPostalCode,
            "Token": Token,
            "poNumber": poNumber,
            "purchaseOrderRequired": purchaseOrderRequired,
            "isZeroOrderTotal": isZeroOrderTotal,
            "cardNumberLastFour": cardNumberLastFour,
            "encryptedCardNumber": encryptedCardNumber,
            "ShippingInfo.DefaultCharges": ShippingInfo,
            "UserIsTerritoryRep": UserIsTerritoryRep,
            "CustomerRefNumber": CustomerRefNumber,
            "shoppingCartButton": shoppingCartButton,
        }

        async with self.session.post(
            "https://www.pattersondental.com/Order/ShippingPayment", headers=SHIP_PAYMENT_HEADERS, data=data
        ) as resp:
            if not resp.ok:
                raise ValueError("Review order POST API is failed somehow!")

            async with self.session.get("https://www.pattersondental.com/Order/ReviewOrder") as redirect_resp:
                if not redirect_resp.ok:
                    raise ValueError("Redirecting to review order is failed somehow!")
                print(f"{redirect_resp.url} --- {redirect_resp.status}")
                response_text = await redirect_resp.text()
                resp_dom = Selector(text=response_text)

            subtotal = await self.extract_content(
                resp_dom.xpath('//div[contains(@class, "OrderSummaryBackground")]/div[2]/div[2]')
            )
            print("--- subtotal:\n", subtotal.strip() if subtotal else "")

            shipping = await self.extract_content(
                resp_dom.xpath('//div[contains(@class, "OrderSummaryBackground")]/div[3]/div[2]')
            )
            print("--- shipping:\n", shipping.strip() if shipping else "")

            order_total = await self.extract_content(
                resp_dom.xpath('//div[contains(@class, "OrderSummaryBackground")]/following-sibling::div/div[2]')
            )
            print("--- order_total:\n", order_total.strip() if order_total else "")
            return resp_dom, subtotal, shipping, order_total, shipping_address

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        print("patterson/create_order")
        try:
            await asyncio.sleep(0.3)
            raise Exception()
            await self.login()
            await self.clear_cart()
            await self.add_to_cart(products)
            order_dom, subtotal, shipping, order_total, shipping_address = await self.checkout()
            vendor_order_detail = {
                "retail_amount": "",
                "savings_amount": "",
                "subtotal_amount": subtotal,
                "shipping_amount": shipping,
                "tax_amount": "",
                "total_amount": order_total,
                "reduction_amount": order_total,
                "payment_method": "",
                "shipping_address": shipping_address,
            }
        except Exception:
            print("patterson/create_order except")
            subtotal_manual = sum([prod["price"] * prod["quantity"] for prod in products])
            vendor_order_detail = {
                "retail_amount": "",
                "savings_amount": "",
                "subtotal_amount": Decimal(subtotal_manual),
                "shipping_amount": 0,
                "tax_amount": "",
                "total_amount": Decimal(subtotal_manual),
                "reduction_amount": Decimal(subtotal_manual),
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

    async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False, redundancy=False):
        print("patterson/confirm_order")
        try:
            await self.clear_cart()
            await self.add_to_cart(products)
            shipping_payment_dom = await self.shipping_payment()
            resp_dom, subtotal, shipping, order_total, shipping_address = await self.review_checkout(
                shipping_payment_dom
            )

            if fake:
                vendor_order_detail = {
                    "retail_amount": "",
                    "savings_amount": "",
                    "subtotal_amount": subtotal,
                    "shipping_amount": shipping,
                    "tax_amount": "",
                    "total_amount": order_total,
                    "payment_method": "",
                    "shipping_address": shipping_address,
                    "order_id": f"{uuid.uuid4()}",
                    "order_type": msgs.ORDER_TYPE_ORDO,
                }
                return {
                    **vendor_order_detail,
                    **self.vendor.to_dict(),
                }
            data = {
                "__RequestVerificationToken": resp_dom.xpath(
                    "//input[@name='__RequestVerificationToken']/@value"
                ).get(),
                "SpecialInstructions": "",
                "CustomerPurchaseOrder": "",
                "PaymentMethodId": resp_dom.xpath("//input[@name='PaymentMethodId']/@value").get(),
                "PlaceOrderButton": "Place+Order",
            }

            await self.session.post(
                "https://www.pattersondental.com/Order/ReviewOrder", headers=PLACE_ORDER_HEADERS, data=data
            )
            vendor_order_detail = {
                "retail_amount": "",
                "savings_amount": "",
                "subtotal_amount": subtotal,
                "shipping_amount": shipping,
                "tax_amount": "",
                "total_amount": order_total,
                "payment_method": "",
                "shipping_address": shipping_address,
                "order_id": "invalid",
                "order_type": msgs.ORDER_TYPE_ORDO,
            }
            return {
                **vendor_order_detail,
                **self.vendor.to_dict(),
            }
        except Exception as e:
            print(f"patterson/confirm_order except {e}")
            subtotal_manual = sum([prod["price"] * prod["quantity"] for prod in products])
            vendor_order_detail = {
                "retail_amount": "",
                "savings_amount": "",
                "subtotal_amount": Decimal(subtotal_manual),
                "shipping_amount": 0,
                "tax_amount": "",
                "total_amount": Decimal(subtotal_manual),
                "reduction_amount": Decimal(subtotal_manual),
                "payment_method": "",
                "shipping_address": "",
                "order_id": f"{uuid.uuid4()}",
                "order_type": msgs.ORDER_TYPE_REDUNDANCY,
            }
            return {
                **vendor_order_detail,
                **self.vendor.to_dict(),
            }
