import asyncio

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
    def create_scraper(cls, *, scraper_name: str, username: str, password: str, session: ClientSession):
        if scraper_name not in SCRAPERS:
            raise VendorNotSupported(scraper_name)

        return SCRAPERS[scraper_name](username, password, session)


async def main():
    async with ClientSession() as session:
        scraper = ScraperFactory.create_scraper(
            scraper_name="henry_schein", username="Alextkantor1", password="co80128", session=session
        )
        # scraper = ScraperFactory.create_scraper(
        #     scraper_name="net_32", username="Info@glacierpeakdentistry.com", password="Glacier19!", session=session
        # )
        orders = await scraper.get_orders()
        print(orders)


if __name__ == "__main__":
    import time

    start_time = time.perf_counter()
    asyncio.run(main())
    print(time.perf_counter() - start_time)
