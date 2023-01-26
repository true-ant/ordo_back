import csv
import os
import re

import requests
from scrapy import Selector


class UltradentSpider:
    vendor_slug = "ultradent"
    session = requests.Session()
    baseItem = {
        "product_id": "",
        "name": "",
        "url": "",
        "images": "",
        "price": "",
        "promo": "",
    }

    def textParser(self, element):
        if not element:
            return ""
        text = re.sub(r"\s+", " ", " ".join(element.xpath(".//text()").extract()))
        return text.strip() if text else ""

    def run(self):
        if os.path.exists(f"./promotions/{self.vendor_slug}.csv"):
            os.remove(f"./promotions/{self.vendor_slug}.csv")

        headers = {
            "authority": "www.ultradent.com",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,\
                */*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="100", "Google Chrome";v="100"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, \
                like Gecko) Chrome/100.0.4896.75 Safari/537.36",
        }

        response = self.session.get("https://www.ultradent.com/", headers=headers)
        self.parse_products(Selector(text=response.text))

    def parse_products(self, response):
        for product in response.xpath('//div[contains(@class, "promo-wrap")]//li[@class="promo-item"]'):
            item = self.baseItem.copy()
            item["name"] = self.textParser(product.xpath('.//p[@class="product-name"]'))
            item["url"] = "https://www.ultradent.com" + product.xpath("./a[@data-promo-id]/@href").get()
            images = product.xpath('.//span[contains(@class, "thumbnail")]/picture/img/@ data-src').extract()
            item["images"] = ";".join(images)
            item["promo"] = "\n".join(product.xpath('.//p[@class="fine-print"]//text()').extract()).strip()
            self.write_csv(item)

        next_page = response.xpath('//ul[@class="pagination"]//a[@aria-label="Next"]/@href').get()
        if next_page:
            link = f"https://www.ultradentdental.com{next_page}"
            next_response = self.session.get(link, headers=self.headers)
            self.parse_products(Selector(text=next_response.text))

    def write_csv(self, item):
        file_exists = os.path.exists(f"./promotions/{self.vendor_slug}.csv")
        with open(f"./promotions/{self.vendor_slug}.csv", "a", encoding="utf-8-sig", newline="") as result_f:
            fieldnames = item.keys()
            writer = csv.DictWriter(result_f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(item)


if __name__ == "__main__":
    UltradentSpider().run()
