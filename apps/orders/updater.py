import asyncio
import datetime
import logging
import time
from asyncio import Queue
from collections import deque
from typing import Deque, NamedTuple

from aiohttp import ClientSession
from django.utils import timezone

from apps.accounts.models import OfficeVendor, Vendor
from apps.orders.models import OfficeProduct, Product
from apps.vendor_clients.async_clients import BaseClient
from apps.vendor_clients.async_clients.base import PriceInfo, TooManyRequests

logger = logging.getLogger(__name__)


class ProcessTask(NamedTuple):
    product: Product
    attempt: int = 0


class ProcessResult(NamedTuple):
    timestamp: datetime.datetime
    success: bool


class Stats(NamedTuple):
    rate: float
    error_rate: float
    total: int


class StatBuffer:
    max_duration = datetime.timedelta(seconds=20)

    def __init__(self):
        self.items: Deque[ProcessResult] = deque()
        self.total_errors = 0
        self.total = 0

    def cleanup(self):
        if not self.items:
            return
        while (self.items[-1].timestamp - self.items[0].timestamp) >= self.max_duration:
            self.pop()

    def add_item(self, item: bool):
        self.items.append(ProcessResult(timezone.now(), item))
        if not item:
            self.total_errors += 1
        self.total += 1

    def pop(self):
        if not self.items:
            return
        left = self.items.popleft()
        if not left.success:
            self.total_errors -= 1
        self.total -= 1

    def stats(self):
        self.cleanup()
        if self.items:
            td = self.items[-1].timestamp - self.items[0].timestamp
        else:
            td = datetime.timedelta(0)
        return Stats(
            rate=len(self.items) / td.total_seconds() if td.total_seconds() else None,
            error_rate=self.total_errors / self.total if self.total else None,
            total=self.total,
        )


class Updater:
    attempt_threshold = 3

    def __init__(self, vendor: Vendor):
        self.to_process: Queue[ProcessTask] = Queue(maxsize=20)
        self.session = ClientSession()
        self.vendor = vendor
        self._crendentials = None
        self.statbuffer = StatBuffer()
        self.target_rate = 1
        self.last_check: float = time.monotonic()
        self.errors = 0

    async def get_credentials(self):
        if not self._crendentials:
            self._crendentials = (
                await OfficeVendor.objects.filter(vendor=self.vendor).values("username", "password").afirst()
            )
        return self._crendentials

    async def producer(self):
        async for product in Product.objects.filter(vendor=self.vendor):
            await self.to_process.put(ProcessTask(product))
            await asyncio.sleep(1 / self.target_rate)

    async def process(self, client, pt: ProcessTask):
        try:
            product_price: PriceInfo = await client.get_product_price_v2(pt.product)
        except TooManyRequests:
            logger.debug("Retrying fetching product price for %s. Attempt #%s", pt.product.id, pt.attempt + 1)
            self.statbuffer.add_item(False)
            await self.to_process.put(ProcessTask(pt.product, pt.attempt + 1))
        except:  # noqa
            logger.debug("Retrying fetching product price for %s. Attempt #%s", pt.product.id, pt.attempt + 1)
            self.statbuffer.add_item(True)
            await self.to_process.put(ProcessTask(pt.product, pt.attempt + 1))
        else:
            self.statbuffer.add_item(True)
            await self.update_price(pt.product, product_price)

    async def update_price(self, product: Product, price_info: PriceInfo):
        update_time = timezone.now()
        logger.debug("Updating price for product %s: %s", product.id, price_info)
        await Product.objects.filter(pk=product.pk).aupdate(
            special_price=price_info.special_price,
            is_special_offer=price_info.is_special_offer,
            price=price_info.price,
            last_price_updated=update_time,
        )
        await OfficeProduct.objects.filter(product_id=product.pk).aupdate(
            price=price_info.price, last_price_updated=update_time
        )

    async def consumer(self):
        credentials = await self.get_credentials()
        client = BaseClient.make_handler(
            vendor_slug=self.vendor.slug,
            session=self.session,
            username=credentials["username"],
            password=credentials["password"],
        )
        while not self.to_process.empty():
            pt = await self.to_process.get()
            if pt.attempt > self.attempt_threshold:
                logger.warning("Too many attempts updating product %s. Giving up", pt.product.id)
                continue
            asyncio.create_task(self.process(client, pt))
            stats = self.statbuffer.stats()
            logger.debug("Stats: %s", stats)
            if stats.total > 10 and time.monotonic() - self.last_check > 20:
                if stats.error_rate > 0:
                    self.errors += 1
                    self.target_rate /= 1.05
                else:
                    self.target_rate *= 1 + 0.05 / (self.errors + 1)
                self.last_check = time.monotonic()
                logger.debug("New target rate: %s", self.target_rate)


async def fetch_for_vendor(slug):
    vendor = await Vendor.objects.aget(slug=slug)
    updater = Updater(vendor=vendor)
    asyncio.create_task(updater.producer())
    await updater.consumer()
