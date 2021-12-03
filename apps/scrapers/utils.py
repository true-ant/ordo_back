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


def semaphore_coroutine(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        await args[1].acquire()
        await func(*args, **kwargs)
        args[1].release()

    return wrapper
