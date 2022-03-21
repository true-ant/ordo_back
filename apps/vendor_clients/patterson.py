import json
from decimal import Decimal
from typing import Optional, Union

from aiohttp import ClientResponse
from scrapy import Selector

from apps.vendor_clients import types
from apps.vendor_clients.base import BASE_HEADERS, BaseClient

PRE_LOGIN_HEADERS = {
    **BASE_HEADERS,
    "Upgrade-Insecure-Requests": "1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
}

LOGIN_HEADERS = {
    **BASE_HEADERS,
    "Cache-Control": "max-age=0",
    "Upgrade-Insecure-Requests": "1",
    "Origin": "https://pcsts.pattersoncompanies.com",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
}

LOGIN_HOOK_HEADER = {
    **BASE_HEADERS,
    "Cache-Control": "max-age=0",
    "Upgrade-Insecure-Requests": "1",
    "Origin": "https://pcsts.pattersoncompanies.com",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://pcsts.pattersoncompanies.com/",
}

LOGIN_HOOK_HEADER2 = {
    **BASE_HEADERS,
    "Cache-Control": "max-age=0",
    "Upgrade-Insecure-Requests": "1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
}

GET_CART_HEADERS = {
    **BASE_HEADERS,
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "If-Modified-Since": "Mon, 26 Jul 1997 05:00:00 GMT",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://www.pattersondental.com/ShoppingCart",
}

CLEAR_CART_HEADERS = {
    **BASE_HEADERS,
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://www.pattersondental.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://www.pattersondental.com/ShoppingCart",
}

ADD_PRODUCT_CART_HEADERS = {
    **BASE_HEADERS,
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://www.pattersondental.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://www.pattersondental.com/ShoppingCart",
}


class PattersonClient(BaseClient):
    VENDOR_SLUG = "patterson"
    GET_PRODUCT_PAGE_HEADERS = BASE_HEADERS

    async def get_login_data(self, *args, **kwargs) -> types.LoginInformation:
        params = {
            "returnUrl": "/",
            "signIn": "userSignIn",
        }
        async with self.session.get(
            url="https://www.pattersondental.com/Account", headers=PRE_LOGIN_HEADERS, params=params
        ) as resp:
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

    async def check_authenticated(self, resp: ClientResponse) -> bool:
        dom = Selector(text=await resp.text())
        return False if dom.xpath(".//div[@id='error']") else True

    async def after_login_hook(self, response: ClientResponse):
        response_dom = Selector(text=await response.text())
        data = {
            "wa": response_dom.xpath("//input[@name='wa']/@value").get(),
            "wresult": response_dom.xpath("//input[@name='wresult']/@value").get(),
            "wctx": response_dom.xpath("//input[@name='wctx']/@value").get(),
        }
        await self.session.post(url="https://www.pattersondental.com", headers=LOGIN_HOOK_HEADER, data=data)
        async with self.session.get(url="https://www.pattersondental.com", headers=LOGIN_HOOK_HEADER2) as resp:
            text = await resp.text()
            return text

    async def get_cart_page(self) -> Union[Selector, dict]:
        return await self.get_response_as_json(
            url="https://www.pattersondental.com/ShoppingCart/CartItemQuantities",
            headers=GET_CART_HEADERS,
        )

    async def clear_cart(self):
        products = await self.get_cart_page()
        data = []
        for product in products:
            data.append(
                {
                    "OrderItemId": product["OrderItemId"],
                    "ParentItemId": None,
                    "PublicItemNumber": product["PublicItemNumber"],
                    "PersistentItemNumber": "",
                    "ItemQuantity": product["ItemQuantity"],
                    "BasePrice": None,
                    "ItemPriceBreaks": None,
                    "UnitPriceOverride": None,
                    "IsLabelItem": False,
                    "IsTagItem": False,
                    "ItemDescription": "",
                    "UseMyCatalogQuantity": False,
                    "UnitPrice": product["UnitPrice"],
                    "ItemSubstitutionReasonModel": None,
                    "NavInkConfigurationId": None,
                    "CanBePersonalized": False,
                    "HasBeenPersonalized": False,
                    "Manufacturer": False,
                }
            )
        await self.session.post(
            url="https://www.pattersondental.com/ShoppingCart/RemoveItemsFromShoppingCart",
            headers=CLEAR_CART_HEADERS,
            json=data,
        )

    async def add_product_to_cart(self, product: types.CartProduct, *args, **kwargs):
        data = {
            "itemNumbers": product["product"]["product_id"],
            "loadItemType": "ShoppingCart",
        }
        await self.session.post(
            "https://www.pattersondental.com/Item/ValidateItems",
            headers=ADD_PRODUCT_CART_HEADERS,
            data=json.dumps(data),
        )
        data = [
            {
                "OrderItemId": None,
                "ParentItemId": None,
                "PublicItemNumber": product["product"]["product_id"],
                "PersistentItemNumber": None,
                "ItemQuantity": product["quantity"],
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
            headers=ADD_PRODUCT_CART_HEADERS,
            data=json.dumps(data),
        )

    def serialize(self, data: Union[dict, Selector]) -> Optional[types.Product]:
        product_detail = data.xpath("//input[@id='ItemSkuDetail']/@value").get()
        try:
            product_detail = json.loads(product_detail)
            product_id = product_detail["PublicItemNumber"]
            return {
                "product_id": product_id,
                "sku": product_id,
                "name": product_detail["ItemDescription"],
                "url": f"https://www.pattersondental.com/Supplies/ItemDetail/{product_id}",
                "images": [
                    f"https://content.pattersondental.com/items/LargeSquare/images/{image['AssetFilename']}"
                    for image in product_detail["Images"]
                ],
                "price": Decimal(str(product_detail["UnitPrice"])),
                "category": "",
                "unit": "",
            }
        except (TypeError, json.decoder.JSONDecodeError):
            pass

    async def checkout_and_review_order(self, shipping_method: Optional[str] = None) -> dict:
        pass
