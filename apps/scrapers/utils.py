import re
from decimal import Decimal
from functools import wraps
from typing import List

from aiohttp.client_exceptions import ClientConnectorError

from apps.scrapers.errors import NetworkConnectionException


def catch_network(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            res = await func(*args, **kwargs)
        except ClientConnectorError:
            raise NetworkConnectionException()
        except Exception as e:
            raise e
        else:
            return res

    return wrapper


def semaphore_coroutine(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        await args[1].acquire()
        ret = await func(*args, **kwargs)
        args[1].release()
        return ret

    return wrapper


def extract_numeric_values(text: str) -> List[str]:
    return re.findall(r"(\d[\d.,]*)\b", text)


def convert_string_to_price(text: str) -> Decimal:
    try:
        price = extract_numeric_values(text)[0]
        price = price.replace(",", "")
        return Decimal(price)
    except (KeyError, ValueError, TypeError):
        return Decimal("0")
