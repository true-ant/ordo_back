from functools import wraps

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
