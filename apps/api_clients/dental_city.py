import datetime
import logging
import os
from decimal import Decimal
from typing import List

from apps.accounts.models import CompanyMember, OfficeVendor, User
from apps.orders.models import VendorOrder
from apps.types.orders import CartProduct
from services.api_client import DentalCityAPIClient
from services.api_client.vendor_api_types import (
    DentalCityBillingAddress,
    DentalCityOrderInfo,
    DentalCityOrderProduct,
    DentalCityPartnerInfo,
    DentalCityShippingAddress,
)

logger = logging.getLogger(__name__)
DENTAL_CITY_AUTH_KEY = os.environ.get("DENTAL_CITY_AUTH_KEY")


class DentalCityClient:
    def __init__(self, session):
        self.api_client = DentalCityAPIClient(session=session, auth_key=DENTAL_CITY_AUTH_KEY)

    async def place_order(self, office_vendor: OfficeVendor, vendor_order: VendorOrder, products: List[CartProduct]):
        logger.error(f"Placing Order {office_vendor} - {vendor_order} - {products}")
        office_address = office_vendor.office.addresses.first()
        office_admin = await CompanyMember.objects.filter(
            company=office_vendor.office.company, role=User.Role.ADMIN
        ).afirst()
        logger.error("Building Dental City Request")
        partner_info = DentalCityPartnerInfo(partner_name="Ordo", shared_secret="a4GTFG2a5", customer_id="O00001")
        dental_city_shipping_address = DentalCityShippingAddress(
            name=office_address.office.name,
            address_id=office_address.id,
            deliver_to=office_address.office.name,
            street=office_address.address,
            city=office_address.city,
            state=office_address.state,
            postal_code=office_address.zip_code,
            country_code="US",
            country_name="United States",
            email=office_admin.email,
            phone_number=str(office_vendor.office.phone_number),
        )
        dental_city_billing_address = DentalCityBillingAddress(
            name=office_address.office.name,
            address_id=office_address.id,
            deliver_to=office_address.office.name,
            street=office_address.address,
            city=office_address.city,
            state=office_address.state,
            postal_code=office_address.zip_code,
            country_code="US",
            country_name="United States",
        )
        order_info = DentalCityOrderInfo(
            order_id=vendor_order.vendor_order_id,
            order_datetime=datetime.datetime.now(),
            shipping_address=dental_city_shipping_address,
            billing_address=dental_city_billing_address,
            order_products=[
                DentalCityOrderProduct(
                    product_sku=product["sku"],
                    unit_price=Decimal(str(product["price"])) if product["price"] else Decimal(0),
                    quantity=product["quantity"],
                    manufacturer_part_number=product["manufacturer_number"],
                    product_description=product["product_description"],
                )
                for product in products
            ],
        )
        # Just send the order request using the dental city API
        # We assume that they always process our order request successfully.
        # So, we're always returning true. We will see how it works...
        logger.error("Creating Dental City Order Request")
        await self.api_client.create_order_request(partner_info, order_info)
