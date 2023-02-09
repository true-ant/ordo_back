import asyncio
import datetime
import logging
import random
import time
from asyncio import Queue
from collections import deque
from typing import Deque, NamedTuple

from aiohttp import ClientSession
from django.db.models.functions import Now
from django.utils import timezone

from apps.accounts.models import OfficeVendor, Vendor
from apps.orders.models import OfficeProduct, Product
from apps.vendor_clients.async_clients import BaseClient
from apps.vendor_clients.async_clients.base import (
    EmptyResults,
    PriceInfo,
    TooManyRequests,
)

logger = logging.getLogger(__name__)


STATUS_UNAVAILABLE = "Unavailable"
STATUS_EXHAUSTED = "Exhausted"
STATUS_ACTIVE = "Active"

SESSION_COUNT = 1
BULK_SIZE = 500


INVENTORY_AGE_DEFAULT = datetime.timedelta(days=1)
NONINVENTORY_AGE_DEFAULT = datetime.timedelta(days=2)


class AgeParams(NamedTuple):
    inventory: datetime.timedelta
    regular: datetime.timedelta


DEFAULT_AGE_PARAMS = AgeParams(inventory=datetime.timedelta(days=7), regular=datetime.timedelta(days=14))

VENDOR_AGE = {"net_32": AgeParams(inventory=datetime.timedelta(days=1), regular=datetime.timedelta(days=2))}


def get_vendor_age(v: Vendor, p: Product):
    age_params = VENDOR_AGE.get(v.slug, DEFAULT_AGE_PARAMS)
    if p.inventory_refs > 0:
        return age_params.inventory
    return age_params.regular


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
    record_age = datetime.timedelta(days=2)

    def __init__(self, vendor: Vendor):
        self.to_process: Queue[ProcessTask] = Queue(maxsize=20)
        self.vendor = vendor
        self._crendentials = None
        self.statbuffer = StatBuffer()
        self.target_rate = 1.5
        self.last_check: float = time.monotonic()
        self.errors = 0

    async def get_credentials(self):
        if not self._crendentials:
            self._crendentials = (
                await OfficeVendor.objects.filter(vendor=self.vendor).values("username", "password").afirst()
            )
        return self._crendentials

    async def producer(self):
        products = (
            Product.objects.all()
            .with_inventory_refs()
            .filter(vendor=self.vendor, price_expiration__lt=Now())
            .exclude(product_vendor_status__in=(STATUS_UNAVAILABLE, STATUS_EXHAUSTED))
            .order_by("-_inventory_refs", "price_expiration")[:BULK_SIZE]
        )
        async for product in products:
            await self.put(ProcessTask(product))

    async def put(self, item):
        await self.to_process.put(item)

    async def process(self, client, pt: ProcessTask):
        try:
            product_price: PriceInfo = await client.get_product_price_v2(pt.product)
        except TooManyRequests:
            logger.debug("Retrying fetching product price for %s. Attempt #%s", pt.product.id, pt.attempt + 1)
            self.statbuffer.add_item(False)
            await self.put(ProcessTask(pt.product, pt.attempt + 1))
        except EmptyResults:
            logger.debug("Marking product %s as empty", pt.product.id)
            self.statbuffer.add_item(True)
            await self.mark_status(pt.product, STATUS_UNAVAILABLE)
        except:  # noqa
            logger.debug("Retrying fetching product price for %s. Attempt #%s", pt.product.id, pt.attempt + 1)
            self.statbuffer.add_item(True)
            await self.put(ProcessTask(pt.product, pt.attempt + 1))
        else:
            self.statbuffer.add_item(True)
            await self.update_price(pt.product, product_price)
        finally:
            self.to_process.task_done()

    async def mark_status(self, product: Product, status: str):
        await Product.objects.filter(pk=product.pk).aupdate(product_vendor_status=status)
        await OfficeProduct.objects.filter(product_id=product.pk).aupdate(product_vendor_status=status)

    async def update_price(self, product: Product, price_info: PriceInfo):
        update_time = timezone.now()
        logger.debug("Updating price for product %s: %s", product.id, price_info)
        await Product.objects.filter(pk=product.pk).aupdate(
            special_price=price_info.special_price,
            is_special_offer=price_info.is_special_offer,
            price=price_info.price,
            last_price_updated=update_time,
            product_vendor_status=STATUS_ACTIVE,
            price_expiration=timezone.now() + get_vendor_age(self.vendor, product),
        )
        await OfficeProduct.objects.filter(product_id=product.pk).aupdate(
            price=price_info.price, last_price_updated=update_time, product_vendor_status=STATUS_ACTIVE
        )

    async def consumer(self):
        logger.debug("Getting credentials")
        credentials = await self.get_credentials()
        async with ClientSession() as session:
            logger.debug("Making handler")
            client = BaseClient.make_handler(
                vendor_slug=self.vendor.slug,
                session=session,
                username=credentials["username"],
                password=credentials["password"],
            )
            while True:
                await asyncio.sleep(SESSION_COUNT * random.uniform(0.5, 1.5) / self.target_rate)
                pt = await self.to_process.get()
                if pt.attempt > self.attempt_threshold:
                    logger.warning("Too many attempts updating product %s. Giving up", pt.product.id)
                    await self.mark_status(pt.product, STATUS_EXHAUSTED)
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

    async def complete(self):
        await self.to_process.join()


async def fetch_for_vendor(slug):
    vendor = await Vendor.objects.aget(slug=slug)
    updater = Updater(vendor=vendor)
    worker_tasks = [asyncio.create_task(updater.consumer()) for _ in range(SESSION_COUNT)]
    asyncio.create_task(updater.producer())
    await asyncio.sleep(1)
    await updater.complete()
    for worker_task in worker_tasks:
        worker_task.cancel()