import logging
from typing import List

from apps.accounts.models import OfficeVendor
from apps.orders.models import VendorOrder
from apps.types.orders import CartProduct
from services.api_client import DCDentalAPIClient

logger = logging.getLogger(__name__)


class DCDentalClient:
    def __init__(self, session):
        self.api_client = DCDentalAPIClient(session=session)

    async def get_or_create_customer_id(self, email, customer_data):
        customer_info = await self.api_client.get_customer(email)
        if customer_info:
            return customer_info[0]["internalid"]
        else:
            return await self.api_client.create_customer(customer_data)

    async def get_or_create_customer_address(self, customer_id, customer_address_data):
        customer_address_info = await self.api_client.get_customer_address(customer_id)
        if customer_address_info[0]["addressinternalid"]:
            return customer_address_info[0]["addressinternalid"]
        else:
            customer_address_info = await self.api_client.create_customer_address(customer_address_data)
            return customer_address_info["addressid"]

    async def place_order(self, office_vendor: OfficeVendor, vendor_order: VendorOrder, products: List[CartProduct]):
        office = office_vendor.office
        office_address = office_vendor.office.addresses.first()
        office_email = office_vendor.username

        office_phone_number = f"+{office.phone_number.country_code} {office.phone_number.national_number}"
        customer_data = {
            "body": {
                "entitystatus": "13",
                "entityid": f"{office.name} {office_phone_number}",
                "companyname": office.name,
                "phone": office_phone_number,
                "externalid": office_vendor.id,
                "email": office_email,
            }
        }
        customer_id = await self.get_or_create_customer_id(office_email, customer_data)

        customer_address_data = {
            "parameters": {"customerid": customer_id},
            "body": {
                "defaultbilling": True,
                "defaultshipping": False,
                "addressee": office.name,
                "attention": office_address.address,
                "city": office_address.city,
                "state": office_address.state,
                "country": "US",
                "zip": office_address.zip_code,
                "addr1": office_address.address,
            },
        }
        customer_address = await self.get_or_create_customer_address(customer_id, customer_address_data)

        order_info = {
            "body": {
                "entity": customer_id,
                "trandate": vendor_order.created_at.strftime("%m/%d/%Y"),
                "otherrefnum": str(vendor_order.id),
                "shipaddresslist": customer_address,
                "billaddresslist": customer_address,
                "items": [
                    {
                        "itemid": product["sku"],
                        "quantity": product["quantity"],
                        "rate": product["price"] if product["price"] else 0,
                    }
                    for product in products
                ],
            }
        }

        result = await self.api_client.create_order_request(order_info)
        vendor_order.vendor_order_id = result
        await vendor_order.asave()
