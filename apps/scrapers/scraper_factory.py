import asyncio
from typing import Optional

from aiohttp import ClientSession

from apps.scrapers.errors import VendorNotSupported
from apps.scrapers.henryschein import HenryScheinScraper
from apps.scrapers.net32 import Net32Scraper

SCRAPERS = {
    "henry_schein": HenryScheinScraper,
    "net_32": Net32Scraper,
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
    async with ClientSession() as session:
        # scraper = ScraperFactory.create_scraper(
        #     scraper_name="henry_schein", session=session, username="Alextkantor1", password="co80128"
        # )
        scraper = ScraperFactory.create_scraper(
            scraper_name="net_32", session=session, username="Info@glacierpeakdentistry.com", password="Glacier19!"
        )
        orders = await scraper.get_orders()
        print(orders)


if __name__ == "__main__":
    import time

    start_time = time.perf_counter()
    asyncio.run(main())
    print(time.perf_counter() - start_time)
