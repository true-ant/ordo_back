import asyncio
from typing import Optional

from aiohttp import ClientSession

from apps.scrapers.darby import DarbyScraper
from apps.scrapers.errors import VendorNotSupported
from apps.scrapers.henryschein import HenryScheinScraper
from apps.scrapers.net32 import Net32Scraper
from apps.scrapers.ultradent import UltraDentScraper

SCRAPERS = {
    "henry_schein": HenryScheinScraper,
    "net_32": Net32Scraper,
    "ultradent": UltraDentScraper,
    "darby": DarbyScraper,
}


class ScraperFactory:
    @classmethod
    def create_scraper(
        cls,
        *,
        scraper_name: str,
        session: ClientSession,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        if scraper_name not in SCRAPERS:
            raise VendorNotSupported(scraper_name)

        return SCRAPERS[scraper_name](session, username, password)


async def main():
    scraper_name = "darby"
    credentials = {
        "henry_schein": {"username": "Alextkantor1", "password": "co80128"},
        "net_32": {"username": "Info@glacierpeakdentistry.com", "password": "Glacier19!"},
        "ultradent": {"username": "info@columbinecreekdentistry.com", "password": "co80128!"},
        "darby": {"username": "whale5310*", "password": "co80128"},
    }
    credential = credentials[scraper_name]
    async with ClientSession() as session:
        scraper = ScraperFactory.create_scraper(
            scraper_name=scraper_name,
            session=session,
            username=credential["username"],
            password=credential["password"],
        )
        orders = await scraper.get_orders(perform_login=True)
        print(orders)


if __name__ == "__main__":
    import time

    start_time = time.perf_counter()
    asyncio.run(main())
    print(time.perf_counter() - start_time)
