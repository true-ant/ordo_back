import re
import json
import scrapy
import requests
import traceback
from scrapy import Selector

email = "info@columbinecreekdentistry.com"
passw = "Happy16!"

session = requests.Session()
headers = {
    'authority': 'store.implantdirect.com',
    'sec-ch-ua': '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36',
    'accept': '*/*',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-user': '?1',
    'sec-fetch-dest': 'document',
    'referer': 'https://store.implantdirect.com/us/en/',
    'accept-language': 'en-US,en;q=0.9',
}

def extractContent(dom, xpath):
    return re.sub(r"\s+", " ", " ".join(dom.xpath(xpath).extract())).strip()

def getHomePage():
    response = session.get('https://store.implantdirect.com/us/en/', headers=headers)
    print("Home Page:", response.status_code)
    return response

def getLoginPage(login_link):
    response = session.get(login_link, headers=headers)
    print("LogIn Page:", response.status_code)
    return response

def login():
    home_resp = getHomePage()
    home_dom = scrapy.Selector(text=home_resp.text)
    login_link = home_dom.xpath('//ul/li[contains(@class, "authorization-link")]/a/@href').get()
    
    login_resp = getLoginPage(login_link)
    login_dom = scrapy.Selector(text=login_resp.text)
    form_key = login_dom.xpath('//form[@id="login-form"]/input[@name="form_key"]/@value').get()
    form_action = login_dom.xpath('//form[@id="login-form"]/@action').get()

    data = {
        'form_key': form_key,
        'login[username]': email,
        'login[password]': passw,
        'send': ''
    }

    response = session.post(form_action, data=data, headers=headers, proxies={"url": "195.110.59.175:3128"})
    print("Log In POST:", response.status_code)

def getCartPage():
    response = session.get('https://store.implantdirect.com/us/en/checkout/cart/', headers=headers)
    print("Cart Page:", response.status_code)
    return response.text

def clear_cart():
    cart_page = getCartPage()
    dom = Selector(text=cart_page)
    form_key = dom.xpath('//form[@id="form-validate"]//input[@name="form_key"]/@value').get()
    products = dom.xpath('//form[@id="form-validate"]//table[@id="shopping-cart-table"]/tbody[@class="cart item"]')
    data = {
        'form_key': form_key,
        'cart[11143][qty]': '1',
        'cart[11144][qty]': '1',
        'update_cart_action': 'empty_cart',
    }
    for product in products:
        _key = product.xpath('.//input[@data-role="cart-item-qty"]/@name').get()
        _val = product.xpath('.//input[@data-role="cart-item-qty"]/@value').get()
        data[_key] = _val
        print(f"{_key}:{_val}")
    
    if products:
        response = session.post('https://store.implantdirect.com/us/en/checkout/cart/updatePost/', data=data, headers=headers)
        print("Empty Cart POST:", response.status_code)
    else:
        print("Empty Cart: Already Empty")
    
def getProductPage(link):
    response = session.get(link, headers=headers)
    return response.text

