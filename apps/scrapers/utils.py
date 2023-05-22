import re
import os
from decimal import Decimal
from functools import wraps
from unicaps import CaptchaSolver, CaptchaSolvingService
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

def solve_captcha(site_key: str, url: str, score: float, is_enterprise: bool, api_domain: str):
    solver = CaptchaSolver(CaptchaSolvingService.ANTI_CAPTCHA, os.getenv("ANTI_CAPTCHA_API_KEY"))
    solved = solver.solve_recaptcha_v3(
        site_key=site_key,
        page_url=url,
        is_enterprise=is_enterprise,
        min_score=score,
        api_domain=api_domain
    )
    return solved