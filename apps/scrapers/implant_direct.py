import logging

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.types.scraper import LoginInformation, ProductSearch

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
HOMEPAGE_HEADERS = {
    "authority": "store.implantdirect.com",
    "cache-control": "max-age=0",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "none",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

LOGIN_PAGE_HEADERS = {
    "authority": "store.implantdirect.com",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "referer": "https://store.implantdirect.com/",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

LOGIN_HEADERS = {
    "authority": "store.implantdirect.com",
    "cache-control": "max-age=0",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1",
    "origin": "https://store.implantdirect.com",
    "content-type": "application/x-www-form-urlencoded",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}


class ImplantDirectScraper(Scraper):
    BASE_URL = "https://www.henryschein.com"
    CATEGORY_URL = "https://www.henryschein.com/us-en/dental/c/browsesupplies"
    TRACKING_BASE_URL = "https://narvar.com/tracking/itemvisibility/v1/henryschein-dental/orders"

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        text = await response.text()
        dom = Selector(text=text)
        page_title = dom.css("title::text").get()
        return page_title != "Customer Login"

    async def get_login_link(self):
        async with self.session.get("https://store.implantdirect.com/", headers=HOMEPAGE_HEADERS) as resp:
            text = await resp.text()
            home_dom = Selector(text=text)
            return home_dom.xpath('//ul/li[@class="authorization-link"]/a/@href').get()

    async def get_login_form(self, login_link):
        async with self.session.get(login_link, headers=LOGIN_PAGE_HEADERS) as resp:
            text = await resp.text()
            login_dom = Selector(text=text)
            form_key = login_dom.xpath('//form[@id="login-form"]/input[@name="form_key"]/@value').get()
            form_action = login_dom.xpath('//form[@id="login-form"]/@action').get()
            return {
                "key": form_key,
                "action": form_action,
            }

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        login_link = await self.get_login_link()
        form = await self.get_login_form(login_link)
        headers = LOGIN_HEADERS.copy()
        headers["referer"] = login_link

        return {
            "url": form["action"],
            "headers": headers,
            "data": {
                "form_key": form["key"],
                "login[username]": self.username,
                "login[password]": self.password,
                "send": "",
            },
        }

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0, sort_by="price", office_id=None
    ) -> ProductSearch:
        return await self._search_products_from_table(query, page, min_price, max_price, sort_by, office_id)
