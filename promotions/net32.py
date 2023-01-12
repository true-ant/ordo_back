import csv
import os
import re
import requests
from scrapy import Selector


class Net32Spider():
    vendor_slug = "net_32"
    baseItem = {
        "product_id": "",
        "name": "",
        "url": "",
        "images": "",
        "price": "",
        "promo": "",
    }
    
    def textParser(self, element):
        text = re.sub(r"\s+", " ", " ".join(element.xpath('.//text()').extract()))
        return text.strip() if text else ""

    def get_product(self, page=1):
        headers = {
            'authority': 'www.net32.com',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'origin': 'https://www.net32.com',
            'referer': 'https://www.net32.com/weekly-specials',
            'sec-ch-ua': '"Chromium";v="106", "Google Chrome";v="106", "Not;A=Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36',
        }

        json_data = {
            'searchParam': '',
            'page': page,
            'resultsPerPage': 60,
            'isUgrIdRequired': False,
            'isBuyGetPage': False,
            'filters': [
                {
                    'field': 'availability',
                    'value': 'in stock',
                },
                {
                    'field': 'weekly_special',
                    'value': 'Y',
                },
            ],
            'sorting': [
                {
                    'field': 'ga_item_revenue',
                    'direction': 'desc',
                },
            ],
            'tag': '',
        }

        response = requests.post('https://www.net32.com/rest/neo/search/get-search-results', headers=headers, json=json_data)
        return response.json()


    def run(self):
        if os.path.exists(f"./promotions/{self.vendor_slug}.csv"):
            os.remove(f"./promotions/{self.vendor_slug}.csv")

        products = list()
        next_page = 1
        while True:
            product_response = self.get_product(next_page)
            print(next_page, len(product_response["productDetails"]))
            products += product_response["productDetails"]

            next_page = product_response["pagination"]["nextPage"]
            if not next_page:
                break
            
        self.parse_products(products)

    def parse_products(self, products):
        for product in products:
            item = self.baseItem.copy()
            item["product_id"] = product["mp_id"]
            item["name"] = product["name"]
            item["url"] = "https://www.net32.com"+product["url"]
            item["images"] = "https://www.net32.com/"+product["thumbnailImageUrl"]
            item["price"] = product["bestPrice"]
            if not item["price"]:
                item["price"] = product["price"]
            if not item["price"]:
                item["price"] = product["msrp"]

            print(item)
            self.write_csv(item)

    def write_csv(self, item):
        file_exists = os.path.exists(f"./promotions/{self.vendor_slug}.csv")
        with open(f"./promotions/{self.vendor_slug}.csv", "a", encoding="utf-8-sig", newline="") as result_f:
            fieldnames = item.keys()
            writer = csv.DictWriter(result_f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(item)


if __name__ == "__main__":
    Net32Spider().run()
