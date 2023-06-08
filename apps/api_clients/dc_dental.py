import datetime
import logging
from decimal import Decimal
from typing import List

from apps.accounts.models import OfficeVendor
from apps.orders.models import VendorOrder
from apps.types.orders import CartProduct
from services.api_client import DCDentalAPIClient

logger = logging.getLogger(__name__)


class DCDentalClient:
    def __init__(self, session):
        self.api_client = DCDentalAPIClient(session=session)

    async def place_order(self, office_vendor: OfficeVendor, vendor_order: VendorOrder, products: List[CartProduct]):
        office_email = office_vendor.username
        customer_info = await self.api_client.get_customer(office_email)
        customer_id = customer_info[0]["internalid"]

        customer_address_info = await self.api_client.get_customer_address(customer_id)
        customer_address = customer_address_info[0]["addressinternalid"]

        order_info = {
            "body": {
                "entity": customer_id,
                "trandate": datetime.datetime.strptime(vendor_order.created_at, "%Y-%m-%d"),
                "otherrefnum": str(vendor_order.id),
                "shipaddresslist": customer_address,
                "billaddresslist": customer_address,
                "items": [
                    {
                        "itemid": product["sku"],
                        "quantity": product["quantity"],
                        "rate": Decimal(str(product["price"])) if product["price"] else Decimal(0),
                    }
                    for product in products
                ],
            }
        }
        # Just send the order request using the dental city API
        # We assume that they always process our order request successfully.
        # So, we're always returning true. We will see how it works...
        result = await self.api_client.create_order_request(order_info)
        print(result)
