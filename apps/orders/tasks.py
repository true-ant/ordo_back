import asyncio
import datetime

from aiohttp import ClientSession
from celery import shared_task
from django.db.models import Q
from django.utils import timezone
from slugify import slugify

from apps.accounts.models import OfficeVendor
from apps.orders.models import Keyword as KeywordModel
from apps.orders.models import OfficeCheckoutStatus
from apps.orders.models import Product as ProductModel
from apps.orders.models import ProductCategory
from apps.orders.models import ProductImage as ProductImageModel
from apps.scrapers.schema import Product as ProductDataClass
from apps.scrapers.scraper_factory import ScraperFactory


@shared_task
def update_office_cart_status():
    ten_minutes_ago = timezone.now() - datetime.timedelta(minutes=10)
    objs = OfficeCheckoutStatus.objects.filter(
        checkout_status=OfficeCheckoutStatus.CHECKOUT_STATUS.IN_PROGRESS,
        order_status=OfficeCheckoutStatus.ORDER_STATUS.COMPLETE,
        updated_at__lt=ten_minutes_ago,
    )
    total_count = objs.count()
    batch_size = 100
    for i in range(0, total_count, batch_size):
        batch_objs = objs[i * batch_size : min((i + 1) * batch_size, total_count)]
        for obj in batch_objs:
            obj.checkout_status = OfficeCheckoutStatus.CHECKOUT_STATUS.COMPLETE
        OfficeCheckoutStatus.objects.bulk_update(batch_objs, ["checkout_status"])


async def get_product_detail(product_id, product_url, office_vendor, vendor) -> ProductDataClass:
    async with ClientSession() as session:
        scraper = ScraperFactory.create_scraper(
            vendor=vendor,
            session=session,
            username=office_vendor.username,
            password=office_vendor.password,
        )
        return await scraper.get_product(product_id, product_url, perform_login=True)


@shared_task
def update_product_detail(product_id, product_url, office_id, vendor_id):
    try:
        office_vendor = OfficeVendor.objects.get(office_id=office_id, vendor_id=vendor_id)
    except OfficeVendor.DoesNotExist:
        return

    vendor = office_vendor.vendor

    if ProductModel.objects.filter(vendor=vendor, product_id=product_id, category__isnull=False).exists():
        return

    # get product detail
    product_data = asyncio.run(get_product_detail(product_id, product_url, office_vendor, vendor))

    product_data = product_data.to_dict()
    product_data.pop("product_id", None)
    product_images = product_data.pop("images", [])
    product_category = product_data.pop("category", None)

    # find product category
    if product_category:
        product_category_slug = slugify(product_category[0])
        q = {f"vendor_categories__{vendor.slug}__contains": product_category_slug}
        q = Q(**q)
        product_category = ProductCategory.objects.filter(q).first()

    if not product_category:
        product_category = ProductCategory.objects.filter(slug="other").first()

    product_data["category"] = product_category
    try:
        product = ProductModel.objects.get(vendor=vendor, product_id=product_id)
        product.name = product_data.get("name")
        product.description = product_data.get("description")
        product.url = product_data.get("url")
        product.price = product_data.get("price")
        product.category = product_category
        product.product_unit = product_data.get("product_unit")
        product.save()
    except ProductModel.DoesNotExist:
        product = ProductModel.objects.create(
            vendor=vendor,
            product_id=product_id,
            name=product_data.get("name"),
            description=product_data.get("description"),
            url=product_data.get("url"),
            price=product_data.get("price"),
            category=product_category,
            product_unit=product_data.get("product_unit"),
        )

    # product, _ = ProductModel.objects.get_or_create(
    #     vendor=vendor, product_id=product_id, defaults=product_data
    # )
    for product_image in product_images:
        ProductImageModel.objects.create(
            product=product,
            image=product_image["image"],
        )


async def _search_products(keyword, office_vendors):
    async with ClientSession() as session:
        tasks = []
        for office_vendor in office_vendors:
            scraper = ScraperFactory.create_scraper(
                vendor=office_vendor.vendor,
                session=session,
                username=office_vendor.username,
                password=office_vendor.password,
            )
            tasks.append(scraper.search_products_v2(query=keyword, office=office_vendor.office))
        return await asyncio.gather(*tasks, return_exceptions=True)


@shared_task
def search_products(keyword, office_id, vendor_ids):
    office_vendors = list(
        OfficeVendor.objects.select_related("office")
        .select_related("vendor")
        .filter(office_id=office_id, vendor_id__in=vendor_ids)
    )
    keyword_objs = KeywordModel.objects.filter(keyword=keyword, office_id=office_id, vendor_id__in=vendor_ids)
    for keyword_obj in keyword_objs:
        keyword_obj.task_status = KeywordModel.TaskStatus.IN_PROGRESS
    KeywordModel.objects.bulk_update(keyword_objs, ["task_status"])

    vendors_products = asyncio.run(_search_products(keyword, office_vendors))

    for keyword_obj, vendor_products in zip(keyword_objs, vendors_products):
        if isinstance(vendor_products, list) and all(
            [isinstance(vendor_product, ProductModel) for vendor_product in vendor_products]
        ):
            keyword_obj.task_status = KeywordModel.TaskStatus.COMPLETE
        else:
            # TODO: if it fails, we need to retry
            keyword_obj.task_status = KeywordModel.TaskStatus.FAILED
        keyword_obj.save()

    # pricing comparison
    # meta, products = group_products_from_search_result(products)