def add_to_cart(products):
    add_to_cart_headers = {
        'authority': 'store.implantdirect.com',
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        'content-type': 'multipart/form-data; boundary=----WebKitFormBoundarytvKTimFXuo4R6Xsw',
        'origin': 'https://store.implantdirect.com',
        'referer': 'https://store.implantdirect.com/us/en/surgical-kit-grommet-small-2pk',
        'sec-ch-ua': '"Google Chrome";v="105", "Not)A;Brand";v="8", "Chromium";v="105"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }

    cookies = {
        'form_key': 'l7i7sDRkNglwFRKP',
    }
    
    for product in products:
        product_page = getProductPage(product["link"])
        dom = Selector(text=product_page)
        action_link = dom.xpath('//form[@id="product_addtocart_form"]/@action').get()
        product_id = dom.xpath('//div[@data-product-id]/@data-product-id').get()

        data = f'------WebKitFormBoundarytvKTimFXuo4R6Xsw\r\nContent-Disposition: form-data; name="product"\r\n\r\n{product_id}\r\n------WebKitFormBoundarytvKTimFXuo4R6Xsw\r\nContent-Disposition: form-data; name="selected_configurable_option"\r\n\r\n\r\n------WebKitFormBoundarytvKTimFXuo4R6Xsw\r\nContent-Disposition: form-data; name="related_product"\r\n\r\n\r\n------WebKitFormBoundarytvKTimFXuo4R6Xsw\r\nContent-Disposition: form-data; name="item"\r\n\r\n{product_id}\r\n------WebKitFormBoundarytvKTimFXuo4R6Xsw\r\nContent-Disposition: form-data; name="form_key"\r\n\r\nl7i7sDRkNglwFRKP\r\n------WebKitFormBoundarytvKTimFXuo4R6Xsw\r\nContent-Disposition: form-data; name="qty"\r\n\r\n{product["qty"]}\r\n------WebKitFormBoundarytvKTimFXuo4R6Xsw--\r\n'

        response = session.post(action_link, data=data, headers=add_to_cart_headers, cookies=cookies)
        print(f"Product ({product_id}) added to cart:", response.status_code)

def shipping_infomation(payload):
    post_headers = {
        'authority': 'store.implantdirect.com',
        'pragma': 'no-cache',
        'cache-control': 'no-cache',
        'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
        'x-newrelic-id': 'VQUAU1dTABAHXFhUDgUHXlc=',
        'sec-ch-ua-mobile': '?0',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36',
        'content-type': 'application/json',
        'accept': '*/*',
        'x-requested-with': 'XMLHttpRequest',
        'sec-ch-ua-platform': '"Windows"',
        'origin': 'https://store.implantdirect.com',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-mode': 'cors',
        'sec-fetch-dest': 'empty',
        'referer': 'https://store.implantdirect.com/us/en/checkout/',
        'accept-language': 'en-US,en;q=0.9',
    }

    response = session.post('https://store.implantdirect.com/us/en/rest/us_en/V1/carts/mine/shipping-information', headers=post_headers, json=payload)
    print("Shipping Infomation:", response.status_code)
    return response.json()["totals"]

def proceed_checkout():
    response = session.get('https://store.implantdirect.com/us/en/checkout/', headers=headers)
    print("Checkout Page:", response.status_code)
    response_dom = Selector(text=response.text)
    json_text = response_dom.xpath('//script[contains(text(), "totalsData")]//text()').get().strip()
    json_text = json_text.split("window.checkoutConfig", 1)[1].split("window.customerData", 1)[0].split("window.isCustomerLoggedIn", 1)[0].rsplit("};", 1)[0]
    json_text = json_text.strip("\n\r\t =")
    json_data = json.loads(json_text+"}")

    cartId = json_data["quoteData"]["entity_id"]
    
    shipping_payload = {
        'addressInformation': {
            'shipping_address': {},
            'billing_address': {},
            # shipping_method_code: 
            # - Will Call – Pomona, CA: 38
            # - UPS 2 Day : 31
            # - UPS Overnight : 33
            # - UPS Overnight - AM delivery : 34
            # - UPS Overnight - Saturday delivery : UD
            # - UPS Overnight - AM Saturday delivery : 59
            'shipping_method_code': '31',
            'shipping_carrier_code': 'shippingoptions',
            'extension_attributes': {},
        },
    }
    
    shipping_address_l = json_data["customerData"]["addresses"]
    for item in shipping_address_l.values():
        if item["default_billing"]:
            shipping_payload["addressInformation"]["billing_address"]["customerAddressId"] = item["id"]
            shipping_payload["addressInformation"]["billing_address"]["countryId"] = item["country_id"]
            shipping_payload["addressInformation"]["billing_address"]["regionId"] = item["region_id"]
            shipping_payload["addressInformation"]["billing_address"]["regionCode"] = item["region"]["region_code"]
            shipping_payload["addressInformation"]["billing_address"]["region"] = item["region"]["region"]
            shipping_payload["addressInformation"]["billing_address"]["customerId"] = item["customer_id"]
            shipping_payload["addressInformation"]["billing_address"]["street"] = item["street"]
            shipping_payload["addressInformation"]["billing_address"]["company"] = item["company"]
            shipping_payload["addressInformation"]["billing_address"]["telephone"] = item["telephone"]
            shipping_payload["addressInformation"]["billing_address"]["fax"] = item["fax"]
            shipping_payload["addressInformation"]["billing_address"]["postcode"] = item["postcode"]
            shipping_payload["addressInformation"]["billing_address"]["city"] = item["city"]
            shipping_payload["addressInformation"]["billing_address"]["firstname"] = item["firstname"]
            shipping_payload["addressInformation"]["billing_address"]["lastname"] = item["lastname"]
            shipping_payload["addressInformation"]["billing_address"]["middlename"] = item["middlename"]
            shipping_payload["addressInformation"]["billing_address"]["prefix"] = item["prefix"]
            shipping_payload["addressInformation"]["billing_address"]["suffix"] = item["suffix"]
            shipping_payload["addressInformation"]["billing_address"]["vatId"] = item["vat_id"]
            shipping_payload["addressInformation"]["billing_address"]["customAttributes"] = list(item["custom_attributes"].values())

            billing_address = f'{item["inline"]}\n{item["telephone"]}'
            print("--- billing_address:\n", billing_address.strip() if billing_address else "")

        if item["default_shipping"]:
            shipping_payload["addressInformation"]["shipping_address"]["customerAddressId"] = item["id"]
            shipping_payload["addressInformation"]["shipping_address"]["email"] = json_data["customerData"]["email"]
            shipping_payload["addressInformation"]["shipping_address"]["countryId"] = item["country_id"]
            shipping_payload["addressInformation"]["shipping_address"]["regionId"] = item["region_id"]
            shipping_payload["addressInformation"]["shipping_address"]["regionCode"] = item["region"]["region_code"]
            shipping_payload["addressInformation"]["shipping_address"]["region"] = item["region"]["region"]
            shipping_payload["addressInformation"]["shipping_address"]["customerId"] = item["customer_id"]
            shipping_payload["addressInformation"]["shipping_address"]["street"] = item["street"]
            shipping_payload["addressInformation"]["shipping_address"]["company"] = item["company"]
            shipping_payload["addressInformation"]["shipping_address"]["telephone"] = item["telephone"]
            shipping_payload["addressInformation"]["shipping_address"]["fax"] = item["fax"]
            shipping_payload["addressInformation"]["shipping_address"]["postcode"] = item["postcode"]
            shipping_payload["addressInformation"]["shipping_address"]["city"] = item["city"]
            shipping_payload["addressInformation"]["shipping_address"]["firstname"] = item["firstname"]
            shipping_payload["addressInformation"]["shipping_address"]["lastname"] = item["lastname"]
            shipping_payload["addressInformation"]["shipping_address"]["middlename"] = item["middlename"]
            shipping_payload["addressInformation"]["shipping_address"]["prefix"] = item["prefix"]
            shipping_payload["addressInformation"]["shipping_address"]["suffix"] = item["suffix"]
            shipping_payload["addressInformation"]["shipping_address"]["vatId"] = item["vat_id"]
            shipping_payload["addressInformation"]["shipping_address"]["customAttributes"] = list(item["custom_attributes"].values())

            shipping_address = f'{item["inline"]}\n{item["telephone"]}'
            print("--- shipping_address:\n", shipping_address.strip() if shipping_address else "")

    total_info = shipping_infomation(shipping_payload)
    currency = total_info["base_currency_code"]
    subtotal = total_info["subtotal"]
    print("--- subtotal:\n", f'{currency} {subtotal}'.strip() if subtotal else "")

    shipping = total_info["shipping_amount"]
    print("--- shipping:\n", f'{currency} {shipping}'.strip() if shipping else "")

    discount = total_info["discount_amount"]
    print("--- discount:\n", f'{currency} {discount}'.strip() if discount else "")

    tax = total_info["tax_amount"]
    print("--- tax:\n", f'{currency} {tax}'.strip() if tax else "")

    order_total = total_info["grand_total"]
    print("--- order_total:\n", f'{currency} {order_total}'.strip() if order_total else "")

    return cartId, shipping_payload

def submit_order(cartId, shipping_payload):
    post_headers = {
        'authority': 'store.implantdirect.com',
        'pragma': 'no-cache',
        'cache-control': 'no-cache',
        'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
        'x-newrelic-id': 'VQUAU1dTABAHXFhUDgUHXlc=',
        'sec-ch-ua-mobile': '?0',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36',
        'content-type': 'application/json',
        'accept': '*/*',
        'x-requested-with': 'XMLHttpRequest',
        'sec-ch-ua-platform': '"Windows"',
        'origin': 'https://store.implantdirect.com',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-mode': 'cors',
        'sec-fetch-dest': 'empty',
        'referer': 'https://store.implantdirect.com/us/en/checkout/',
        'accept-language': 'en-US,en;q=0.9',
    }

    billingAddress = shipping_payload["addressInformation"]["shipping_address"]
    billingAddress["saveInAddressBook"] = None

    json_data = {
        'cartId': cartId,
        'billingAddress': billingAddress,
        "paymentMethod": {
            "method": "checkmo",
            "po_number": None,
            "additional_data": None
        }
    }

    response = session.post('https://store.implantdirect.com/us/en/rest/us_en/V1/carts/mine/payment-information', headers=post_headers, json=json_data)
    print("Place Order Response:", response.status_code)
    print("Place Order Response:", response.text)

    response = session.get('https://store.implantdirect.com/us/en/checkout/onepage/success/', headers=headers)
    print("Order Result Response:", response.status_code)

    response_dom = Selector(text=response.text)
    order_num = response_dom.xpath('//a[@class="order-number"]/strong//text()').get()
    order_num = order_num.strip() if order_num else order_num
    return order_num

if __name__ == "__main__":
    login()

    clear_cart()

    products = [
        {
            "link": "https://store.implantdirect.com/us/en/surgical-kit-grommet-small-2pk",
            "qty": "1"
        },
    ]
    add_to_cart(products)

    cartId, shipping_payload = proceed_checkout()
    # order_num = submit_order(cartId, shipping_payload)
    # print("Order Number:", order_num)
