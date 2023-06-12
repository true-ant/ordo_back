from aiohttp import ClientSession

from apps.api_clients.dc_dental import DCDentalClient
from apps.api_clients.dental_city import DentalCityClient
from apps.scrapers.errors import VendorNotSupported

API_CLIENTS = {
    "dental_city": DentalCityClient,
    "dcdental": DCDentalClient,
}


class APIClientFactory:
    @classmethod
    def get_api_client(
        cls,
        *,
        vendor,
        session: ClientSession,
    ):
        if vendor.slug not in API_CLIENTS:
            raise VendorNotSupported(vendor.slug)

        return API_CLIENTS[vendor.slug](session)
