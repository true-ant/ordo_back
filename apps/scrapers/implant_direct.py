import re
import json
import scrapy
import requests
import traceback
import asyncio
from scrapy import Selector
from typing import Dict, List, Optional, Tuple
from http.cookies import SimpleCookie

from apps.scrapers.base import Scraper
from apps.scrapers.utils import catch_network, semaphore_coroutine
from apps.scrapers.schema import VendorOrderDetail
from apps.types.orders import CartProduct


headers = {
    'authority': 'store.implantdirect.com',
    'sec-ch-ua': '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36',
    'accept': '*/*',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-user': '?1',
    'sec-fetch-dest': 'document',
    'referer': 'https://store.implantdirect.com/us/en/',
    'accept-language': 'en-US,en;q=0.9',
}

class ImplantDirectScraper(Scraper):

    session = requests.Session()

    @catch_network
    async def login(self, username: Optional[str] = None, password: Optional[str] = None) -> SimpleCookie:
        if username:
            self.username = username
        if password:
            self.password = password

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None,self.loginsync)

    def getHomePage(self):
        response = self.session.get('https://store.implantdirect.com/us/en/', headers=headers)
        print("Home Page:", response.status_code)
        return response

    def getLoginPage(self, login_link):
        response = self.session.get(login_link, headers=headers)
        print("LogIn Page:", response.status_code)
        return response
        
    def login(self):
        home_resp = self.getHomePage()
        home_dom = scrapy.Selector(text=home_resp.text)
        login_link = home_dom.xpath('//ul/li[contains(@class, "authorization-link")]/a/@href').get()
        
        login_resp = self.getLoginPage(login_link)
        login_dom = scrapy.Selector(text=login_resp.text)
        form_key = login_dom.xpath('//form[@id="login-form"]/input[@name="form_key"]/@value').get()
        form_action = login_dom.xpath('//form[@id="login-form"]/@action').get()

        data = {
            'form_key': form_key,
            'login[username]': self.username,
            'login[password]': self.password,
            'send': ''
        }

        response = self.session.post(form_action, data=data, headers=headers)
        print(response.url)
        print("Log In POST:", response.status_code)
    
    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        print("Implant Direct/create_order")
        await self.login()
        
