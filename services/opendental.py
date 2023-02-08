import requests

QUERY_URL = "https://api.opendental.com/api/v1/queries/ShortQuery"


class OpenDentalClient:
    def __init__(self, auth_header):
        self.session = requests.Session()
        self.session.headers = {"Authorization": auth_header}

    def query(self, query, offset=None):
        params = {"Offset": offset} if offset else None
        resp = self.session.put(QUERY_URL, params=params, json={"SqlCommand": query})
        return resp.json(), resp.status_code
