import asyncio
import datetime
import logging
from collections import defaultdict

from aiohttp import ClientSession
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import F, Q
from django.template.loader import render_to_string
from django.utils import timezone
from slugify import slugify

from apps.accounts.models import CompanyMember, OfficeVendor, User
from apps.common.utils import group_products
from apps.orders.models import Keyword as KeyModel
from apps.orders.models import OfficeCheckoutStatus
from apps.orders.models import OfficeKeyword as OfficeKeyModel
from apps.orders.models import OfficeProduct as OfficeProductModel
from apps.orders.models import Order as OrderModel
from apps.orders.models import OrderStatus
from apps.orders.models import Product as ProductModel
from apps.orders.models import ProductCategory
from apps.orders.models import ProductImage as ProductImageModel
from apps.orders.models import VendorOrder as VendorOrderModel
from apps.orders.models import VendorOrderProduct as VendorOrderProductModel
from apps.scrapers.schema import Product as ProductDataClass
from apps.scrapers.scraper_factory import ScraperFactory

logger = logging.getLogger(__name__)


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
            tasks.append(scraper.search_products_v2(keyword, office=office_vendor.office))
        return await asyncio.gather(*tasks, return_exceptions=True)


@shared_task
def search_and_group_products(keyword, office_id, vendor_ids):
    office_vendors_to_be_searched = list(
        OfficeVendor.objects.select_related("office")
        .select_related("vendor")
        .filter(office_id=office_id, vendor_id__in=vendor_ids)
    )
    keyword = KeyModel.objects.get(keyword=keyword)
    keyword_objs = OfficeKeyModel.objects.filter(keyword=keyword, office_id=office_id, vendor_id__in=vendor_ids)
    for keyword_obj in keyword_objs:
        keyword_obj.task_status = OfficeKeyModel.TaskStatus.IN_PROGRESS
    OfficeKeyModel.objects.bulk_update(keyword_objs, ["task_status"])

    searched_vendors_products = asyncio.run(_search_products(keyword, office_vendors_to_be_searched))

    vendors_products = []
    for keyword_obj, vendor_products in zip(keyword_objs, searched_vendors_products):
        if isinstance(vendor_products, list) and all(
            [isinstance(vendor_product, ProductModel) for vendor_product in vendor_products]
        ):
            keyword_obj.task_status = OfficeKeyModel.TaskStatus.FETCHING_COMPLETE
            vendors_products.append(vendor_products)
        else:
            # TODO: if it fails, we need to retry
            keyword_obj.task_status = OfficeKeyModel.TaskStatus.FAILED

    OfficeKeyModel.objects.bulk_update(keyword_objs, ["task_status"])

    # pricing comparison
    # get other linked vendor products
    other_office_vendors = (
        OfficeVendor.objects.select_related("office")
        .select_related("vendor")
        .filter(Q(office_id=office_id) & ~Q(vendor_id__in=vendor_ids))
    )
    for other_office_vendor in other_office_vendors:
        vendors_products.append(
            ProductModel.objects.filter(
                Q(vendor=other_office_vendor.vendor), (Q(tags=keyword) | Q(name__icontains=keyword.keyword))
            )
        )

    grouped = group_products(vendors_products, model=True)
    if grouped:
        for keyword_obj in keyword_objs:
            keyword_obj.task_status = OfficeKeyModel.TaskStatus.COMPLETE
        OfficeKeyModel.objects.bulk_update(keyword_objs, ["task_status"])


@shared_task
def notify_order_creation(order_id, approval_needed, product_ids=()):
    try:
        order = OrderModel.objects.get(id=order_id)
    except OrderModel.DoesNotExist:
        return

    office = order.office

    # add products to inventory lists
    office_products = OfficeProductModel.objects.filter(office=office, product__product_id__in=product_ids)
    for office_product in office_products:
        office_product.is_inventory = True
    OfficeProductModel.objects.bulk_update(office_products, ["is_inventory"])

    # send notification
    if approval_needed:
        emails = (
            CompanyMember.objects.select_related("user")
            .filter(
                Q(invite_status=CompanyMember.InviteStatus.INVITE_APPROVED),
                Q(company=office.company),
                Q(role=User.Role.ADMIN),
                (Q(office=office) | Q(office__isnull=True)),
            )
            .values_list("user__email", flat=True)
        )
    else:
        emails = (
            CompanyMember.objects.select_related("user")
            .filter(
                Q(invite_status=CompanyMember.InviteStatus.INVITE_APPROVED),
                Q(company=office.company),
                (Q(office=office) | Q(office__isnull=True)),
            )
            .values_list("user__email", flat=True)
        )

    products = VendorOrderProductModel.objects.filter(vendor_order__order_id=order_id).annotate(
        total_price=F("unit_price") * F("quantity")
    )
    # TODO: Compare performance above vs below, I guess below is more faster than above
    #  because additional query won't happen in django templates

    # products = (
    #     VendorOrderProductModel.objects.filter(vendor_order__order_id=order_id)
    #     .annotate(total_price=F("unit_price") * F("quantity"))
    #     .values(
    #         "product__images__image",
    #         "product__name",
    #         "product__vendor__name",
    #         "product__vendor__logo",
    #         "quantity",
    #         "unit_price",
    #         "total_price",
    #     )
    # )

    if approval_needed:
        email_template = "order_approval_needed.html"
    else:
        email_template = "order_creation.html"
    htm_content = render_to_string(
        f"emails/{email_template}.html",
        {
            "order": order,
            "products": products,
            "SITE_URL": settings.SITE_URL,
        },
    )

    send_mail(
        subject="Order Approval Needed!" if approval_needed else "Created Order!",
        message="message",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=emails,
        html_message=htm_content,
    )


async def _sync_with_vendor_for_orders(orders_by_office_vendors, office_vendors):
    sem = asyncio.Semaphore(value=50)
    async with ClientSession() as session:
        tasks = []
        for orders_by_office_vendor, office_vendor in zip(orders_by_office_vendors, office_vendors):
            scraper = ScraperFactory.create_scraper(
                vendor=office_vendor.vendor,
                session=session,
                username=office_vendor.username,
                password=office_vendor.password,
            )
            tasks.extend([scraper.get_order(order.order_id, sem) for order in orders_by_office_vendor])
        await asyncio.gather(*tasks)


@shared_task
def sync_with_vendor_for_orders():
    """Sync order status with vendor for pending orders"""
    # get pending orders
    processing_vendor_orders = VendorOrderModel.objects.select_related("vendor", "order", "order__office").filter(
        status=OrderStatus.PROCESSING
    )

    orders_by_office_vendors = defaultdict(list)
    office_vendors = []
    for processing_vendor_order in processing_vendor_orders:
        office_id = processing_vendor_order.order.office_id
        vendor_id = processing_vendor_order.vendor_id
        office_vendor_id = f"{office_id}-{vendor_id}"
        if office_vendor_id not in orders_by_office_vendors:
            office_vendors.append(OfficeVendor.objects.get(office_id=office_id, vendor_id=vendor_id))

        orders_by_office_vendors[office_vendor_id].append(processing_vendor_order)

    asyncio.run(_sync_with_vendor_for_orders(orders_by_office_vendors, office_vendors))
