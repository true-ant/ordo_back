import asyncio
import aiohttp

CLIENT_SESSSION = None

_lock = asyncio.Lock()


async def get_client_session():
    from .asgi import application

    global CLIENT_SESSSION

    async with _lock:
        if not CLIENT_SESSSION:
            CLIENT_SESSSION = aiohttp.ClientSession()
            application.on_shutdown.append(CLIENT_SESSSION.close)

    return CLIENT_SESSSION
