import requests

QUERY_URL = "https://api.opendental.com/api/v1/queries/ShortQuery"
DEVELOPOER_KEY = "ODFHIR Qh3A7zcjmr7TGg4Z"


class OpenDentalClient:
    def __init__(self, office_key):
        self.session = requests.Session()
        self.session.headers = {"Authorization": f"{DEVELOPOER_KEY}/{office_key}"}

    def query(self, query, offset=None):
        params = {"Offset": offset} if offset else None
        resp = self.session.put(QUERY_URL, params=params, json={"SqlCommand": query})
        return resp.json(), resp.status_code
