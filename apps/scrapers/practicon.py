import datetime
from decimal import Decimal
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

from apps.common import messages as msgs
from apps.scrapers.base import Scraper
from apps.scrapers.utils import catch_network, semaphore_coroutine
from apps.scrapers.schema import VendorOrderDetail, Order
from apps.types.orders import CartProduct

class PracticonScraper(Scraper):

    reqsession = requests.Session()

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        print("Practicon/create_order")
        
    async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False):
        print("Practicon/confirm_order")
