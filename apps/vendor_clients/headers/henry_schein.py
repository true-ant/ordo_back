from .base import BASE_HEADERS

LOGIN_HEADERS = {
    **BASE_HEADERS,
    "authority": "www.henryschein.com",
    "n": "pikP/UtnnyEIsCZl3cphEgyUhacC9CnLZqSaDcvfufM=",
    "iscallingfromcms": "False",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "origin": "https://www.henryschein.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.henryschein.com/us-en/Profiles/Logout.aspx?redirdone=1",
}

CLEAR_CART_HEADERS = {
    **BASE_HEADERS,
    "authority": "www.henryschein.com",
    "n": "faMC175siE4Ji7eGjyxEnEahdp30gAd6F12KILNn68E=",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua-platform": '"Windows"',
    "origin": "https://www.henryschein.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx",
}

ADD_PRODUCTS_TO_CART_HEADERS = {
    "authority": "www.henryschein.com",
    "sec-ch-ua": '"Google Chrome";v="95", "Chromium";v="95", ";Not A Brand";v="99"',
    "n": "8Q66eFEZrl21cfd7A18MlrVGecsxls25GU/+P6Nw3QM=",
    "iscallingfromcms": "False",
    "sec-ch-ua-mobile": "?0",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua-platform": '"Windows"',
    "origin": "https://www.henryschein.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.henryschein.com",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

CHECKOUT_HEADER = {
    **BASE_HEADERS,
    "authority": "www.henryschein.com",
    "cache-control": "max-age=0",
    "upgrade-insecure-requests": "1",
    "origin": "https://www.henryschein.com",
    "content-type": "application/x-www-form-urlencoded",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
}

GET_PRODUCT_PRICES_HEADERS = {
    **BASE_HEADERS,
    "authority": "www.henryschein.com",
    "n": "pikP/UtnnyEIsCZl3cphEgyUhacC9CnLZqSaDcvfufM=",
    "iscallingfromcms": "False",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "origin": "https://www.henryschein.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.henryschein.com",
}
