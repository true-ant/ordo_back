import asyncio
import os
from typing import Optional

from aiohttp import ClientSession
from dotenv import load_dotenv

from apps.scrapers.benco import BencoScraper
from apps.scrapers.darby import DarbyScraper
from apps.scrapers.errors import VendorNotSupported
from apps.scrapers.henryschein import HenryScheinScraper
from apps.scrapers.net32 import Net32Scraper
from apps.scrapers.patterson import PattersonScraper
from apps.scrapers.ultradent import UltraDentScraper

SCRAPERS = {
    "henry_schein": HenryScheinScraper,
    "net_32": Net32Scraper,
    "ultradent": UltraDentScraper,
    "darby": DarbyScraper,
    "patterson": PattersonScraper,
    "benco": BencoScraper,
}


class ScraperFactory:
    @classmethod
    def create_scraper(
        cls,
        *,
        scraper_name: str,
        session: ClientSession,
        username: Optional[str] = None,
        password: Optional[str] = None,
        vendor_id: Optional[int] = None,
    ):
        if scraper_name not in SCRAPERS:
            raise VendorNotSupported(scraper_name)

        return SCRAPERS[scraper_name](session, scraper_name, username, password, vendor_id)


async def main():

    load_dotenv()
    scraper_name = "net_32"
    BASE_DATA = {
        "henry_schein": {
            "username": os.getenv("HENRY_SCHEIN_USERNAME"),
            "password": os.getenv("HENRY_SCHEIN_PASSWORD"),
            "products": [
                {
                    "product_id": "3840072",
                    "product_url": "https://www.henryschein.com/us-en/dental/p/restorative-cosmetic"
                    "/articulating/articulating-paper-40-microns/3840072",
                },
                {
                    "product_id": "4434033",
                    "product_url": "https://www.henryschein.com/us-en/dental/p/infection-control-products"
                    "/protective-eyewear/visor-shield-kit-medium/4434033",
                },
            ],
        },
        "net_32": {
            "username": os.getenv("NET32_USERNAME"),
            "password": os.getenv("NET32_PASSWORD"),
            "products": [
                {
                    "product_id": "113866",
                    "product_url": "https://www.net32.com/ec/house-brand-premium-nitrile-exam-gloves-small-d-113866",
                },
                {
                    "product_id": "149881",
                    "product_url": "https://www.net32.com/ec/caviwipes-12-towelettes-large-6-x-675-d-149881",
                },
            ],
        },
        "darby": {
            "username": os.getenv("DARBY_SCHEIN_USERNAME"),
            "password": os.getenv("DARBY_SCHEIN_PASSWORD"),
            "products": [
                {
                    "product_id": "323-3644",
                    "product_url": "https://www.darbydental.com/categories/Infection-Control"
                    "/Sterilization-Bags--Pouches--and-Tubing/CSR-Sterilization-Wrap/3233644",
                },
                {
                    "product_id": "5250698",
                    "product_url": "https://www.darbydental.com/categories/Preventive-Products"
                    "/Toothbrushes/Oral-B-Orthodontic-Brush/5250698",
                },
            ],
        },
        "patterson": {
            "username": os.getenv("PATTERSON_USERNAME"),
            "password": os.getenv("PATTERSON_PASSWORD"),
        },
        "ultradent": {
            "username": os.getenv("ULTRADENT_SCHEIN_USERNAME"),
            "password": os.getenv("ULTRADENT_SCHEIN_PASSWORD"),
        },
        "benco": {
            "username": os.getenv("BENCO_USERNAME"),
            "password": os.getenv("BENCO_PASSWORD"),
            "products": [
                {
                    "product_id": "2127-717",
                    "product_url": "https://shop.benco.com/Product/2127-717/turbosensor-ultrasonic-scaler",
                },
                {
                    "product_id": "2452-311",
                    "product_url": "https://shop.benco.com/Product/2452-311"
                    "/periosonic-multi-fluid-irrigator#product-detail-tab",
                },
            ],
        },
    }

    credential = BASE_DATA[scraper_name]
    async with ClientSession() as session:
        scraper = ScraperFactory.create_scraper(
            scraper_name=scraper_name,
            session=session,
            username=credential["username"],
            password=credential["password"],
        )
        # await scraper.login()

        # results = await scraper.get_orders(perform_login=True)
        # results = await scraper.search_products(query="todsadsadsaoth brush")
        # results = [r.to_dict() for r in results]
        results = await scraper.get_product(
            product_id=BASE_DATA[scraper_name]["products"][0]["product_id"],
            product_url=BASE_DATA[scraper_name]["products"][0]["product_url"],
            perform_login=True,
        )

        print(results)


if __name__ == "__main__":
    import time

    start_time = time.perf_counter()
    asyncio.run(main())
    print(time.perf_counter() - start_time)
