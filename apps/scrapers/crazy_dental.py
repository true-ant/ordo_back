import datetime
import time
import re
import json
import uuid
import scrapy
import requests
import traceback
import asyncio
from scrapy import Selector
from typing import Dict, List, Optional, Tuple
from http.cookies import SimpleCookie

from apps.scrapers.base import Scraper
from apps.scrapers.utils import catch_network, semaphore_coroutine
from apps.scrapers.schema import VendorOrderDetail, Order
from apps.types.orders import CartProduct

class CrazyDentalScraper(Scraper):
    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        print("Crazy dental/create_order")

    async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False):
        print("Crazy dental/confirm_order")