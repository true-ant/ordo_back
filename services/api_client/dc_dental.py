import asyncio
import json
import logging
import os
from typing import List
from urllib.parse import urlencode

import oauthlib.oauth1
from aiohttp.client import ClientSession

from services.api_client.vendor_api_types import DCDentalProduct
from services.utils.secrets import get_secret_value

logger = logging.getLogger(__name__)


class DCDentalOauth:
    def __init__(self):
        self.NETSUITE_ACCOUNT_ID = "1075085_SB1"
        self.BASE_URL = "https://1075085-sb1.restlets.api.netsuite.com/app/site/hosting/restlet.nl"
        self.SAFE_CHARS = "~()*!.'"
        self.client = oauthlib.oauth1.Client(
            client_key=os.getenv("DCDENTAL_CONSUMER_KEY"),
            client_secret=get_secret_value("DCDENTAL_CONSUMER_SECRET"),
            resource_owner_key=os.getenv("DCDENTAL_TOKEN_ID"),
            resource_owner_secret=get_secret_value("DCDENTAL_TOKEN_SECRET"),
            signature_method="HMAC-SHA256",
        )

    def sign(self, params, http_method, headers):
        uri = f"{self.BASE_URL}?{urlencode(params)}"
        url, headers, body = self.client.sign(
            uri=uri, http_method=http_method, realm=self.NETSUITE_ACCOUNT_ID, headers=headers
        )
        return url, headers, body


class DCDentalAPIClient:
    def __init__(self, session: ClientSession):
        self.session = session
        self.page_size = 1000
        self.oauthclient = DCDentalOauth()
        self.headers = {"Content-Type": "application/json"}

    async def get_product_list(self, page_number: int = 1, page_size: int = 1000):
        http_method = "GET"
        params = {
            "script": "customscript_pri_rest_product",
            "deploy": "customdeploy_pri_rest_product_ordo4837",
            "page": page_number,
            "pagesize": page_size,
        }
        url, headers, body = self.oauthclient.sign(params=params, http_method=http_method, headers=self.headers)
        async with self.session.get(url, headers=headers) as resp:
            if resp.status == 200:
                result = await resp.json()
                if result["success"]:
                    return result["result"]

    async def get_customer(self, email: str):
        http_method = "GET"
        params = {
            "script": "customscript_pri_rest_customer",
            "deploy": "customdeploy_pri_rest_customer_ordo4837",
            "email": email,
        }
        url, headers, body = self.oauthclient.sign(params=params, http_method=http_method, headers=self.headers)
        async with self.session.get(url, headers=headers) as resp:
            if resp.status == 200:
                result = await resp.json()
                if result["success"]:
                    return result["result"]

    async def get_customer_address(self, customer_id):
        http_method = "GET"
        params = {
            "script": "customscript_pri_rest_customer_address",
            "deploy": "customdeploy_pri_rest_cust_add_ordo4837",
            "customerid": customer_id,
        }
        url, headers, body = self.oauthclient.sign(params=params, http_method=http_method, headers=self.headers)
        async with self.session.get(url, headers=headers) as resp:
            if resp.status == 200:
                result = await resp.json()
                if result["success"]:
                    return result["result"]

    async def get_page_products(self, page_number: int = 1) -> List[DCDentalProduct]:
        products = await self.get_product_list(page_number, self.page_size)
        if products:
            return [DCDentalProduct.from_dict(product) for product in products]

    async def get_products(self) -> List[DCDentalProduct]:
        products: List[DCDentalProduct] = []
        start_page = 1
        while True:
            end_page = start_page + 10
            tasks = (self.get_page_products(page) for page in range(start_page, end_page))
            results = await asyncio.gather(*tasks)
            for result in results:
                if result is None:
                    continue
                products.extend(result)
            if len(products) < self.page_size * (end_page - 1):
                break
            start_page = end_page
        return products

    async def create_order_request(self, order_info):
        http_method = "POST"
        params = {
            "script": "customscript_pri_rest_salesorder",
            "deploy": "customdeploy_pri_rest_salesord_ordo4837",
        }
        order_info = json.dumps(order_info)
        url, headers, body = self.oauthclient.sign(params=params, http_method=http_method, headers=self.headers)
        async with self.session.post(url, headers=headers, data=order_info) as resp:
            if resp.status == 200:
                result = await resp.json()
                if result["success"]:
                    return result["result"]


async def main():
    async with ClientSession() as session:
        api_client = DCDentalAPIClient(session)
        cusomters = await api_client.get_customer()
        print(cusomters)
        # return await api_client.get_products()


if __name__ == "__main__":
    asyncio.run(main())
