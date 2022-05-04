import asyncio
import datetime
import logging
import re
from collections import defaultdict
from http.cookies import SimpleCookie
from typing import Dict, List, Optional, Tuple

from aiohttp import ClientResponse, ClientSession
from asgiref.sync import sync_to_async
from django.db.models import F
from month import Month
from scrapy import Selector
from slugify import slugify

from apps.scrapers.errors import VendorAuthenticationFailed
from apps.scrapers.schema import Order, Product, ProductCategory, VendorOrderDetail
from apps.scrapers.utils import catch_network, semaphore_coroutine
from apps.types.orders import CartProduct, VendorCartProduct
from apps.types.scraper import (
    InvoiceFile,
    LoginInformation,
    ProductSearch,
    SmartProductID,
)

logger = logging.getLogger(__name__)


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
        self.objs = {"product_categories": defaultdict(dict)}

    @staticmethod
    def extract_first(dom, xpath):
        return x.strip() if (x := dom.xpath(xpath).extract_first()) else x

    @staticmethod
    def extract_string_only(s):
        return re.sub(r"\s+", " ", s).strip()

    @staticmethod
    def extract_amount(s):
        return re.search(r"[,\d]+.?\d*", s).group(0)

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

    @staticmethod
    def normalize_order_status(order_status):
        order_status = order_status.lower()
        if any(
            status in order_status
            for status in ("delivered", "shipped", "complete", "order shipped", "cancelled", "closed")
        ):
            return "closed"
        elif any([status in order_status for status in ("open", "in progress", "processing", "pending")]):
            return "open"
        else:
            return order_status

    @staticmethod
    def normalize_order_product_status(order_product_status):
        order_product_status = order_product_status.lower()

        if any(status in order_product_status for status in ("processing", "pending", "open")):
            return "processing"
        elif any([status in order_product_status for status in ("backordered",)]):
            return "backordered"
        elif any([status in order_product_status for status in ("returned",)]):
            return "returned"
        elif any([status in order_product_status for status in ("cancelled",)]):
            return "cancelled"
        elif any([status in order_product_status for status in ("received", "complete", "shipped")]):
            return "received"
        else:
            return order_product_status

    @staticmethod
    def normalize_product_status(product_status):
        product_status = product_status.lower()
        return product_status

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
        completed_order_ids: Optional[List[str]] = None,
    ) -> List[Order]:
        raise NotImplementedError()

    async def get_product_as_dict(self, product_id, product_url, perform_login=False) -> dict:
        raise NotImplementedError()

    async def get_product(self, product_id, product_url, perform_login=False, semaphore=None) -> Product:
        product = await self.get_product_as_dict(product_id, product_url, perform_login)
        return Product.from_dict(product)

    async def get_product_v2(
        self, product_id, product_url, perform_login=False, semaphore=None, queue: asyncio.Queue = None
    ) -> Optional[Product]:
        if semaphore:
            await semaphore.acquire()

        product = await self.get_product_as_dict(product_id, product_url, perform_login)
        product = Product.from_dict(product)
        if queue:
            await queue.put(product)

        await asyncio.sleep(3)
        if semaphore:
            semaphore.release()

        return product

    @semaphore_coroutine
    async def get_missing_product_fields(self, sem, product_id, product_url, perform_login=False, fields=None) -> dict:
        product = await self.get_product_as_dict(product_id, product_url, perform_login)

        if fields and isinstance(fields, tuple):
            return {k: v for k, v in product.items() if k in fields}

    async def download_invoice(self, invoice_link, order_id) -> InvoiceFile:
        await self.login()
        async with self.session.get(invoice_link) as resp:
            return await resp.content.read()

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

    def save_single_product_to_db(self, product_data, office=None, is_inventory=False, keyword=None, order_date=None):
        """save product to product table"""
        from django.db import transaction
        from django.db.models import Q

        from apps.orders.models import OfficeProduct as OfficeProductModel
        from apps.orders.models import (
            OfficeProductCategory as OfficeProductCategoryModel,
        )
        from apps.orders.models import Product as ProductModel
        from apps.orders.models import ProductCategory as ProductCategoryModel
        from apps.orders.models import ProductImage as ProductImageModel

        other_category = self.objs["product_categories"].get("other_category", None)
        if other_category is None:
            other_category = ProductCategoryModel.objects.filter(slug="other").first()
            self.objs["product_categories"]["other_category"] = other_category

        vendor_data = product_data.pop("vendor")
        product_images = product_data.pop("images", [])
        product_id = product_data.pop("product_id")
        product_category_hierarchy = product_data.pop("category")

        if product_category_hierarchy:
            product_root_category = slugify(product_category_hierarchy[0])
            product_category = self.objs["product_categories"].get(product_root_category, None)
            if product_category is None:
                q = {f"vendor_categories__{vendor_data['slug']}__contains": product_root_category}
                q = Q(**q)
                product_category = ProductCategoryModel.objects.filter(q).first()
                self.objs["product_categories"][product_root_category] = product_category
        else:
            product_category = None

        product_data["category"] = product_category or other_category
        product_price = product_data.pop("price")
        with transaction.atomic():
            product, created = ProductModel.objects.get_or_create(
                vendor=self.vendor,
                product_id=product_id,
                defaults=product_data,
            )
            if keyword:
                product.tags.add(keyword)

            if created:
                product_images = [
                    ProductImageModel(
                        product=product,
                        image=product_image["image"],
                    )
                    for product_image in product_images
                ]
                ProductImageModel.objects.bulk_create(product_images)

            if office:
                office_product_category_slug = product_data["category"].slug
                office_product_category = (
                    self.objs["product_categories"].get(office, {}).get(office_product_category_slug)
                )
                if office_product_category is None:
                    office_product_category = OfficeProductCategoryModel.objects.filter(
                        office=office, slug=office_product_category_slug
                    ).first()
                    self.objs["product_categories"][office][office_product_category_slug] = office_product_category

                try:
                    office_product = OfficeProductModel.objects.get(
                        office=office,
                        product=product,
                    )
                    office_product.price = product_price
                    office_product.office_product_category = office_product_category
                    if is_inventory:
                        office_product.is_inventory = is_inventory

                    if order_date:
                        if office_product.last_order_date is None or office_product.last_order_date < order_date:
                            office_product.last_order_date = order_date
                            office_product.last_order_price = product_price

                    office_product.save()
                except OfficeProductModel.DoesNotExist:
                    office_product = OfficeProductModel.objects.create(
                        office=office,
                        product=product,
                        is_inventory=is_inventory,
                        price=product_price,
                        office_product_category=office_product_category,
                        last_order_date=order_date,
                        last_order_price=product_price,
                    )
                    if product.parent:
                        OfficeProductModel.objects.get_or_create(
                            office=office,
                            product=product.parent,
                            is_inventory=is_inventory,
                            office_product_category=office_product_category,
                        )
            else:
                office_product = None

        return product, office_product

    @sync_to_async
    def save_order_to_db(self, office, order: Order):
        from django.db import transaction

        from apps.orders.models import Order as OrderModel
        from apps.orders.models import VendorOrder as VendorOrderModel
        from apps.orders.models import VendorOrderProduct as VendorOrderProductModel

        order_data = order.to_dict()
        order_data.pop("shipping_address")
        order_products_data = order_data.pop("products")
        order_id = order_data["order_id"]
        order_data["vendor_status"] = order_data["status"]
        order_data["status"] = self.normalize_order_status(order_data["vendor_status"])
        order_date = order_data["order_date"]
        with transaction.atomic():
            try:
                if self.vendor.slug == "henry_schein":
                    vendor_order = VendorOrderModel.objects.get(
                        vendor=self.vendor, vendor_order_reference=order_data["vendor_order_reference"]
                    )
                    if order_data["vendor_order_reference"] != order_id:
                        vendor_order.vendor_order_id = order_id
                        vendor_order.save()
                else:
                    vendor_order = VendorOrderModel.objects.get(vendor=self.vendor, vendor_order_id=order_id)
            except VendorOrderModel.DoesNotExist:
                order = OrderModel.objects.create(
                    office=office,
                    status=order_data["status"],
                    order_date=order_date,
                    total_items=order_data["total_items"],
                    total_amount=order_data["total_amount"],
                )
                vendor_order = VendorOrderModel.from_dataclass(vendor=self.vendor, order=order, dict_data=order_data)

                month = Month(year=order_date.year, month=order_date.month)
                office_budget = office.budgets.filter(month=month).first()
                if office_budget:
                    office_budget.dental_spend = F("dental_spend") + order_data["total_amount"]
                    office_budget.save()
                else:
                    office_budget = office.budgets.filter(month__gte=month).order_by("month").first()
                    office_budget.id = None
                    office_budget.month = month
                    office_budget.dental_spend = order_data["total_amount"]
                    office_budget.office_spend = 0
                    office_budget.miscellaneous_spend = 0
                    office_budget.save()

            for order_product_data in order_products_data:
                product_data = order_product_data.pop("product")
                product, _ = self.save_single_product_to_db(
                    product_data, office, is_inventory=True, order_date=order_date
                )
                order_product_data["vendor_status"] = order_product_data["status"]
                order_product_data["status"] = self.normalize_order_product_status(order_product_data["vendor_status"])

                VendorOrderProductModel.objects.update_or_create(
                    vendor_order=vendor_order,
                    product=product,
                    defaults=order_product_data,
                )

    async def get_missing_products_fields(self, order_products, fields=("description",)):
        sem = asyncio.Semaphore(value=2)
        tasks = (
            self.get_missing_product_fields(
                sem,
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
            if not isinstance(product_missing_data, dict):
                continue

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
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0, sort_by="price", office_id=None
    ) -> ProductSearch:
        pass

    @catch_network
    async def search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0, sort_by="price"
    ) -> ProductSearch:
        res_products = []
        page_size = 0

        if self.vendor.slug not in ["ultradent", "amazon"]:
            await self.login()

        while True:
            product_search = await self._search_products(
                query, page, min_price=min_price, max_price=max_price, sort_by=sort_by
            )
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

    @sync_to_async
    def get_page_queryset(self, query, page, page_size, office_id=None):
        from apps.orders.models import OfficeProduct

        products = OfficeProduct.objects.all()
        if office_id:
            products = products.filter(office_id=office_id)

        products = products.filter(product__vendor_id=self.vendor.id, product__name__icontains=query)
        total_size = products.count()
        if (page - 1) * page_size < total_size:
            page_products = products[(page - 1) * page_size : page * page_size]
            page_products = [product.to_dataclass() for product in page_products]
        else:
            page_products = []

        return total_size, page_products

    async def _search_products_from_table(
        self,
        query: str,
        page: int = 1,
        min_price: int = 0,
        max_price: int = 0,
        sort_by="price",
        office_id=None,
    ) -> ProductSearch:
        page_size = 15
        total_size, page_products = await self.get_page_queryset(query, page, page_size, office_id)
        last_page = page_size * page >= total_size
        return {
            "vendor_slug": self.vendor.slug,
            "total_size": total_size,
            "page": page,
            "page_size": page_size,
            "products": page_products,
            "last_page": last_page,
        }

    @catch_network
    async def search_products_v2(self, keyword, office=None):
        if self.vendor.slug == "ultradent":
            return

        await self.login()

        page = 1
        products_objs = []
        fetch_all = False
        while True:
            product_search = await self._search_products(keyword.keyword, page)
            last_page = product_search["last_page"]
            products = product_search["products"]

            for product in products:
                product_obj, _ = await sync_to_async(self.save_single_product_to_db)(
                    product.to_dict(), office=office, keyword=keyword
                )
                products_objs.append(product_obj)

            if not fetch_all or (fetch_all and last_page):
                break

            page += 1

        return products_objs

    async def track_product(self, order_id, product_id, tracking_link, tracking_number, perform_login=False):
        raise NotImplementedError("Vendor scraper must implement `track_product`")

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

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        raise NotImplementedError("Vendor scraper must implement `create_order`")

    # async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False):
    #     raise NotImplementedError("Vendor scraper must implement `confirm_order`")
