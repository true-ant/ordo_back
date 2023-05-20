import re
from decimal import Decimal
from functools import wraps
from typing import Dict, List, Optional, Type

from aiohttp.client_exceptions import ClientConnectorError

from apps.scrapers.errors import NetworkConnectionException

TransformValue = Type[Exception]
TranformExceptionMapping = Dict[Type[Exception], TransformValue]


def transform_exceptions(exception_mapping: TranformExceptionMapping, default: Optional[TransformValue] = None):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
            except Exception as e:
                for exception_class, substitute in exception_mapping.items():
                    if not isinstance(e, exception_class):
                        continue
                    raise substitute() from e
                else:
                    if default is None:
                        raise
                    raise default() from e
            else:
                return result

        return wrapper

    return decorator


catch_network = transform_exceptions({ClientConnectorError: NetworkConnectionException})


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
    except (KeyError, ValueError, TypeError, IndexError):
        return Decimal("0")
