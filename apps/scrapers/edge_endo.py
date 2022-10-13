import asyncio
import datetime
import traceback
import uuid
import re
import time
from typing import Dict, List, Optional

import scrapy
from aiohttp import ClientSession
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product, ProductCategory, VendorOrderDetail
from apps.scrapers.utils import catch_network, convert_string_to_price, semaphore_coroutine
from apps.types.orders import CartProduct
from apps.types.scraper import ProductSearch

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
    
    def __init__(
        self, 
        session: ClientSession,
        vendor,
        username: Optional[str] = None,
        password: Optional[str] = None,
        ):
        Scraper.__init__(self, session,vendor, username,password)
        self.driver = None
        self.sleepAmount = 10
    
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

    # extract text
    def textParser(self, element):
        text = element.get_attribute("textContent")
        return text.strip() if text else ""

    def scroll_and_click_element(self, element: WebElement):
        # self.driver.execute_script("arguments[0].scrollIntoView(false);", element)
        try:
            element.click()
        except:
            self.driver.execute_script("arguments[0].click();", element)
        
        time.sleep(0.5)

    # create browser
    def setDriver(self):
        user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_3) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/80.0.3987.132 Safari/537.36"
        )

        caps = DesiredCapabilities.CHROME
        caps["pageLoadStrategy"] = "eager"
        # chrome_options = webdriver.ChromeOptions()
        # # chrome_options.add_argument("--headless")
        # chrome_options.add_argument("--disable-dev-shm-usage")
        # chrome_options.add_argument(f"user-agent={user_agent}")
        # chrome_options.add_argument("--log-level=3")
        # driver = webdriver.Chrome(
        #     options=chrome_options,
        #     desired_capabilities=caps,
        # )
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument(f"user-agent={user_agent}")
        options.add_argument("--log-level=3")
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), 
            options=options, 
            desired_capabilities=caps,
        )
        
        driver.set_window_size(1920, 1080)
        print("edge_endo/set_Driver done")
        return driver
    
    def login(self):
        try:
            self.driver.get("https://store.edgeendo.com/login.aspx")
            emailInput = WebDriverWait(self.driver, self.sleepAmount).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        '//input[@name="ctl00$ctl00$cphMain$cphMain$lfBtoC$emlLogin$txtEmail"]'
                    )
                )
            )
            emailInput.clear()
            emailInput.send_keys(self.username)
            time.sleep(0.5)
            
            passInput = WebDriverWait(self.driver, self.sleepAmount).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        '//input[@name="ctl00$ctl00$cphMain$cphMain$lfBtoC$pwdLogin$rtbPassword$txtRestricted"]'
                    )
                )
            )
            passInput.clear()
            passInput.send_keys(self.password)
            time.sleep(0.5)

            loginBtn = WebDriverWait(self.driver, self.sleepAmount).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        '//input[@name="ctl00$ctl00$cphMain$cphMain$lfBtoC$btnCustomerLogin"]'
                    )
                )
            )

            self.scroll_and_click_element(loginBtn)
            time.sleep(5)
            print("edge_endo/login done")
        except:
            traceback.print_exc()
    
    def wait_cart_action(self):
        while True:
            progress_ele = WebDriverWait(self.driver, self.sleepAmount).until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        '//div[contains(@id, "upoCartData_uprProgress")]',
                    )
                )
            )
            progress_style = progress_ele.get_attribute("style")
            if "block" in progress_style:
                time.sleep(3)
                break

    def add_to_cart(self, products):
        for product in products:
            self.driver.get(product["product_url"])
            sku = product["product_id"]
            WebDriverWait(self.driver, self.sleepAmount).until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        '//td[@id="ctl00_ctl00_ctl00_cphMain_cphMain_tdMain"]',
                    )
                )
            )
            if "nextExpressOrderDetailContainer" in self.driver.page_source:
                open_tab_ele = WebDriverWait(self.driver, self.sleepAmount).until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            '//a[@id="__tab_ctl00_ctl00_ctl00_cphMain_cphMain_cphMain_pdtProduct_tcTabs_tpReviewsQuestions3"]'
                        )
                    )
                )
                self.scroll_and_click_element(open_tab_ele)
                
                while True:
                    quantity_ele = WebDriverWait(self.driver, self.sleepAmount).until(
                        EC.presence_of_element_located(
                            (
                                By.XPATH,
                                f'//table[@class="nextExpressOrderSKUTable"]//tr/td[2][contains(text(), "{sku}")]'
                                '/following-sibling::td/span/input[@title="Enter Quantity"]'
                            )
                        )
                    )
                    quantity = int(quantity_ele.get_attribute('value'))

                    if quantity == product["quantity"]:
                        add_to_cart_btn = WebDriverWait(self.driver, self.sleepAmount).until(
                            EC.element_to_be_clickable(
                                (
                                    By.XPATH,
                                    '//div[@class="nextExpressOrderATC"]//input[@type="submit"]'
                                )
                            )
                        )
                        self.scroll_and_click_element(add_to_cart_btn)
                        time.sleep(2)
                        self.wait_cart_action()
                        break
                    else:
                        plus_quantity_ele = WebDriverWait(self.driver, self.sleepAmount).until(
                            EC.element_to_be_clickable(
                                (
                                    By.XPATH,
                                    f'//table[@class="nextExpressOrderSKUTable"]//tr/td[2][contains(text(), "{sku}")]'
                                    '/following-sibling::td/span/a[contains(@id, "Quantity_aIncrementTxt")]'
                                )
                            )
                        )
                        self.scroll_and_click_element(plus_quantity_ele)
            else:
                while True:
                    quantity_ele = WebDriverWait(self.driver, self.sleepAmount).until(
                        EC.presence_of_element_located(
                            (
                                By.XPATH,
                                '//input[@name="ctl00$ctl00$ctl00$cphMain$cphMain$cphMain$pdtProduct$atcTabbed$txtQuantity"]',
                            )
                        )
                    )
                    quantity = quantity_ele.get_attribute('value')

                    if quantity == product["quantity"]:
                        add_to_cart_btn = WebDriverWait(self.driver, self.sleepAmount).until(
                            EC.element_to_be_clickable(
                                (
                                    By.XPATH,
                                    '//input[@name="ctl00$ctl00$ctl00$cphMain$cphMain$cphMain$pdtProduct$atcTabbed$btnAddToCart"]',
                                )
                            )
                        )
                        self.scroll_and_click_element(add_to_cart_btn)
                        time.sleep(2)
                        self.wait_cart_action()
                        break
                    else:
                        plus_quantity_ele = WebDriverWait(self.driver, self.sleepAmount).until(
                            EC.element_to_be_clickable(
                                (
                                    By.XPATH,
                                    '//a[@id="ctl00_ctl00_ctl00_cphMain_cphMain_cphMain_pdtProduct_atcTabbed_aIncrementATCTxt"]',
                                )
                            )
                        )
                        self.scroll_and_click_element(plus_quantity_ele)
        print("edge_endo/add_to_cart done")

    def clear_cart(self):
        try:
            self.driver.get("https://store.edgeendo.com/storefront.aspx")
            clear_cart_ele = WebDriverWait(self.driver, self.sleepAmount).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        '//a[@id="ctl00_ctl00_ctl00_cphMain_ctl00_ctrShoppingCart_lbRemoveAll"]',
                    )
                )
            )
            self.scroll_and_click_element(clear_cart_ele)
            WebDriverWait(self.driver, self.sleepAmount).until(EC.alert_is_present())
            self.driver.switch_to.alert.accept()
            time.sleep(3)
            print("edge_endo/clear_cart Done")
        except TimeoutException:
            pass

    def checkout(self):
        checkoutBtn = None
        try:
            checkoutBtn = self.driver.find_element(
                By.XPATH, '//input[contains(@name, "$cphMain$ctl00$btnCheckOutBottom")]'
            )
        except NoSuchElementException:
            pass

        if not checkoutBtn:
            self.driver.get("https://store.edgeendo.com/storefront.aspx")
            checkoutBtn = WebDriverWait(self.driver, self.sleepAmount*2).until(
                EC.element_to_be_clickable((
                        By.XPATH,
                        '//input[contains(@name, "$cphMain$ctl00$btnCheckOutBottom")]'
                ))
            )
        self.scroll_and_click_element(checkoutBtn)
        continueBtn = WebDriverWait(self.driver, self.sleepAmount).until(
            EC.element_to_be_clickable((
                    By.XPATH,
                    '//input[contains(@name, "$cphMain$uplUpsell$btnClose")]'
            ))
        )
        self.scroll_and_click_element(continueBtn)
        time.sleep(1.5)
        print("edge_endo/checkout done")
    
    def secure_payment(self):
        securepaymentBtn = WebDriverWait(self.driver, self.sleepAmount).until(
            EC.element_to_be_clickable((
                    By.XPATH,
                    '//input[contains(@name, "$cphMain$dbSubmit$btnSubmit")]'
            ))
        )
        self.scroll_and_click_element(securepaymentBtn)
        time.sleep(1)
        print("edge_endo/secure_payment done")


    def real_order(self):
        shipping_address_ele = WebDriverWait(self.driver, self.sleepAmount).until(
            EC.element_to_be_clickable((
                    By.XPATH,
                    '//td[@class="nextInvoiceShipToAddress"]'
            ))
        )
        shipping_address = self.textParser(shipping_address_ele)
        print("Shpping Address:\n", shipping_address)
        
        billing_address_ele = WebDriverWait(self.driver, self.sleepAmount).until(
            EC.element_to_be_clickable((
                    By.XPATH,
                    '//span[contains(@id, "adBillTo_spnAddressDisplay")]'
            ))
        )
        billing_address = self.textParser(billing_address_ele)
        print("Billing Address:\n", billing_address)
        
        subtotal_ele = WebDriverWait(self.driver, self.sleepAmount).until(
            EC.element_to_be_clickable((
                    By.XPATH,
                    '//td[contains(@id, "sctrShipToOrder_tdSubtotalPrice")]'
            ))
        )
        subtotal = convert_string_to_price(self.textParser(subtotal_ele))
        print("Subtotal:\n", subtotal)
        
        tax_ele = WebDriverWait(self.driver, self.sleepAmount).until(
            EC.element_to_be_clickable((
                    By.XPATH,
                    '//td[contains(@id, "sctrShipToOrder_tdSalesTaxPrice")]'
            ))
        )
        tax = convert_string_to_price(self.textParser(tax_ele))
        print("Tax:\n", tax)
        
        shipping_ele = WebDriverWait(self.driver, self.sleepAmount).until(
            EC.element_to_be_clickable((
                    By.XPATH,
                    '//td[contains(@id, "sctrShipToOrder_tdShippingPrice")]'
            ))
        )
        shipping = convert_string_to_price(self.textParser(shipping_ele))
        print("Shipping:\n", shipping)
        
        order_total_ele = WebDriverWait(self.driver, self.sleepAmount).until(
            EC.element_to_be_clickable((
                By.XPATH,
                '//td[contains(@id, "sctrShipToOrder_tdTotalPrice")]'
            ))
        )
        order_total = convert_string_to_price(self.textParser(order_total_ele))
        print("Order Total:\n", order_total)

        # payment option
        invoice_ele = WebDriverWait(self.driver, self.sleepAmount).until(
            EC.element_to_be_clickable((
                By.XPATH,
                '//tr[@id="ctl00_cphMain_piInformation_trInvoicePay"]//label'
            ))
        )
        self.scroll_and_click_element(invoice_ele)
        
        submitBtn = WebDriverWait(self.driver, self.sleepAmount).until(
            EC.element_to_be_clickable((
                    By.XPATH,
                    '//input[contains(@name, "$cphMain$dbOrderSubmit$btnSubmit")]'
            ))
        )
        self.scroll_and_click_element(submitBtn)

        # order number
        ordernum_ele = WebDriverWait(self.driver, self.sleepAmount).until(
            EC.presence_of_element_located((
                By.XPATH,
                '//p[@class="nextOrderConfirmationText"]/b[1]'
            ))
        )
        orderNumber = ordernum_ele.get_attribute("textContent")
        print("Order Number:", orderNumber)

        return shipping_address, shipping, tax, subtotal, order_total, orderNumber

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        print("edge_endo/create_order")
        # loop = asyncio.get_event_loop()
        # self.driver = await loop.run_in_executor(None,self.setDriver)
        # await loop.run_in_executor(None,self.login)
        # await loop.run_in_executor(None,self.clear_cart)
        # await loop.run_in_executor(None,self.add_to_cart, products)

        # self.driver = self.setDriver()
        # self.login()
        # self.clear_cart()
        # self.add_to_cart(products)
        # self.checkout()

        from time import sleep
        sleep(3)

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

    async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False):
        print("edge_endo/confirm_order")
        loop = asyncio.get_event_loop()
        self.driver = await loop.run_in_executor(None,self.setDriver)
        await loop.run_in_executor(None,self.login)
        await loop.run_in_executor(None,self.clear_cart)
        await loop.run_in_executor(None,self.add_to_cart, products)
        await loop.run_in_executor(None,self.checkout)
        
        if fake:
            vendor_order_detail = {
                "retail_amount": "",
                "savings_amount": "",
                "subtotal_amount": "50.84",
                "shipping_amount": "0.00",
                "tax_amount": "3.43",
                "total_amount": "54.27",
                "payment_method": "",
                "shipping_address": "Alexandra KantorColumbine Creek Dentistry",
            }
            return {
                **vendor_order_detail,
                "order_id": f"{uuid.uuid4()}",
            }
        await loop.run_in_executor(None,self.secure_payment)
        shipping_address, shipping, tax, subtotal, order_total, orderNumber = await loop.run_in_executor(None,self.real_order)    

        self.secure_payment()
        shipping_address, shipping, tax, subtotal, order_total, orderNumber = self.real_order()

        vendor_order_detail = {
            "retail_amount": "",
            "savings_amount": "",
            "subtotal_amount": subtotal,
            "shipping_amount": shipping,
            "tax_amount": tax,
            "total_amount": order_total,
            "payment_method": "",
            "shipping_address": shipping_address,
        }
        return {
            **vendor_order_detail,
            "order_id": orderNumber,
        }
