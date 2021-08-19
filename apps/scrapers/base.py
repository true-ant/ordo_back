from aiohttp import ClientSession
from aiohttp.typedefs import LooseCookies

from apps.scrapers.errors import VendorAuthenticationFailed
from apps.types.scraper import LoginInformation


class Scraper:
    def __init__(self, username: str, password: str, session: ClientSession):
        self.username = username
        self.password = password
        self.session = session

    async def login(self) -> LooseCookies:
        login_info = self._get_login_data()
        async with self.session.post(
            login_info["url"], headers=login_info["headers"], data=login_info["data"]
        ) as resp:
            if resp.status != 200:
                raise VendorAuthenticationFailed()
        return resp.cookies

    def _get_login_data(self) -> LoginInformation:
        pass
