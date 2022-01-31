from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.types.scraper import LoginInformation

LOGIN_PAGE_HEADERS = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

LOGIN_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "sec-ch-ua-mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Cache-Control": "no-cache",
    "X-Requested-With": "XMLHttpRequest",
    "X-MicrosoftAjax": "Delta=true",
    "sec-ch-ua-platform": '"Windows"',
    "Accept": "*/*",
    "Origin": "https://store.edgeendo.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://store.edgeendo.com/login.aspx",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}


class EdgeEndoScraper(Scraper):
    BASE_URL = "https://www.henryschein.com"
    CATEGORY_URL = "https://www.henryschein.com/us-en/dental/c/browsesupplies"
    TRACKING_BASE_URL = "https://narvar.com/tracking/itemvisibility/v1/henryschein-dental/orders"

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        text = await response.text()
        return "CustomerID" in text

    async def get_login_form(self):
        async with self.session.get("https://store.edgeendo.com/login.aspx", headers=LOGIN_PAGE_HEADERS) as resp:
            text = await resp.text()
            login_dom = Selector(text=text)
            login_dom.xpath('//input[@name="_TSM_HiddenField_"]/@value').extract()

            hidden_field = login_dom.xpath('//input[@name="_TSM_HiddenField_"]/@value').extract_first()
            event_target = login_dom.xpath('//input[@name="__EVENTTARGET"]/@value').extract_first()
            event_argument = login_dom.xpath('//input[@name="__EVENTARGUMENT"]/@value').extract_first()
            view_state = login_dom.xpath('//input[@name="__VIEWSTATE"]/@value').extract_first()
            view_state_generator = login_dom.xpath('//input[@name="__VIEWSTATEGENERATOR"]/@value').extract_first()
            return {
                "hidden_field": hidden_field,
                "event_target": event_target,
                "event_argument": event_argument,
                "view_state": view_state,
                "view_state_generator": view_state_generator,
            }

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        form = await self.get_login_form()

        return {
            "url": "https://store.edgeendo.com/login.aspx",
            "headers": LOGIN_HEADERS,
            "data": {
                "ctl00$ctl00$tsmScripts": "",
                "_TSM_HiddenField_": form["hidden_field"],
                "__EVENTTARGET": form["event_target"],
                "__EVENTARGUMENT": form["event_argument"],
                "__VIEWSTATE": form["view_state"],
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$emlLogin$txtEmail": self.username,
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$emlLogin$vceValid_ClientState": "",
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$emlLogin$vceRequired_ClientState": "",
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$pwdLogin$rtbPassword$txtRestricted": self.password,
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$pwdLogin$rtbPassword$vceRegExp_ClientState": "",
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$pwdLogin$rtbPassword$vceLength_ClientState": "",
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$pwdLogin$rtbPassword$vceRequired_ClientState": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartProductID": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartSKUID": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartQuantity": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartWriteInIDs": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartWriteInValues": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartBidPrice": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartShipTo": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartNewShipTo": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartGiftMessage": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartGiftWrap": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartFulfillmentMethod": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartPickupAt": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartEmailTo": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartSubscriptionID": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartExpressOrder": "",
                "ctl00$ctl00$cphMain$ctl00$hfManualCartPostBack": "",
                "ctl00$ctl00$cphMain$ctl00$hfRemoveCartProductIndex": "",
                "ctl00$ctl00$cphMain$ctl00$hfEditQuantityNewValue": "",
                "ctl00$ctl00$cphMain$ctl00$hfEditQuantityCartProductIndex": "",
                "ctl00$ctl00$cphMain$ctl00$hfReorderID": "",
                "ctl00$ctl00$cphMain$ctl00$hfProductSharingDiscountID": "",
                "ctl00$ctl00$cphMain$ctl00$hfCartRefresh": "",
                "__VIEWSTATEGENERATOR": form["view_state_generator"],
                "__ASYNCPOST": "true",
                "ctl00$ctl00$cphMain$cphMain$lfBtoC$btnCustomerLogin": "Log In Securely",
            },
        }
