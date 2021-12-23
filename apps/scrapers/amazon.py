import logging

from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Product
from apps.types.scraper import ProductSearch

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

SEARCH_HEADERS = {
    "authority": "www.amazon.com",
    "rtt": "250",
    "downlink": "10",
    "ect": "4g",
    "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="96", "Google Chrome";v="96"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.93 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "none",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}


class AmazonScraper(Scraper):
    BASE_URL = "https://www.amazon.com"

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        url = f"{self.BASE_URL}/s"
        page_size = 16
        params = {"k": query, "page": page, "ref": "nb_sb_noss"}

        async with self.session.get(url, headers=SEARCH_HEADERS, params=params) as resp:
            text = await resp.text()
            response_dom = Selector(text=text)

        total_size_str = response_dom.xpath("//span[@data-component-type='s-result-info-bar']//h1//span/text()").get()
        try:
            total_size_str = total_size_str.split("of", 1)[1]
            total_size_str = self.remove_thousands_separator(self.extract_amount(total_size_str))
            total_size = int(total_size_str)
        except ValueError:
            total_size = 0
        products = []
        for product_dom in response_dom.xpath(
            '//div[contains(@class, "s-result-list")]/div[contains(@class, "s-result-item")]'
        ):
            product_id = product_dom.xpath("./@data-asin").get()  # asin
            if not product_id:
                continue

            product_name = product_dom.xpath(".//h2//text()").get()
            product_url = product_dom.xpath(".//h2/a/@href").get()
            product_price = product_dom.xpath('.//span[@class="a-price"]/span[@class="a-offscreen"]//text()').get()
            if product_price:
                product_price = product_price.strip("$")

            product_image = product_dom.xpath('.//span[@data-component-type="s-product-image"]//img/@src').get()
            products.append(
                {
                    "product_id": product_id,
                    "product_unit": "",
                    "name": product_name,
                    "description": "",
                    "url": f"{self.BASE_URL}{product_url}",
                    "images": [
                        {
                            "image": product_image,
                        }
                    ],
                    "price": product_price,
                    "vendor": self.vendor.to_dict(),
                }
            )

        next_page_button = response_dom.xpath(".//a[contains(@class, 's-pagination-next')]")
        last_page = not bool(next_page_button)

        return {
            "vendor_slug": self.vendor.slug,
            "total_size": total_size,
            "page": page,
            "page_size": page_size,
            "products": [Product.from_dict(product) for product in products],
            "last_page": last_page,
        }
