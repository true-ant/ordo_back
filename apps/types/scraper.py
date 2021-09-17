from typing import TypedDict


class LoginInformation(TypedDict):
    url: str
    headers: dict
    data: dict
