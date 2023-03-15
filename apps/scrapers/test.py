import asyncio
import os

from aiohttp import ClientSession, ClientTimeout


def get_testing_data():
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
            "invoice_data": {
                "invoice_link": "https://www.net32.com/account/orders/invoice/35222736",
                "order_id": "35222736",
            },
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
            "username": os.getenv("DARBY_USERNAME"),
            "password": os.getenv("DARBY_PASSWORD"),
            "invoice_data": {
                "invoice_link": "https://www.darbydental.com/scripts/invoicedownload.ashx?"
                "invno=9743471&id=416135630f1df27f297dba23b80f2227edf78a73cffec84448dd70d90ee7f4a4",
            },
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
            "invoice_data": {
                "invoice_link": "https://www.pattersondental.com/DocumentLibrary/Invoice?"
                "invoiceNumber=3018684279&customerNumber=410201838",
            },
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
            "username": os.getenv("ULTRADENT_USERNAME"),
            "password": os.getenv("ULTRADENT_PASSWORD"),
            "invoice_data": {"invoice_link": "", "order_id": "11678713"},
        },
        "benco": {
            "username": os.getenv("BENCO_USERNAME"),
            "password": os.getenv("BENCO_PASSWORD"),
            "invoice_data": {"invoice_link": "https://shop.benco.com/PurchaseHistory/InvoicePDFByInvoiceNum/1R763393"},
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
        "amazon": {
            "username": os.getenv("AMAZON_USERNAME"),
            "password": os.getenv("AMAZON_PASSWORD"),
            "products": [
                {
                    "product_id": "",
                    "product_url": "",
                    "quantity": 1,
                },
            ],
        },
        "implant_direct": {
            "username": os.getenv("IMPLANT_DIRECT_USERNAME"),
            "password": os.getenv("IMPLANT_DIRECT_PASSWORD"),
            "invoice_data": {
                "invoice_link": "https://store.implantdirect.com/us/en/customer/order/print/id/0041532869/",
                "order_id": "1641753",
            },
        },
        "edge_endo": {
            "username": os.getenv("EDGE_ENDO_USERNAME"),
            "password": os.getenv("EDGE_ENDO_PASSWORD"),
            "invoice_data": {
                "invoice": "https://store.edgeendo.com/accountinvoice.aspx?RowID=634931",
                "order_id": "634931",
            },
        },
        "dental_city": {
            "username": os.getenv("DENTAL_CITY_USERNAME"),
            "password": os.getenv("DENTAL_CITY_PASSWORD"),
            "invoice_data": {
                "invoice_link": "https://www.dentalcity.com/profile/invoicedetails?invoiceid=99533480",
            },
        },
    }


async def test_download_invoices(vendors):
    from apps.scrapers.scraper_factory import ScraperFactory

    testing_data = get_testing_data()
    tasks = []
    async with ClientSession(timeout=ClientTimeout(30)) as session:
        for vendor in vendors:
            scraper_testing_data = testing_data[vendor.slug]
            scraper = ScraperFactory.create_scraper(
                vendor=vendor,
                session=session,
                username=scraper_testing_data["username"],
                password=scraper_testing_data["password"],
            )
            tasks.append(scraper.download_invoice(**scraper_testing_data["invoice_data"]))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for vendor, result in zip(vendors, results):
            with open(f"{vendor.slug}.pdf", "wb") as f:
                f.write(result)


async def test_get_orders(vendors):
    from apps.scrapers.scraper_factory import ScraperFactory

    testing_data = get_testing_data()
    tasks = []
    async with ClientSession(timeout=ClientTimeout(30)) as session:
        for vendor in vendors:
            scraper_testing_data = testing_data[vendor.slug]
            scraper = ScraperFactory.create_scraper(
                vendor=vendor,
                session=session,
                username=scraper_testing_data["username"],
                password=scraper_testing_data["password"],
            )
            tasks.append(scraper.get_orders(perform_login=True))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        print(results)


if __name__ == "__main__":
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    from dotenv import load_dotenv

    load_dotenv()

    from apps.accounts.models import Vendor

    testing_scrapers = [
        "net_32",
        "ultradent",
        "benco",
        "darby",
        "dental_city",
        "implant_direct",
        "edge_endo",
        "patterson",
    ]
    vendors = Vendor.objects.filter(slug__in=testing_scrapers)
    # asyncio.run(test_get_orders(vendors))
    asyncio.run(test_download_invoices(vendors))
