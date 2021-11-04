import asyncio
import datetime
import re
from http.cookies import SimpleCookie
from typing import Dict, List, Optional, Tuple

from aiohttp import ClientResponse, ClientSession
from asgiref.sync import sync_to_async
from scrapy import Selector
from slugify import slugify

from apps.scrapers.errors import VendorAuthenticationFailed
from apps.scrapers.schema import Order, Product, ProductCategory, VendorOrderDetail
from apps.scrapers.utils import catch_network
from apps.types.orders import CartProduct, VendorCartProduct
from apps.types.scraper import (
    InvoiceFile,
    LoginInformation,
    ProductSearch,
    SmartProductID,
)


class Scraper:
    def __init__(
        self,
        session: ClientSession,
        vendor,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.session = session
        self.vendor = vendor
        self.username = username
        self.password = password
        self.orders = {}

    @staticmethod
    def extract_first(dom, xpath):
        return x.strip() if (x := dom.xpath(xpath).extract_first()) else x

    @staticmethod
    def merge_strip_values(dom, xpath, delimeter=""):
        return delimeter.join(filter(None, map(str.strip, dom.xpath(xpath).extract())))

    @staticmethod
    def remove_thousands_separator(value):
        try:
            value = value.strip(" $")
            value = value.replace(" ", "")
            value = value.replace(",", "")
            return value
        except AttributeError:
            return "0"

    @staticmethod
    def get_category_slug(value) -> Optional[str]:
        try:
            return value.split("/")[-1]
        except (AttributeError, IndexError):
            pass

    @staticmethod
    def extract_price(value):
        prices = re.findall("\\d+\\.\\d+", value)
        return prices[0] if prices else None

    async def _get_check_login_state(self) -> Tuple[bool, dict]:
        return False, {}

    @catch_network
    async def login(self, username: Optional[str] = None, password: Optional[str] = None) -> SimpleCookie:
        if username:
            self.username = username
        if password:
            self.password = password

        is_already_login, kwargs = await self._get_check_login_state()
        if not is_already_login:
            login_info = await self._get_login_data(**kwargs)
            async with self.session.post(
                login_info["url"], headers=login_info["headers"], data=login_info["data"]
            ) as resp:
                if resp.status != 200:
                    raise VendorAuthenticationFailed()

                is_authenticated = await self._check_authenticated(resp)
                if not is_authenticated:
                    raise VendorAuthenticationFailed()

                await self._after_login_hook(resp)

            return resp.cookies

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        return True

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        pass

    async def _after_login_hook(self, response: ClientResponse):
        pass

    def _get_vendor_categories(self, response) -> List[ProductCategory]:
        pass

    async def get_orders(
        self,
        office=None,
        perform_login=False,
        from_date: Optional[datetime.date] = None,
        to_date: Optional[datetime.date] = None,
    ) -> List[Order]:
        raise NotImplementedError()

    async def get_product_as_dict(self, product_id, product_url, perform_login=False) -> dict:
        raise NotImplementedError()

    async def get_product(self, product_id, product_url, perform_login=False) -> Product:
        product = await self.get_product_as_dict(product_id, product_url, perform_login)
        return Product.from_dict(product)

    async def get_missing_product_fields(self, product_id, product_url, perform_login=False, fields=None) -> dict:
        product = await self.get_product_as_dict(product_id, product_url, perform_login)

        if fields and isinstance(fields, tuple):
            return {k: v for k, v in product.items() if k in fields}

    async def download_invoice(self, invoice_link) -> InvoiceFile:
        raise NotImplementedError("download_invoice must be implemented by the individual scraper")

    @staticmethod
    async def run_command(cmd, data=None):
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await proc.communicate(data)
            return stdout
        except Exception as e:
            raise e

    async def html2pdf(self, data: bytes):
        return await self.run_command(cmd="htmldoc --quiet -t pdf --webpage -", data=data)

    @sync_to_async
    def save_order_to_db(self, office, order: Order):
        from django.db import transaction
        from django.db.models import Q

        from apps.orders.models import (
            InventoryProduct,
            Order,
            Product,
            ProductCategory,
            ProductImage,
            VendorOrder,
            VendorOrderProduct,
        )

        order_data = order.to_dict()
        order_data.pop("shipping_address")
        order_products_data = order_data.pop("products")
        order_id = order_data["order_id"]
        with transaction.atomic():
            try:
                vendor_order = VendorOrder.objects.get(vendor=self.vendor, vendor_order_id=order_id)
            except VendorOrder.DoesNotExist:
                order = Order.objects.create(
                    office=office,
                    status=order_data["status"],
                    order_date=order_data["order_date"],
                    total_items=order_data["total_items"],
                    total_amount=order_data["total_amount"],
                )
                vendor_order = VendorOrder.from_dataclass(vendor=self.vendor, order=order, dict_data=order_data)

            other_category = ProductCategory.objects.filter(slug="other").first()

            for order_product_data in order_products_data:
                vendor_data = order_product_data["product"].pop("vendor")
                order_product_images = order_product_data["product"].pop("images", [])
                product_id = order_product_data["product"].pop("product_id")
                product_category = order_product_data["product"].pop("category")

                if product_category:
                    product_category = slugify(product_category[0])
                    q = {f"vendor_categories__{vendor_data['slug']}__contains": product_category}
                    q = Q(**q)
                    product_category = ProductCategory.objects.filter(q).first()
                    if product_category:
                        order_product_data["product"]["category_id"] = product_category.id
                    else:
                        order_product_data["product"]["category_id"] = other_category.id
                else:
                    order_product_data["product"]["category_id"] = other_category.id

                product, created = Product.objects.get_or_create(
                    vendor=self.vendor, product_id=product_id, defaults=order_product_data["product"]
                )
                if created:
                    for order_product_image in order_product_images:
                        ProductImage.objects.create(
                            product=product,
                            image=order_product_image["image"],
                        )

                VendorOrderProduct.objects.get_or_create(
                    vendor_order=vendor_order,
                    product=product,
                    defaults={
                        "quantity": order_product_data["quantity"],
                        "unit_price": order_product_data["unit_price"],
                        "status": order_product_data["status"],
                    },
                )

                order_product_data["product"].pop("price")
                InventoryProduct.objects.get_or_create(
                    office=office,
                    vendor=self.vendor,
                    product_id=product_id,
                    defaults=order_product_data["product"],
                )

    async def get_missing_products_fields(self, order_products, fields=("description",)):
        tasks = (
            self.get_missing_product_fields(
                product_id=order_product["product"]["product_id"],
                product_url=order_product["product"]["url"],
                perform_login=False,
                fields=fields,
            )
            for order_product in order_products
            if order_product["product"]["url"]
        )
        products_missing_data = await asyncio.gather(*tasks, return_exceptions=True)
        for order_product, product_missing_data in zip(order_products, products_missing_data):
            for field in fields:
                order_product["product"][field] = product_missing_data[field]

    async def get_vendor_categories(self, url=None, headers=None, perform_login=False) -> List[ProductCategory]:
        if perform_login:
            await self.login()

        url = self.CATEGORY_URL if hasattr(self, "CATEGORY_URL") else url
        if not url:
            raise ValueError

        headers = self.CATEGORY_HEADERS if hasattr(self, "CATEGORY_HEADERS") else headers

        ssl_context = self._ssl_context if hasattr(self, "_ssl_context") else None
        async with self.session.get(url, headers=headers, ssl=ssl_context) as resp:
            if resp.content_type == "application/json":
                response = await resp.json()
            else:
                response = Selector(text=await resp.text())
            return self._get_vendor_categories(response)

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        pass

    @catch_network
    async def search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        res_products = []
        page_size = 0

        if self.vendor.slug != "ultradent":
            await self.login()

        while True:
            product_search = await self._search_products(query, page, min_price=min_price, max_price=max_price)
            if not page_size:
                page_size = product_search["page_size"]

            total_size = product_search["total_size"]
            products = product_search["products"]
            last_page = product_search["last_page"]
            if max_price:
                products = [product for product in products if product.price and product.price < max_price]
            if min_price:
                products = [product for product in products if product.price and product.price > min_price]

            res_products.extend(products)

            if len(res_products) > 10 or last_page:
                break
            page += 1

        return {
            "vendor_slug": self.vendor.slug,
            "total_size": total_size,
            "page": page,
            "page_size": page_size,
            "products": res_products,
            "last_page": last_page,
        }

    async def add_product_to_cart(self, product: CartProduct, perform_login=False) -> VendorCartProduct:
        raise NotImplementedError("Vendor scraper must implement `add_product_to_cart`")

    async def add_products_to_cart(self, products: List[CartProduct]) -> List[VendorCartProduct]:
        raise NotImplementedError("Vendor scraper must implement `add_products_to_cart`")

    async def remove_product_from_cart(
        self, product_id: SmartProductID, perform_login: bool = False, use_bulk: bool = True
    ):
        raise NotImplementedError("Vendor scraper must implement `remove_product_from_cart`")

    async def remove_products_from_cart(self, product_ids: List[SmartProductID]):
        tasks = (self.remove_product_from_cart(product_id, use_bulk=False) for product_id in product_ids)
        await asyncio.gather(*tasks)

    async def clear_cart(self):
        raise NotImplementedError("Vendor scraper must implement `clear_cart`")

    async def create_order(self, products: List[CartProduct]) -> Dict[str, VendorOrderDetail]:
        raise NotImplementedError("Vendor scraper must implement `create_order`")

    async def confirm_order(self, products: List[CartProduct], fake=False):
        raise NotImplementedError("Vendor scraper must implement `confirm_order`")
