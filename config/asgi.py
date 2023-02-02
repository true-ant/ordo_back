"""
ASGI config for ordo_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/howto/deployment/asgi/
"""

import asyncio
import os
import django

from django.core.handlers.asgi import ASGIHandler

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


class OrdoASGIHandler(ASGIHandler):
    def __init__(self):
        super().__init__()
        self.on_shutdown = []

    async def __call__(self, scope, receive, send):
        from django.apps import apps

        if scope["type"] == "lifespan":
            while True:
                message = await receive()

                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await self.shutdown()
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        else:
            return await super().__call__(scope, receive, send)

    async def shutdown(self):
        for handler in self.on_shutdown:
            if asyncio.iscoroutinefunction(handler):
                await handler()
            else:
                handler()


def get_asgi_application():
    """
    The public interface to Django's ASGI support. Return an ASGI 3 callable.

    Avoids making django.core.handlers.ASGIHandler a public API, in case the
    internal implementation changes or moves in the future.
    """
    django.setup(set_prefix=False)
    return OrdoASGIHandler()


application = get_asgi_application()
