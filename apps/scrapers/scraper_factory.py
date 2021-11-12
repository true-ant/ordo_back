import asyncio
import datetime
import os
from typing import Optional

from aiohttp import ClientSession
from dotenv import load_dotenv

from apps.common.utils import group_products, group_products_from_search_result
from apps.scrapers.benco import BencoScraper
from apps.scrapers.darby import DarbyScraper
from apps.scrapers.errors import VendorNotSupported
from apps.scrapers.henryschein import HenryScheinScraper
from apps.scrapers.net32 import Net32Scraper
from apps.scrapers.patterson import PattersonScraper
from apps.scrapers.schema import Product
from apps.scrapers.ultradent import UltraDentScraper

SCRAPERS = {
    "henry_schein": HenryScheinScraper,
    "net_32": Net32Scraper,
    "ultradent": UltraDentScraper,
    "darby": DarbyScraper,
    "patterson": PattersonScraper,
    "benco": BencoScraper,
}


class ScraperFactory:
    @classmethod
    def create_scraper(
        cls,
        *,
        vendor,
        session: ClientSession,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        if vendor.slug not in SCRAPERS:
            raise VendorNotSupported(vendor.slug)

        return SCRAPERS[vendor.slug](session, vendor, username, password)


def get_scraper_data():
    return {
        "henry_schein": {
            "username": os.getenv("HENRY_SCHEIN_USERNAME"),
            "password": os.getenv("HENRY_SCHEIN_PASSWORD"),
            "products": [
                # {
                #     "product_id": "3840072",
                #     "product_url": "https://www.henryschein.com/us-en/dental/p/restorative-cosmetic"
                #     "/articulating/articulating-paper-40-microns/3840072",
                #     "quantity": 20,
                # },
                {"product_id": "1045452", "quantity": 1, "product_unit": "BX"},
                {"product_id": "3780394", "quantity": 1, "product_unit": "EA"},
                {"product_id": "1280024", "quantity": 1, "product_unit": "BX"},
                {"product_id": "3780386", "quantity": 1, "product_unit": "PK"},
                {"product_id": "9004578", "quantity": 3, "product_unit": "PK"},
                # {"product_id": "1126865", "quantity": 1, "product_unit": ""},
                # {"product_id": "1019278", "quantity": 6, "product_unit": ""},
                # {"product_id": "5430154", "quantity": 2, "product_unit": ""},
                # {"product_id": "5430262", "quantity": 2, "product_unit": ""},
                # {"product_id": "7740131", "quantity": 2, "product_unit": ""},
                # {"product_id": "1073642", "quantity": 2, "product_unit": ""},
                # {"product_id": "1127015", "quantity": 5, "product_unit": ""},
                # {"product_id": "7211022", "quantity": 1, "product_unit": ""},
                # {"product_id": "2220860", "quantity": 1, "product_unit": ""},
                # {"product_id": "1014060", "quantity": 1, "product_unit": ""},
                # {
                #     "product_id": "4434033",
                #     "product_url": "https://www.henryschein.com/us-en/dental/p/infection-control-products"
                #     "/protective-eyewear/visor-shield-kit-medium/4434033",
                #     "quantity": 1,
                # },
                # {
                #     "product_id": "5430231",
                #     "product_url": "https://www.henryschein.com/us-en/dental/p/preventive"
                #     "/toothbrushes/colgate-pj-masks-toothbrush/5430231",
                #     "quantity": 10,
                # },
            ],
        },
        "net_32": {
            "username": os.getenv("NET32_USERNAME"),
            "password": os.getenv("NET32_PASSWORD"),
            "products": [
                # {
                #     "product_id": "113866",
                #     "product_url": "https://www.net32.com/ec/house-brand-premium-nitrile-exam-gloves-small-d-113866",
                #     "quantity": 1,
                # },
                # {
                #     "product_id": "149881",
                #     "product_url": "https://www.net32.com/ec/caviwipes-12-towelettes-large-6-x-675-d-149881",
                #     "quantity": 1,
                # },
                {
                    "product_id": "101047",
                    "quantity": 1,
                },
                {
                    "product_id": "147024",
                    "quantity": 1,
                },
                {
                    "product_id": "138937",
                    "quantity": 1,
                },
                {
                    "product_id": "40817",
                    "quantity": 1,
                },
            ],
        },
        "darby": {
            "username": os.getenv("DARBY_SCHEIN_USERNAME"),
            "password": os.getenv("DARBY_SCHEIN_PASSWORD"),
            "products": [
                {
                    "product_id": "323-3644",
                    "product_url": "https://www.darbydental.com/categories/Infection-Control"
                    "/Sterilization-Bags--Pouches--and-Tubing/CSR-Sterilization-Wrap/3233644",
                    "quantity": 1,
                },
                {
                    "product_id": "5250698",
                    "product_url": "https://www.darbydental.com/categories/Preventive-Products"
                    "/Toothbrushes/Oral-B-Orthodontic-Brush/5250698",
                    "quantity": 1,
                },
            ],
        },
        "patterson": {
            "username": os.getenv("PATTERSON_USERNAME"),
            "password": os.getenv("PATTERSON_PASSWORD"),
            "products": [
                {
                    "product_id": "PIF_63718",
                    "product_url": "https://www.pattersondental.com/Supplies/ProductFamilyDetails/PIF_63718?mc=0",
                },
                {
                    "product_id": "PIF_857369",
                    "product_url": "https://www.pattersondental.com/Supplies/ItemDetail/071110139",
                },
            ],
        },
        "ultradent": {
            "username": os.getenv("ULTRADENT_SCHEIN_USERNAME"),
            "password": os.getenv("ULTRADENT_SCHEIN_PASSWORD"),
        },
        "benco": {
            "username": os.getenv("BENCO_USERNAME"),
            "password": os.getenv("BENCO_PASSWORD"),
            "products": [
                # {
                #     "product_id": "2127-717",
                #     "product_url": "https://shop.benco.com/Product/2127-717/turbosensor-ultrasonic-scaler",
                #     "quantity": 2,
                # },
                # {
                #     "product_id": "2452-311",
                #     "product_url": "https://shop.benco.com/Product/2452-311"
                #     "/periosonic-multi-fluid-irrigator#product-detail-tab",
                #     "quantity": 3,
                # },
                {
                    "product_id": "4556-394",
                    "product_url": "https://shop.benco.com/Product/2452-311"
                    "/periosonic-multi-fluid-irrigator#product-detail-tab",
                    "quantity": 1,
                },
            ],
        },
    }


def get_test_products(scraper_name):
    base_data = get_scraper_data()
    return [
        {
            "product_id": product["product_id"],
            "product_unit": product["product_unit"],
            "quantity": product["quantity"],
        }
        for product in base_data[scraper_name]["products"]
    ]


def get_task(scraper, scraper_name, test="login", **kwargs):
    base_data = get_scraper_data()
    if test == "login":
        return scraper.login()
    elif test == "order_history":
        office = kwargs.get("office")
        return scraper.get_orders(office, perform_login=True)
    elif test == "order_history_date_range":
        office = kwargs.get("office")
        orders_from_date = datetime.date(year=2021, month=9, day=1)
        orders_to_date = datetime.date(year=2021, month=9, day=1)
        return scraper.get_orders(office, perform_login=True, from_date=orders_from_date, to_date=orders_to_date)
    elif test == "create_order":
        return scraper.create_order(get_test_products(scraper_name))
    elif test == "search_product":
        return scraper.search_products(query="bite registration", page=1)
    elif test == "download_invoice":
        return scraper.download_invoice(
            "https://www.darbydental.com/scripts/invoicedownload.ashx?"
            "invno=9743471&id=416135630f1df27f297dba23b80f2227edf78a73cffec84448dd70d90ee7f4a4",
            None,
        )
    elif test == "get_product":
        return scraper.get_product(
            product_id=base_data[scraper_name]["products"][0]["product_id"],
            product_url=base_data[scraper_name]["products"][0]["product_url"],
            perform_login=True,
        )
    elif test == "add_product_to_cart":
        products = get_test_products(scraper_name)
        product = {"product_id": "114303", "quantity": 1}
        return scraper.add_product_to_cart(product, perform_login=True)
    elif test == "add_products_to_cart":
        products = get_test_products(scraper_name)
        return scraper.add_products_to_cart(products)
    elif test == "clear_cart":
        return scraper.clear_cart()
    elif test == "remove_product_from_cart":
        # products = get_test_products(scraper_name)
        # return scraper.remove_product_from_cart(products[0]["product_id"])
        return scraper.remove_product_from_cart("2288210", perform_login=True, use_bulk=False)
    elif test == "get_all_products_v2":
        office = kwargs.get("office")
        return scraper.get_all_products_v2(office)


async def main(office, vendors):
    scraper_names = ["ultradent"]
    base_data = get_scraper_data()
    tasks = []
    async with ClientSession() as session:
        for scraper_name in scraper_names:
            scraper_data = base_data[scraper_name]
            vendor = [vendor for vendor in vendors if vendor.slug == scraper_name][0]
            scraper = ScraperFactory.create_scraper(
                vendor=vendor,
                session=session,
                username=scraper_data["username"],
                password=scraper_data["password"],
            )
            tasks.append(get_task(scraper, scraper_name, "order_history", office=office))

        results = await asyncio.gather(*tasks, return_exceptions=True)
    # products = [
    #     {
    #         "product_id": "2290224",
    #         "quantity": 1,
    #     },
    #     {
    #         "product_id": "1125510",
    #         "quantity": 1,
    #     },
    #     {
    #         "product_id": "1125511",
    #         "quantity": 1,
    #     },
    #     {
    #         "product_id": "2288210",
    #         "quantity": 1,
    #     },
    #     {
    #         "product_id": "5619254",
    #         "quantity": 1,
    #     },
    #     {
    #         "product_id": "1238703",
    #         "quantity": 1,
    #     },
    # ]

    print(results)


async def search_products(mock=True):
    tasks = []
    if mock:
        net32_product_names = [
            "Septocaine Articaine 4% with Epinephrine 1:100,000. Box of 50 - 1.7 mL",
            "Septocaine Articaine HCl 4% with Epinephrine 1:200,000. Box of 50 - 1.7 mL",
            "Orabloc Articaine HCl 4% with Epinephrine 1:100,000 Injection Cartridges, 1.8",
            "House Brand Articaine HCl 4% with Epinephrine 1:100,000 Injection Cartridges",
            "Orabloc Articaine HCl 4% with Epinephrine 1:200,000 Injection Cartridges, 1.8",
            "Cook-Waite Zorcaine (Articaine Hydrochloride 4%) Local Anesthetic",
            "House Brand Articaine HCl 4% with Epinephrine 1:200,000 Injection Cartridges",
        ]
        net32_products = [
            Product.from_dict({"product_id": f"net32_{i}", "name": product_name, "vendor": {"slug": "net32"}})
            for i, product_name in enumerate(net32_product_names)
        ]
        henry_product_names = [
            "Septocaine Articaine HCl 4% Epinephrine 1:200,000 50/Bx",
            "Articadent Articaine HCl 4% Epinephrine 1:100,000 50/Bx",
            "Articaine HCl 4% Epinephrine 1:100,000 50/Bx",
            "Orabloc Articaine HCl 4% Epinephrine 1:200,000 50/Bx",
            "Articaine HCl 4% Epinephrine 1:200,000 50/Bx",
        ]
        henry_products = [
            Product.from_dict({"product_id": f"henry_{i}", "name": product_name, "vendor": {"slug": "henry"}})
            for i, product_name in enumerate(henry_product_names)
        ]
        benco_product_names = [
            "Septocaine® Articaine HCl 4% and Epinephrine 1:200,000 Silver Box of 50",
            "Septocaine® Articaine HCl 4% and Epinephrine 1:100,000 Gold Box of 50",
            "SNAP Liquid Monomer 4oz.",
            "Hemodent® Liquid 10cc",
            "IRM Ivory Powder Immediate Restorative Material 38gm",
            "Wizard Wedges® Matrix Small Wedges Pack of 500",
            "Benco Dental™ Non-Skid Base Mix Pads 3” x 3” Pad of 50 Sheets",
            "Dr. Thompson's Applicator Pack of 100",
            'Econoback™ Patient Bib 13" x 19" Blue 3-Ply Case of 500',
            'Benco Dental™ Cotton Tip Applicators 6" Box of 1000',
            "Cook-Waite Lidocaine 1:100,000 Red Box of 50",
            "Jeltrate® Alginate Impression Material Fast Set Pink 1 pound package",
            "IRM COMB P&L IVORY",
            "Dental Floss Waxed Mint 200yd Refill",
        ]
        benco_products = [
            Product.from_dict({"product_id": f"benco_{i}", "name": product_name, "vendor": {"slug": "benco"}})
            for i, product_name in enumerate(benco_product_names)
        ]
        results = [net32_products, henry_products, benco_products]
        products = group_products(results)
        print(products)
    else:
        base_data = get_scraper_data()
        async with ClientSession() as session:
            for scraper_name, scraper_data in base_data.items():
                if scraper_name not in ["henry_schein", "net_32"]:
                    continue
                scraper = ScraperFactory.create_scraper(
                    vendor=scraper_data["vendor"],
                    session=session,
                    username=scraper_data["username"],
                    password=scraper_data["password"],
                )
                tasks.append(scraper.search_products(query="Septocaine", page=1))
            results = await asyncio.gather(*tasks, return_exceptions=True)

        meta, products = group_products_from_search_result(results)
        print(meta)
        print(products)


def test_search_products():
    from apps.orders.models import Product as ProductModel

    henry_products = ProductModel.objects.filter(tags__keyword__iexact="Septocaine", vendor_id=1)
    net_products = ProductModel.objects.filter(tags__keyword__iexact="Septocaine", vendor_id=2)
    group_products([henry_products, net_products], model=True)


if __name__ == "__main__":
    import time

    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    load_dotenv()

    from apps.accounts.models import Vendor
    from apps.orders.models import Office

    vendors = Vendor.objects.all()
    office = Office.objects.first()
    start_time = time.perf_counter()
    # asyncio.run(main(office, vendors))
    # asyncio.run(search_products())
    test_search_products()
    print(time.perf_counter() - start_time)
