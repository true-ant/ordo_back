from typing import Optional

from aiohttp import ClientResponse, ClientSession
from aiohttp.typedefs import LooseCookies

from apps.scrapers.errors import VendorAuthenticationFailed
from apps.types.scraper import LoginInformation


class Scraper:
    def __init__(self, session: ClientSession, username: Optional[str] = None, password: Optional[str] = None):
        self.session = session
        self.username = username
        self.password = password

    async def login(self, username: Optional[str] = None, password: Optional[str] = None) -> LooseCookies:
        username = username if username else self.username
        password = password if password else self.password
        login_info = self._get_login_data(username, password)
        async with self.session.post(
            login_info["url"], headers=login_info["headers"], data=login_info["data"]
        ) as resp:
            if resp.status != 200:
                raise VendorAuthenticationFailed()

            is_authenticated = await self._check_authenticated(resp)
            if not is_authenticated:
                raise VendorAuthenticationFailed()

        return resp.cookies

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        return True

    def _get_login_data(self, username: str, password: str) -> LoginInformation:
        pass
