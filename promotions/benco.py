import csv
import os
import re
import requests
from scrapy import Selector


class BencoSpider():
    vendor_slug = "benco"
    baseItem = {
        "product_id": "",
        "name": "",
        "url": "",
        "images": "",
        "price": "",
        "promo": "",
        "category": "",
    }
    
    def textParser(self, element):
        if element:
            text = re.sub(r"\s+", " ", " ".join(element.xpath('.//text()').extract()))
            return text.strip() if text else ""
        return ""

    def run(self):
        if os.path.exists(f"./promotions/{self.vendor_slug}.csv"):
            os.remove(f"./promotions/{self.vendor_slug}.csv")
        
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="100", "Google Chrome";v="100"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        }

        response = requests.get('https://shop.benco.com/Search/SearchBigBigDeals?source=BigBigDealsHeaderLink', headers=headers)
        self.parse_products(Selector(text=response.text))
    
    def parse_products(self, response):
        product_ids = list()
        products = dict()
        for product in response.xpath('//div[contains(@class, "product-grid")]/div[@class="product-tile"]'):
            item = self.baseItem.copy()
            item["images"] = product.xpath("./div[contains(@class, 'product-image-area')]/img/@src").get()
            item["name"] = self.textParser(product.xpath(
                "./div[contains(@class, 'product-data-area')]//h4[@itemprop='name']"
            ))
            item_url = product.xpath(
                    "./div[contains(@class, 'product-data-area')]/div[contains(@class, 'title')]//a/@href"
                ).get()
            if item_url: item["url"] = "https://shop.benco.com"+item_url.strip()
            item["product_id"] = self.textParser(product.xpath(
                "./div[contains(@class, 'product-data-area')]//span[@itemprop='sku']"
            ))
            product_ids.append(item["product_id"])
            products[item["product_id"]] = item

        data = {
            "productNumbers": product_ids,
            "pricePartialType": "ProductPriceRow"
        }

        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Content-Type': 'application/json',
            'Origin': 'https://shop.benco.com',
            'Pragma': 'no-cache',
            'Referer': 'https://shop.benco.com/Search?q=H4sIAAAAAAAACk2OTUsDMRCG%2F4rMOace97ZucV0QKUa8iIeYHePQ2aRMJvRQ%2Bt%2BdrkULCSHPfLzPCXYhIXQbBw8hor4Fblihez%2F9%2Fp%2FDYlW4p3R3uVsMXMHB2mb8VexxMFWPjFFxhk4NnT8cjFLawdNCHGRSXGzppeSgZy7HvmkZiogN%2BfZZlbQplQzdlwVYky9N4jXZzpr7iGFGeaK8dzd01TQH%2F12OL1gba%2B3rKGQq111Tjtxm3AlFyukf16EsB0bFIYje4BEzSmDfUkIz%2B7M6%2FwD5lpuKLQEAAA%3D%3D',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="100", "Google Chrome";v="100"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        }

        price_response = requests.post('https://shop.benco.com/Search/GetPricePartialsForProductNumbers', headers=headers, json=data)
        self.parse_price(price_response.json(), products)

        # pagination
        next_page_ele = response.xpath('//div[@id="resultsPager"]//input[@value="Next >"]')
        next_page_ele_class = next_page_ele.xpath('./@class').get()
        if "disabled" not in next_page_ele_class:
            headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
                'Accept-Language': 'en-US,en;q=0.9',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Origin': 'https://shop.benco.com',
                'Pragma': 'no-cache',
                'Referer': 'https://shop.benco.com',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36',
                'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="100", "Google Chrome";v="100"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
            }

            data = {}
            for _ele in response.xpath('//div[@id="resultsPager"]//input[@value="Next >"]/../input[@name]'):
                _key = _ele.xpath('./@name').get()
                _val = _ele.xpath('./@value').get()
                if not _val: _val = ""
                data[_key] = _val

            next_response = requests.post('https://shop.benco.com/Search/ChangePage', headers=headers, data=data)
            self.parse_products(Selector(text=next_response.text))

    def parse_price(self, response, products):
        for id, row in response.items():
            row_dom = Selector(text=row)
            price = self.textParser(row_dom.xpath(
                "//span[@class='selling-price']"
            ))
            if not price:
                price = self.textParser(row_dom.xpath(
                    "//h4[@class='selling-price']/span"
                ))

            products[id]["price"] = price

            products[id]["promo"] = self.textParser(row_dom.xpath(
                '//div[@class="bulk-discounts"]/span[@class="bulk-discount-quantity"]'
            ))

        self.write_csv(list(products.values()))

    def write_csv(self, products):
        if products:
            print(f"Scraped {len(products)} Products")
            file_exists = os.path.exists(f"./promotions/{self.vendor_slug}.csv")
            with open(f"./promotions/{self.vendor_slug}.csv", "a", encoding="utf-8-sig", newline="") as result_f:
                fieldnames = products[0].keys()
                writer = csv.DictWriter(result_f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerows(products)


if __name__ == "__main__":
    BencoSpider().run()
