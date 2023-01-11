import os
import re
import csv
import requests

from scrapy import Selector

UESRNAME = 'kdg@kantordentalgroup.com'
PASSWORD = 'Happy16!'
UESR_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'


class SkydentalsupplySpider():
    vendor_slug = "skydental"
    base_url = 'https://www.skydentalsupply.com'
    login_url = 'https://www.skydentalsupply.com/index.php'
    cookies = {}

    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Host': 'www.skydentalsupply.com',
        'Origin': 'https://www.skydentalsupply.com',
        'Referer': 'https://www.skydentalsupply.com/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'sec-ch-ua': '"Google Chrome";v="107", "Chromium";v="107", "Not=A?Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'User-Agent': UESR_AGENT,
        'X-Requested-With': 'XMLHttpRequest',
    }

    base_item = {
        "product_id": "",
        "name": "",
        "url": "",
        "images": "",
        "price": "",
        "promo": "",
        "category": "",
    }

    def __init__(self):
        super().__init__()
        if os.path.exists(f'{self.vendor_slug}.csv'):
            os.remove(f'{self.vendor_slug}.csv')

    def generate_cooke(response_data):
        """
        This is to generate the cookie string with incoming response data.
        """
        cookie = f'''
            ADR_SESS_ID=3634314; ADR_SESS_UID=8aa133f63970ec3b4595e769faa6051e; _gcl_au=1.1.62805491.1668545331; ln_or=d; _ga=GA1.2.508460996.1668545332; _gid=GA1.2.876148334.1668545332; _fbp=fb.1.1668545331607.202268083; WEBCARTAUTOLOGIN_NEW=40af759ba7267e58b4e40b06cb9bb6ea
        '''

    def run(self):
        if os.path.exists(f"./promotions/{self.vendor_slug}.csv"):
            os.remove(f"./promotions/{self.vendor_slug}.csv")
        payload = {
            'DATA[EMAIL]': UESRNAME,
            'DATA[PASSWORD1]': PASSWORD,
            'DATA[REMEMBER_ME]': '1',
            'section': 'login',
            'ac': 'login',
            'ACC_TPY': 'CUSTOMERS',
            'userid': '',
            'json': '1'
        }
        response = requests.post(self.login_url, headers=self.headers, data=payload)

        if not response.ok:
            print("Authentication failed")
            return

        self.cookies = response.cookies.get_dict()

        response = requests.get(f'{self.base_url}/products',
                                headers=self.headers,
                                cookies=self.cookies)

        self.parse(Selector(text=response.text))


    def parse(self, response):
        promoted_products = response.xpath('//div[@class="discountline"]')
        for product in promoted_products:
            root_element = product.xpath('..')[0]
            product_link = root_element.xpath('.//a/@href').get()
            print(f'===Scraping a product===: {product_link}')
            prodcut_res = requests.get(product_link,
                                       headers=self.headers,
                                       cookies=self.cookies)
            if not prodcut_res.ok:
                print(f'Request Error in {product_link}')
                continue
            self.parse_product(Selector(text=prodcut_res.text))

        next_page = response.xpath('//li[@class="page-item"]/a[contains(text(), "→")]/@href').get()

        if next_page:
            next_res = requests.get(next_page,
                                    headers=self.headers,
                                    cookies=self.cookies)
            if not next_res.ok:
                print(f'Next page request error: {next_page}')
                return
            self.parse(Selector(text=next_res.text))

    def parse_product(self, response):
        script_data = response.xpath('//script[contains(., "_Settings")]//text()').get()

        item = self.base_item.copy()

        name = re.search('name: "(.+?)"', script_data)
        item['name'] = name.group(1) if name else ''

        sku = re.search('sku: "(.+?)"', script_data)
        item['product_id'] = sku.group(1) if sku else ''

        img = re.search('img: "(.+?)"', script_data)
        item['images'] = img.group(1) if img else ''

        category = re.search('category: "(.+?)"', script_data)
        item['category'] = category.group(1) if category else ''

        url = re.search('url: "(.+?)"', script_data)
        item['url'] = url.group(1) if url else ''

        prices = response.xpath('//div[contains(@class, "zoom_properties")]//span[@class="products__list__item__offer__price__value"]//text()').getall()
        item['price'] = ''.join([i.strip() for i in prices])

        promotions= response.xpath('//div[@class="row"]//div[@class="discountline"]//text()').getall()
        item['promo'] = '\n'.join([i.strip() for i in promotions])

        self.write_csv(item)


    def write_csv(self, item):
        is_file = os.path.exists(f'./promotions/{self.vendor_slug}.csv')

        with open(f'./promotions/{self.vendor_slug}.csv', "a", encoding="utf-8-sig", newline="") as result_f:
            fieldnames = item.keys()
            writer = csv.DictWriter(result_f, fieldnames=fieldnames)
            if not is_file:
                writer.writeheader()
            writer.writerow(item)


if __name__ == "__main__":
    SkydentalsupplySpider().run()
