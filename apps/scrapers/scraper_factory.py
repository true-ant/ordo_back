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
    scraper_name = "ultradent"
    credentials = {
        "henry_schein": {
            "username": os.getenv("HENRY_SCHEIN_USERNAME"),
            "password": os.getenv("HENRY_SCHEIN_PASSWORD"),
        },
        "net_32": {
            "username": os.getenv("NET32_USERNAME"),
            "password": os.getenv("NET32_PASSWORD"),
        },
        "ultradent": {
            "username": os.getenv("ULTRADENT_SCHEIN_USERNAME"),
            "password": os.getenv("ULTRADENT_SCHEIN_PASSWORD"),
        },
        "darby": {
            "username": os.getenv("DARBY_SCHEIN_USERNAME"),
            "password": os.getenv("DARBY_SCHEIN_PASSWORD"),
        },
        "patterson": {
            "username": os.getenv("PATTERSON_USERNAME"),
            "password": os.getenv("PATTERSON_PASSWORD"),
        },
        "benco": {
            "username": os.getenv("BENCO_USERNAME"),
            "password": os.getenv("BENCO_PASSWORD"),
        },
    }
    credential = credentials[scraper_name]
    async with ClientSession() as session:
        scraper = ScraperFactory.create_scraper(
            scraper_name=scraper_name,
            session=session,
            username=credential["username"],
            password=credential["password"],
        )
        # await scraper.login()
        # results = await scraper.get_orders(perform_login=True)
        results = await scraper.search_products(query="tooth brush", page=1, min_price=10, max_price=20)
        # results = [r.to_dict() for r in results]
        print(results)


if __name__ == "__main__":
    import time

    start_time = time.perf_counter()
    asyncio.run(main())
    print(time.perf_counter() - start_time)
