from http.cookies import SimpleCookie
from typing import Optional

from aiohttp import ClientResponse, ClientSession

from apps.scrapers.errors import VendorAuthenticationFailed
from apps.types.scraper import LoginInformation


class Scraper:
    def __init__(
        self,
        session: ClientSession,
        username: Optional[str] = None,
        password: Optional[str] = None,
        vendor_id: Optional[int] = None,
    ):
        self.session = session
        self.username = username
        self.password = password
        self.vendor_id = vendor_id

    async def login(self, username: Optional[str] = None, password: Optional[str] = None) -> SimpleCookie:
        if username:
            self.username = username
        if password:
            self.password = password

        login_info = await self._get_login_data()
        async with self.session.post(
            login_info["url"], headers=login_info["headers"], data=login_info["data"]
        ) as resp:
            if resp.status != 200:
                raise VendorAuthenticationFailed()

            await self._after_login_hook(resp)

            is_authenticated = await self._check_authenticated(resp)
            if not is_authenticated:
                raise VendorAuthenticationFailed()

        return resp.cookies

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        return True

    async def _get_login_data(self) -> LoginInformation:
        pass

    async def _after_login_hook(self, response: ClientResponse):
        pass

    def extract_first(self, dom, xpath):
        return x.strip() if (x := dom.xpath(xpath).extract_first()) else x

    def merge_strip_values(self, dom, xpath, delimeter=""):
        return delimeter.join(filter(None, map(str.strip, dom.xpath(xpath).extract())))
