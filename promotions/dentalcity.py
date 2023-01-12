import csv
import os
import re
import requests
from scrapy import Selector


class DentalcitySpider():
    vendor_slug = "dental_city"
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
        text = re.sub(r"\s+", " ", " ".join(element.xpath('.//text()').extract()))
        return text.strip() if text else ""

    def run(self):
        if os.path.exists(f"./promotions/{self.vendor_slug}.csv"):
            os.remove(f"./promotions/{self.vendor_slug}.csv")
        
        headers = {
            'authority': 'www.dentalcity.com',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="100", "Google Chrome";v="100"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36',
        }

        response = requests.get('https://www.dentalcity.com/category/4/shop-specials', headers=headers)
        self.parse(Selector(text=response.text))
        

    def parse(self, response):
        headers = {
            'authority': 'www.dentalcity.com',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': 'https://www.dentalcity.com/category/4/shop-specials',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="100", "Google Chrome";v="100"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36',
        }
        
        for category in response.xpath('//ul[contains(@class, "categories")]/li[contains(@class, "categoriesdesc")]/a'):
            category_text = category.xpath('./@title').get().split("-")[0].strip()
            category_link = category.xpath('./@href').get()
            category_id = category_link.split("/category/")[1].split("/")[0]

            cat_response = requests.get(category_link, headers=headers)
            self.view_all(Selector(text=cat_response.text), category_id, category_text)

    def view_all(self, response, category_id, category_text):
        view_all_btn_text = response.xpath('//a[@id="showAllLinkHeader"]/@onclick').get()
        all_count = view_all_btn_text.split("ppp_change")[1].split("[")[0].strip('\', ')
        headers = {
            'authority': 'www.dentalcity.com',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'x-requested-with': 'XMLHttpRequest',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.82 Safari/537.36',
            'sec-ch-ua-platform': '"Windows"',
            'origin': 'https://www.dentalcity.com',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://www.dentalcity.com',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        data = {
            'source': 'NarrowSrchData',
            'filter': category_id,
            'cid': '',
            'type': '',
            'search': '',
            'keywordoption': '',
            'fltrdesc': '',
            'hdnCategoryId': category_id,
            'catalogfiltersquerystring': '',
            'hdnSelectedVal': '',
            'hdnFromPrice': '',
            'hdnPageNumber': '1',
            'hdnToPrice': '',
            'hdnCurrentProductIds': '',
            'hdnFilter': category_id,
            'hdndiscountid': '',
            'hdnDisplayType': 'grid',
            'hdnSortType': 'SELLERRECOMMENDATION',
            'hdnSortTypeClicked': 'false',
            'hdnProdPerPage': all_count,
            'searchKeyWordwithinFilter': '',
            'txtSearch': '',
            'txtNarrowSearch': '',
            'hdnSeeMore': '',
            'min_slider_price': '',
            'max_slider_price': '',
        }

        response = requests.post(
            f'https://www.dentalcity.com/widgets-category/gethtml_productlist/{category_id}/html_productlist/300X210?newarrivaldays=30',
            headers=headers, data=data
        )
        self.parse_products(Selector(text=response.text), category_text)

    def parse_products(self, response, category_text):
        for product in response.xpath('//ol[@id="productlisting"]/li[contains(@id, "product_")]//ul[contains(@class, "productitem singleitem")]'):
            item = self.baseItem.copy()
            item["name"] = product.xpath('./li[@class="prod_name_description"]/h3/a/@title').get()
            item["url"] = product.xpath('./li[@class="prod_name_description"]/h3/a/@href').get()
            item["product_id"] = item["url"].split("/product/")[1].split("/")[0]
            item["category"] = category_text
            item["images"] = ";".join(product.xpath('./li[@class="prodimage"]/a/img/@src').extract())
            
            item["price"] = self.textParser(
                product.xpath('./li[@class="actionslink"]//span[@class="aslowasprice"]')
            )
            if "As Low As:" in item["price"]: item["price"] = item["price"].split("As Low As:")[1].strip()
            if not item["price"]:
                item["price"] = self.textParser(
                    product.xpath('.//*[@class="prodprice"]//div[@class="yourpricecontainer"]/span')
                )
            if not item["price"]:
                item["price"] = self.textParser(
                    product.xpath('.//*[@class="prodprice"]//div[@class="listpricecontainer"]/span')
                )

            item["promo"] = "\n".join(product.xpath('.//*[@id="promo-description"]/p//text()').extract())
            
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
    DentalcitySpider().run()
