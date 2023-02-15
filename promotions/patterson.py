import csv
import logging
import os
import re
import time

import requests
from scrapy import Selector


class PattersonSpider:
    vendor_slug = "patterson"
    session = requests.Session()
    baseItem = {"product_id": "", "name": "", "url": "", "images": "", "price": "", "promo": "", "FreeGood": ""}

    headers = {
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, \
            like Gecko) Chrome/99.0.4844.51 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,\
            */*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
        "Sec-Fetch-Dest": "document",
        "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
    }

    def textParser(self, element):
        if not element:
            return ""
        text = re.sub(r"\s+", " ", " ".join(element.xpath(".//text()").extract()))
        return text.strip() if text else ""

    def run(self):
        response = self.session.get("https://www.pattersondental.com/supplies/deals", headers=self.headers)
        return self.parse_products(Selector(text=response.text))

    def parse_products(self, response):
        results = []
        for product in response.xpath(
            '//table[@aria-label="Search Results Table"]//tr//div[@ng-controller="SearchResultsController"]'
        ):
            product_link = (
                "https://www.pattersondental.com"
                + product.xpath(
                    './div[contains(@class, "listViewDescriptionWrapper")]//a[@class="itemTitleDescription"]/@href'
                ).get()
            )
            if "ProductFamilyDetails" in product_link:
                self.parse_family_products(product_link)
            else:
                item = self.baseItem.copy()
                item["product_id"] = product.xpath('.//input[@name="AddToCart"]/@data-objectid').get()
                item["name"] = self.textParser(
                    product.xpath(
                        './div[contains(@class, "listViewDescriptionWrapper")]//a[@class="itemTitleDescription"]'
                    )
                )
                item["url"] = product_link
                images = product.xpath('./div[contains(@class, "listViewImageWrapper")]/img/@src').extract()
                item["images"] = ";".join(images)

                promo_ele = product.xpath(
                    './/span[@class="itemIcons"]/a/span[contains(@data-icontype, "manufacturerPromotionIcon")]'
                )
                if promo_ele:
                    promo_text = self.parse_promo_text(promo_ele)
                    if promo_text:
                        item["promo"] = promo_text

                freegood_ele = product.xpath(
                    './/span[@class="itemIcons"]/a/span[contains(@data-icontype, "autoFreeGoodIcon")]'
                )
                if freegood_ele:
                    freegood_text = self.parse_promo_text(freegood_ele)
                    if freegood_text:
                        item["FreeGood"] = freegood_text

                results.append(item)

        next_page = response.xpath('//ul[@class="pagination"]//a[@aria-label="Next"]/@href').get()

        if next_page:
            link = f"https://www.pattersondental.com{next_page}"
            next_response = self.session.get(link, headers=self.headers)
            next_results = self.parse_products(Selector(text=next_response.text))
            results.extend(next_results)
        return results

    def parse_family_products(self, family_link):
        resp = self.session.get(family_link, headers=self.headers)
        response = Selector(text=resp.text)
        product_name = self.textParser(response.xpath('//div[@id="productFamilyDescriptionHeader"]/h1'))
        for product in response.xpath('//div[@id="productFamilyDetailsGridBody"]'):
            item = self.baseItem.copy()
            item["product_id"] = product.xpath('.//input[@name="checkAllChildQty"]/@value').get()
            item["name"] = product_name + " - " + self.textParser(product.xpath('.//a[@class="itemTitleDescription"]'))
            item["url"] = (
                "https://www.pattersondental.com" + product.xpath('.//a[@class="itemTitleDescription"]/@href').get()
            )
            images = product.xpath(
                './/div[@id="productFamilyDetailsGridBodyColumnOneInnerRowImages"]//img/@src'
            ).extract()
            item["images"] = ";".join(images)

            promo_ele = product.xpath(
                './/span[@class="itemIcons"]/a/span[contains(@class, "manufacturerPromotionIcon")]'
            )
            if promo_ele:
                promo_text = promo_ele.xpath("./@data-title").get()
                if promo_text:
                    item["promo"] = promo_text.strip()

            freegood_ele = product.xpath('.//span[@class="itemIcons"]/a/span[contains(@class, "autoFreeGoodIcon")]')
            if freegood_ele:
                freegood_text = freegood_ele.xpath("./@data-title").get()
                if freegood_text:
                    item["FreeGood"] = freegood_text.strip()

            print(item)
            self.write_csv(item)

    def parse_promo_text(self, ele):
        productfamilykey = ele.xpath("./@data-productfamilykey").get()
        icontype = ele.xpath("./@data-icontype").get()

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Referer": "https://www.pattersondental.com/supplies/deals",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)\
                 Chrome/100.0.4896.75 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="100", "Google Chrome";v="100"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }

        params = {
            "ProductFamilyKey": productfamilykey,
            "IconType": icontype,
            "_": str(int(time.time() * 1000)),
        }

        response = self.session.get(
            "https://www.pattersondental.com/ItemIcons/GetPromotionIconText", headers=headers, params=params
        )
        return response.json()["title"]

    def write_csv(self, item):
        file_exists = os.path.exists(f"./promotions/{self.vendor_slug}.csv")
        with open(f"./promotions/{self.vendor_slug}.csv", "a", encoding="utf-8-sig", newline="") as result_f:
            fieldnames = item.keys()
            writer = csv.DictWriter(result_f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(item)


if __name__ == "__main__":
    logging.basicConfig(level="DEBUG")
    print(PattersonSpider().run())
