import datetime
from typing import List

from aiohttp import ClientSession
from django.db.models import Q
from django.utils import timezone

from apps.orders.models import Product
from services.api_client import Net32APIClient
from services.api_client.vendor_api_types import Net32ProductInfo

BATCH_SIZE = 1000


async def update_net32_products():
    """
    Fetch Full products from Net32 using API
    - Enable or disable products in the table
    - Update prices if not updated since yesterday.
    """
    async with ClientSession() as session:
        client = Net32APIClient(session)
        products_from_api: List[Net32ProductInfo] = await client.get_full_products()

        await enable_or_disable_products(products_from_api)
        await update_prices(products_from_api)


async def enable_or_disable_products(products_from_api: List[Net32ProductInfo]):
    net32_db_product_ids = set(await Product.net32.available_products().avalues_list("product_id"))
    net32_api_product_ids = set(product.mp_id for product in products_from_api)

    updated_at = timezone.now()
    product_ids_to_be_disabled = net32_db_product_ids - net32_api_product_ids
    product_ids_to_be_enabled = net32_api_product_ids - net32_db_product_ids

    if product_ids_to_be_disabled:
        product_instances = Product.net32.filter(product_id__in=product_ids_to_be_disabled)
        async for product_instance in product_instances:
            product_instance.is_available_on_vendor = False
            product_instance.updated_at = updated_at

        await Product.objects.abulk_update(
            product_instances, fields=["is_available_on_vendor", "updated_at"], batch_size=BATCH_SIZE
        )

    if product_ids_to_be_enabled:
        product_instances = Product.net32.filter(product_id__in=product_ids_to_be_enabled)
        existing_product_ids = set()

        async for product_instance in product_instances:
            existing_product_ids.add(product_instance.product_id)
            product_instance.is_available_on_vendor = True
            product_instance.updated_at = updated_at

        product_ids_to_be_created = product_ids_to_be_enabled - existing_product_ids
        products_to_be_created = [
            Product(
                vendor_id=2,
                product_id=product.mp_id,
                manufacturer_number=product.manufacturer_number,
                name=product.name,
                url=product.url,
                price=product.price,
                last_price_updated=updated_at,
                created_at=updated_at,
                updated_at=updated_at,
            )
            for product in products_from_api
            if product.mp_id in product_ids_to_be_created
        ]

        await Product.objects.abulk_update(
            product_instances, fields=["is_available_on_vendor", "updated_at"], batch_size=BATCH_SIZE
        )
        await Product.objects.abulk_create(products_to_be_created, batch_size=BATCH_SIZE)


async def update_prices(products_from_api: List[Net32ProductInfo]):
    product_prices = {p.mp_id: p.price for p in products_from_api}
    updated_at = timezone.now()
    datetime_from = updated_at - datetime.timedelta(days=1)
    product_instances = Product.net32.available_products().filter(
        Q(last_price_updated__lt=datetime_from) | Q(last_price_updated=None)
    )
    for product_instance in product_instances:
        if product_instance.product_id not in product_prices:
            continue
        product_instance.price = product_prices[product_instance.product_id]
        product_instance.last_price_updated = updated_at
        product_instance.updated_at = updated_at

    await Product.objects.abulk_update(
        product_instances, fields=["price", "last_price_updated", "updated_at"], batch_size=BATCH_SIZE
    )
