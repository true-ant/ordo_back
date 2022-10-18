import asyncio
import datetime
import re
from math import prod
from typing import Dict, List, Optional

import scrapy
from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product, ProductCategory, VendorOrderDetail
from apps.scrapers.utils import catch_network, semaphore_coroutine
from apps.types.orders import CartProduct
from apps.types.scraper import LoginInformation, ProductSearch

LOGIN_PAGE_HEADERS = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

LOGIN_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "sec-ch-ua-mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Cache-Control": "no-cache",
    "X-Requested-With": "XMLHttpRequest",
    "X-MicrosoftAjax": "Delta=true",
    "sec-ch-ua-platform": '"Windows"',
    "Accept": "*/*",
    "Origin": "https://store.edgeendo.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://store.edgeendo.com/login.aspx",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}
ORDER_HEADERS = {
    'Connection': 'keep-alive',
    'Cache-Control': 'max-age=0',
    'sec-ch-ua': '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-User': '?1',
    'Sec-Fetch-Dest': 'document',
    'Accept-Language': 'en-US,en;q=0.9',
}

def extractContent(dom, xpath):
    return re.sub(r"\s+", " ", " ".join(dom.xpath(xpath).extract())).strip()
class EdgeEndoScraper(Scraper):
    BASE_URL = "https://www.henryschein.com"
    CATEGORY_URL = "https://www.henryschein.com/us-en/dental/c/browsesupplies"
    TRACKING_BASE_URL = "https://narvar.com/tracking/itemvisibility/v1/henryschein-dental/orders"
    product_skus = dict()
    async def _check_authenticated(self, response: ClientResponse) -> bool:
        text = await response.text()
        return "CustomerID" in text

    async def get_login_form(self):
        async with self.session.get("https://store.edgeendo.com/login.aspx", headers=LOGIN_PAGE_HEADERS) as resp:
            text = await resp.text()
            login_dom = Selector(text=text)
            login_dom.xpath('//input[@name="_TSM_HiddenField_"]/@value').extract()

            hidden_field = login_dom.xpath('//input[@name="_TSM_HiddenField_"]/@value').extract_first()
            event_target = login_dom.xpath('//input[@name="__EVENTTARGET"]/@value').extract_first()
            event_argument = login_dom.xpath('//input[@name="__EVENTARGUMENT"]/@value').extract_first()
            view_state = login_dom.xpath('//input[@name="__VIEWSTATE"]/@value').extract_first()
            view_state_generator = login_dom.xpath('//input[@name="__VIEWSTATEGENERATOR"]/@value').extract_first()
            return {
                "hidden_field": hidden_field,
                "event_target": event_target,
                "event_argument": event_argument,
                "view_state": view_state,
                "view_state_generator": view_state_generator,
            }

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        form = await self.get_login_form()

        return {
            "url": "https://store.edgeendo.com/login.aspx",
            "headers": LOGIN_HEADERS,
            "data": {
                "ctl00$ctl00$tsmScripts": "",
                "_TSM_HiddenField_": form["hidden_field"],
                "__EVENTTARGET": form["event_target"],
                "__EVENTARGUMENT": form["event_argument"],
                "__VIEWSTATE": form["view_state"],
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$emlLogin$txtEmail": self.username,
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$emlLogin$vceValid_ClientState": "",
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$emlLogin$vceRequired_ClientState": "",
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$pwdLogin$rtbPassword$txtRestricted": self.password,
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$pwdLogin$rtbPassword$vceRegExp_ClientState": "",
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$pwdLogin$rtbPassword$vceLength_ClientState": "",
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$pwdLogin$rtbPassword$vceRequired_ClientState": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartProductID": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartSKUID": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartQuantity": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartWriteInIDs": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartWriteInValues": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartBidPrice": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartShipTo": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartNewShipTo": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartGiftMessage": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartGiftWrap": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartFulfillmentMethod": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartPickupAt": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartEmailTo": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartSubscriptionID": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartExpressOrder": "",
                "ctl00$ctl00$cphMain$ctl00$hfManualCartPostBack": "",
                "ctl00$ctl00$cphMain$ctl00$hfRemoveCartProductIndex": "",
                "ctl00$ctl00$cphMain$ctl00$hfEditQuantityNewValue": "",
                "ctl00$ctl00$cphMain$ctl00$hfEditQuantityCartProductIndex": "",
                "ctl00$ctl00$cphMain$ctl00$hfReorderID": "",
                "ctl00$ctl00$cphMain$ctl00$hfProductSharingDiscountID": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartRefresh": "",
                "__VIEWSTATEGENERATOR": form["view_state_generator"],
                "__ASYNCPOST": "true",
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$btnCustomerLogin": "Log In Securely",
            },
        }
    async def product_detail(self, _link):
        if not _link: return None
        headers = {
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1',
            'Sec-Fetch-Dest': 'document',
            'sec-ch-ua': '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        response = await self.session.get(_link, headers=headers)
        dom = scrapy.Selector(text= await response.text())
        sku = extractContent(dom, '//meta[@property="og:mpn"]/@content')
        print(f'Product: {_link} / SKU: {sku}')
        return sku
    async def orderDetail(self, order_history):     
        _link = order_history["order_detail_link"]
        order = dict()

        headers = {
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1',
            'Sec-Fetch-Dest': 'document',
            'sec-ch-ua': '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'Accept-Language': 'en-US,en;q=0.9',
        }

        response = await self.session.get(_link, headers=headers)
        dom = scrapy.Selector(text=await response.text())
        table = dom.xpath('//tr[@class="nextCartSubtotal"]/..')
        order["subtotal"] = extractContent(table, './tr[@class="nextCartSubtotal"]/td[contains(@id, "_tdSubtotalPrice")]//text()')
        order["shipping "] = extractContent(table, './tr[@class="nextShipping"]/td[contains(@id, "_tdShippingPrice")]//text()')
        order["tax"] = extractContent(table, './tr[@class="nextSalesTax"]/td[contains(@id, "_tdSalesTaxPrice")]//text()')
        order["grandtotal"] = extractContent(table, './tr[@class="nextCartTotal"]/td[contains(@id, "_tdTotalPrice")]//text()')
        order["products"] = list()        
        for tr in table.xpath('./tr'):
            if tr.xpath('./@class'): continue
            product = dict()
            product["qty"] = extractContent(tr, './td[1]//text()')
            product["name"] = extractContent(tr, './td[3]/span[@class="nextCartProdText"]/a//text()')
            product["unit_price"] = extractContent(tr, './td[5]//text()')
            product["price"] = product["unit_price"]
            product["ext_price"] = extractContent(tr, './td[6]//text()')            
            product["status"] = extractContent(tr, './td[7]//text()')
            product["vendor"] = self.vendor.to_dict()
            product["product_url"] = extractContent(tr, './td[3]/span[@class="nextCartProdText"]/a/@href')
            if product["product_url"] in self.product_skus:
                product["product_id"] = self.product_skus[product["product_url"]]
            else:
                product["product_id"] = await self.product_detail(product["product_url"])
                if product["product_id"]:
                    self.product_skus[product["product_url"]] = product["product_id"]
            product["images"]= []
            # product["product_id"] = "TESTEOFSK25MMQWE"
            # product["product_url"] =""

            if not product["status"]: continue
            order["products"].append({
                "product":product, 
                "quantity": product.pop("qty"),
                "unit_price": product.pop("unit_price")
            })

        return order

    @semaphore_coroutine
    async def get_order(self, sem, order, office=None) -> dict:
        print(" === get order ==", office, order)
        order_dict=await self.orderDetail(order_history=order)
        order_dict.update(order)
        order_dict.update({"currency":"USD"})
        print(order_dict)
        
        # await self.resolve_product_urls(
        #     [order_product["product"]["product_id"] for order_product in order["products"]]
        # )
        # for order_product in order["product"]:
        #     order_product["product"]["url"] = self.product_urls[order_product["product"]["product_id"]]

        # await self.get_missing_products_fields(
        #     order["products"],
        #     fields=(
        #         "description",
        #         "images",
        #         "category",
        #     ),
        # )
        if office:
            await self.save_order_to_db(office, order=Order.from_dict(order_dict))
        return order


    @catch_network
    async def get_orders(
        self,
        office=None,
        perform_login=False,
        from_date: Optional[datetime.date] = None,
        to_date: Optional[datetime.date] = None,
        completed_order_ids: Optional[List[str]] = None,
    ) -> List[Order]:
        sem = asyncio.Semaphore(value=2)
        url = "https://store.edgeendo.com/account.aspx"
        if perform_login:
            await self.login()
        results=[]
        async with self.session.get(url, headers=ORDER_HEADERS) as response:
            tasks = []
            dom = scrapy.Selector(text=await response.text())
            for tr_ele in dom.xpath(
                '//table[@id="ctl00_ctl00_cphMain_cphMain_oltOrderList_gvOrders"]//tr[contains(@class, "OrderRow")]'
            ):
                order_history = dict()
                order_history["order_id"] = extractContent(tr_ele, './td[1]/span[@id]//text()')
                order_history["order_date"] = extractContent(tr_ele, './td[2]//text()')
                order_history["status"] = extractContent(tr_ele, './td[3]//text()')
                order_history["billing_status"] = extractContent(tr_ele, './td[4]//text()')
                order_history["total_amount"] = extractContent(tr_ele, './td[5]//text()')
                order_detail_link = extractContent(tr_ele, './td[1]/span[@id]/a/@href')
                order_history["order_detail_link"] = order_detail_link
                results.append(order_history)
            
            tasks=[]
            print("===========33434============")
            print(completed_order_ids)
            for order_data in results:
                print("================= #1 ===")
                print(order_data, from_date, to_date)
                month, day, year= order_data["order_date"].split("/")                
                order_date = datetime.date(int(year), int(month), int(day))
                order_data["order_date"] = order_date
                if from_date and to_date and (order_date < from_date or order_date > to_date):
                    continue

                if completed_order_ids and str(order_data["order_id"]) in completed_order_ids:
                    continue

                tasks.append(self.get_order(sem, order_data, office))
            print("================= #2 ===")
            print(tasks)
            if tasks:
                orders = await asyncio.gather(*tasks)
                return [Order.from_dict(order) for order in orders if isinstance(order, dict)]
            else:
                return []        

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0, sort_by="price", office_id=None
    ) -> ProductSearch:
        return await self._search_products_from_table(query, page, min_price, max_price, sort_by, office_id)

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        vendor_order_detail = {
            "retail_amount": "",
            "savings_amount": "",
            "subtotal_amount": "",
            "shipping_amount": "",
            "tax_amount": "",
            "total_amount": "",
            "payment_method": "",
            "shipping_address": "",
        }
        vendor_slug: str = self.vendor.slug
        return {
            vendor_slug: {
                **vendor_order_detail,
                **self.vendor.to_dict(),
            },
        }
