import re
import logging
from scrapy import Selector
from requests import Session
from typing import Dict, List, Optional
from aiohttp import ClientResponse, ClientSession

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Product
from apps.types.scraper import ProductSearch
from apps.types.orders import CartProduct
from apps.scrapers.schema import Order, Product, ProductCategory, VendorOrderDetail

session = Session()


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class AmazonScraper(Scraper):

    BASE_URL = "https://www.amazon.com"

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        print("amazon/create_order")
        
    async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False):
        print("amazon/confirm_order")