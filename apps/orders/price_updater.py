from collections import namedtuple
from typing import List

from aiohttp import ClientSession
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.common.enums import SupportedVendor
from apps.orders.models import OfficeProduct, Product
from services.api_client import DentalCityAPIClient, Net32APIClient, ProductPrice

VendorAPIClientMapper = namedtuple(
    "VendorAPIClientMapper",
    (
        "klass",
        "identifier_in_table",
    ),
)

VendorAPIClientMapping = {
    SupportedVendor.DentalCity: {
        "klass": DentalCityAPIClient,
        "kwargs": {
            "auth_key": settings.DENTAL_CITY_AUTH_KEY,
        },
        "product_identifier_name_in_table": "sku",
    },
    SupportedVendor.Net32: {
        "klass": Net32APIClient,
        "product_identifier_name_in_table": "product_id",
    },
}
BATCH_SIZE = 500


@sync_to_async
def update_prices(vendor: SupportedVendor, products: List[ProductPrice]):
    products_by_identifier = {product.product_identifier: product for product in products}
    update_time = timezone.now()
    office_product_instances = []

    vendor_api_client_info = VendorAPIClientMapping[vendor]
    product_identifier_name_in_table = vendor_api_client_info["product_identifier_name_in_table"]
    filters = Q(vendor__slug=vendor.value) & Q(
        **{f"{product_identifier_name_in_table}__in": products_by_identifier.keys()}
    )
    product_instances = Product.objects.filter(filters)
    for product_instance in product_instances:
        product_identifier_in_table = getattr(product_instance, product_identifier_name_in_table)
        product_price = products_by_identifier[product_identifier_in_table].price
        product_instance.price = product_price
        product_instance.last_price_updated = update_time

        office_products = OfficeProduct.objects.filter(product=product_instance)
        for office_product in office_products:
            office_product.price = product_price
            office_product.last_price_updated = update_time
            office_product_instances.append(office_product)

    updated_fields = (
        "price",
        "last_price_updated",
    )

    with transaction.atomic():
        Product.objects.bulk_update(product_instances, fields=updated_fields)
        OfficeProduct.objects.bulk_update(office_product_instances, fields=updated_fields)


async def update_vendor_products_prices_by_api(vendor_slug: str) -> None:
    async with ClientSession() as session:
        vendor = SupportedVendor(vendor_slug)
        vendor_api_client_info = VendorAPIClientMapping[vendor]
        api_client_klass = vendor_api_client_info["klass"]
        kwargs = {"session": session}
        if extra_kwargs := vendor_api_client_info.get("kwargs"):
            kwargs.update(extra_kwargs)

        client = api_client_klass(**kwargs)
        products_from_api = await client.get_products()
        products_len = len(products_from_api)

        for i in range(0, products_len, BATCH_SIZE):
            products_chunk = products_from_api[i : i + BATCH_SIZE]
            await update_prices(vendor, products_chunk)
