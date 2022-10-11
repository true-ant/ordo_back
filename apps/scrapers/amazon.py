import re
import logging
from scrapy import Selector
from requests import Session
from typing import Dict, List, Optional
from aiohttp import ClientResponse, ClientSession

import undetected_chromedriver.v2 as uc


from apps.scrapers.base import Scraper
from apps.scrapers.schema import Product
from apps.types.scraper import ProductSearch
from apps.types.orders import CartProduct
from apps.scrapers.schema import Order, Product, ProductCategory, VendorOrderDetail

session = Session()


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class AmazonScraper(Scraper):

    def __init__(
        self,
        session: ClientSession,
        vendor,
        username: Optional[str] = None,
        password: Optional[str] = None,
        ):
        Scraper.__init__(self,session,vendor, username,password)
        self.driver = None
        self.sleepAmount = 10
        self.results = list()
        self.testval = 0
        

    BASE_URL = "https://www.amazon.com"

    def setDriver(self):
        user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_3) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/80.0.3987.132 Safari/537.36"
        )

        chrome_options = uc.ChromeOptions()
        chrome_options.add_argument("--disable-dev-shm-usage")
        # chrome_options.add_argument("--headless")
        chrome_options.add_argument(f"user-agent={user_agent}")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--log-level=3")
        driver = uc.Chrome(
            # ChromeDriverManager().install(),
            options=chrome_options,
        )
        self.testval = 23
        return driver

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        print("amazon/create_order")
        self.driver = self.setDriver()
        print(self.testval)
        
    async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False):
        print("amazon/confirm_order")