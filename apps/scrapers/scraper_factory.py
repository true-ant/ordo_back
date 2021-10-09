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
from apps.types.scraper import VendorInformation

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
        vendor: VendorInformation,
        session: ClientSession,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        if vendor["slug"] not in SCRAPERS:
            raise VendorNotSupported(vendor["slug"])

        return SCRAPERS[vendor["slug"]](session, vendor, username, password)


async def main():

    load_dotenv()
    scraper_name = "net_32"
    BASE_DATA = {
        "henry_schein": {
            "username": os.getenv("HENRY_SCHEIN_USERNAME"),
            "password": os.getenv("HENRY_SCHEIN_PASSWORD"),
            "vendor": {
                "id": 1,
                "slug": "henry_schein",
                "logo": "vendors/henry_schein.jpg",
                "name": "Henry Schein",
                "url": "https://www.henryschein.com/",
            },
            "products": [
                {
                    "product_id": "3840072",
                    "product_url": "https://www.henryschein.com/us-en/dental/p/restorative-cosmetic"
                    "/articulating/articulating-paper-40-microns/3840072",
                    "quantity": 1,
                },
                {
                    "product_id": "4434033",
                    "product_url": "https://www.henryschein.com/us-en/dental/p/infection-control-products"
                    "/protective-eyewear/visor-shield-kit-medium/4434033",
                    "quantity": 1,
                },
                {
                    "product_id": "5430231",
                    "product_url": "https://www.henryschein.com/us-en/dental/p/preventive"
                    "/toothbrushes/colgate-pj-masks-toothbrush/5430231",
                    "quantity": 1,
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
                    "quantity": 1,
                },
                {
                    "product_id": "149881",
                    "product_url": "https://www.net32.com/ec/caviwipes-12-towelettes-large-6-x-675-d-149881",
                    "quantity": 1,
                },
            ],
            "vendor": {
                "id": 2,
                "slug": "net_32",
                "logo": "vendors/net_32.jpg",
                "name": "Net 32",
                "url": "https://www.net32.com/",
            },
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
            "vendor": {
                "id": 3,
                "slug": "darby",
                "logo": "vendors/darby.jpg",
                "name": "Darby",
                "url": "https://www.darbydental.com/",
            },
        },
        "patterson": {
            "username": os.getenv("PATTERSON_USERNAME"),
            "password": os.getenv("PATTERSON_PASSWORD"),
            "vendor": {
                "id": 4,
                "slug": "patterson",
                "logo": "vendors/patterson.jpg",
                "name": "Patterson",
                "url": "https://www.pattersondental.com/",
            },
            "products": [
                {
                    "product_id": "PIF_63718",
                    "product_url": "https://www.pattersondental.com/Supplies/ProductFamilyDetails/PIF_63718?mc=0",
                },
                {
                    "product_id": "PIF_857369",
                    "product_url": "https://www.pattersondental.com/Supplies/ItemDetail/071110139",
                },
            ],
        },
        "ultradent": {
            "username": os.getenv("ULTRADENT_SCHEIN_USERNAME"),
            "password": os.getenv("ULTRADENT_SCHEIN_PASSWORD"),
            "vendor": {
                "id": 6,
                "slug": "ultradent",
                "logo": "vendors/ultradent.jpg",
                "name": "Ultradent",
                "url": "https://www.ultradent.com/",
            },
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
            "vendor": {
                "id": 7,
                "slug": "benco",
                "logo": "vendors/benco.jpg",
                "name": "Benco",
                "url": "https://www.benco.com/",
            },
        },
    }

    scraper_data = BASE_DATA[scraper_name]
    async with ClientSession() as session:
        scraper = ScraperFactory.create_scraper(
            vendor=scraper_data["vendor"],
            session=session,
            username=scraper_data["username"],
            password=scraper_data["password"],
        )
        # await scraper.login()

        # results = await scraper.get_orders(perform_login=True)
        # results = await scraper.search_products(query="tooth brush", page=1)
        # results = [r.to_dict() for r in results]
        # results = await scraper.get_product(
        #     product_id=BASE_DATA[scraper_name]["products"][0]["product_id"],
        #     product_url=BASE_DATA[scraper_name]["products"][0]["product_url"],
        #     perform_login=True,
        # )
        # results = await scraper.get_all_products()
        # results = await scraper.get_vendor_categories(perform_login=True)

        # await scraper.login()
        # await scraper.remove_product_from_cart(
        #     product_id=BASE_DATA[scraper_name]["products"][0]["product_id"], use_bulk=False
        # )
        # results = await scraper.add_product_to_cart(
        #     dict(
        #         product_id=BASE_DATA[scraper_name]["products"][0]["product_id"],
        #         quantity=BASE_DATA[scraper_name]["products"][0]["quantity"],
        #     )
        # )

        products = [
            {
                "product_id": product["product_id"],
                "quantity": product["quantity"],
            }
            for product in BASE_DATA[scraper_name]["products"]
        ]
        results = await scraper.create_order(products)
        print(results)


if __name__ == "__main__":
    import time

    start_time = time.perf_counter()
    asyncio.run(main())
    print(time.perf_counter() - start_time)
