import asyncio
import datetime
import logging
import random
import time
from asyncio import Queue
from collections import deque
from typing import Deque, Dict, List, Union

from aiohttp import ClientSession
from django.db.models.functions import Now
from django.utils import timezone

from apps.accounts.models import Office, OfficeVendor, Vendor
from apps.orders.models import OfficeProduct, Product
from apps.orders.types import ProcessResult, ProcessTask, Stats, VendorParams
from apps.vendor_clients.async_clients import BaseClient
from apps.vendor_clients.async_clients.base import (
    EmptyResults,
    PriceInfo,
    ProductPriceUpdateResult,
    TooManyRequests,
)

logger = logging.getLogger(__name__)


STATUS_UNAVAILABLE = "Unavailable"
STATUS_EXHAUSTED = "Exhausted"
STATUS_ACTIVE = "Active"

BULK_SIZE = 500


INVENTORY_AGE_DEFAULT = datetime.timedelta(days=1)
NONINVENTORY_AGE_DEFAULT = datetime.timedelta(days=2)

DEFAULT_VENDOR_PARAMS = VendorParams(
    inventory_age=datetime.timedelta(days=7), regular_age=datetime.timedelta(days=14), batch_size=1, request_rate=1
)

VENDOR_PARAMS: Dict[str, VendorParams] = {
    "net_32": VendorParams(
        inventory_age=datetime.timedelta(days=1),
        regular_age=datetime.timedelta(days=2),
        batch_size=1,
        request_rate=1.5,
        needs_login=False,
    ),
    "henry_schein": VendorParams(
        inventory_age=datetime.timedelta(days=7),
        regular_age=datetime.timedelta(days=7),
        batch_size=20,
        request_rate=5,
        needs_login=True,
    ),
    "benco": VendorParams(
        inventory_age=datetime.timedelta(days=14),
        regular_age=datetime.timedelta(days=14),
        batch_size=20,
        request_rate=5,
        needs_login=True,
    ),
    "darby": VendorParams(
        inventory_age=datetime.timedelta(days=14),
        regular_age=datetime.timedelta(days=14),
        batch_size=1,
        request_rate=5,
        needs_login=True,
    ),
    "dental_city": VendorParams(
        inventory_age=datetime.timedelta(days=14),
        regular_age=datetime.timedelta(days=14),
        batch_size=1,
        request_rate=5,
        needs_login=True,
    ),
    "patterson": VendorParams(
        inventory_age=datetime.timedelta(days=14),
        regular_age=datetime.timedelta(days=14),
        batch_size=1,
        request_rate=5,
        needs_login=True,
    ),
    "edge_endo": VendorParams(
        inventory_age=datetime.timedelta(days=14),
        regular_age=datetime.timedelta(days=14),
        batch_size=1,
        request_rate=5,
        needs_login=True,
    ),
    "ultradent": VendorParams(
        inventory_age=datetime.timedelta(days=14),
        regular_age=datetime.timedelta(days=14),
        batch_size=1,
        request_rate=5,
        needs_login=True,
    ),
}


def get_vendor_age(v: Vendor, p: Union[Product, OfficeProduct]):
    vendor_params = VENDOR_PARAMS.get(v.slug, DEFAULT_VENDOR_PARAMS)
    if isinstance(p, Product):
        if p.inventory_refs > 0:
            return vendor_params.inventory_age
    if isinstance(p, OfficeProduct):
        if p.is_inventory:
            return vendor_params.inventory_age
    return vendor_params.regular_age


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

    def __init__(self, vendor: Vendor, office: Office = None):
        self.vendor = vendor
        self.vendor_params = VENDOR_PARAMS[vendor.slug]
        self.batch_size = self.vendor_params.batch_size
        self.to_process: Queue[ProcessTask] = Queue(maxsize=20)
        self._crendentials = None
        self.statbuffer = StatBuffer()
        self.target_rate = self.vendor_params.request_rate
        self.last_check: float = time.monotonic()
        self.errors = 0
        self.office = office

    async def get_credentials(self):
        if not self._crendentials:
            qs = OfficeVendor.objects.filter(vendor=self.vendor)
            if self.office:
                qs = qs.filter(office=self.office)
            self._crendentials = await qs.values("username", "password").afirst()
        return self._crendentials

    async def producer(self):
        if self.office:
            products = (
                OfficeProduct.objects.select_related("product")
                .filter(office=self.office, vendor=self.vendor, price_expiration__lt=Now())
                .exclude(product_vendor_status__in=(STATUS_EXHAUSTED,))
                .order_by("-is_inventory", "price_expiration")
            )
        else:
            products = (
                Product.objects.all()
                .with_inventory_refs()
                .filter(vendor=self.vendor, price_expiration__lt=Now())
                .exclude(product_vendor_status__in=(STATUS_EXHAUSTED,))
                .order_by("-_inventory_refs", "price_expiration")
            )
        products = products[:BULK_SIZE]
        async for product in products:
            await self.to_process.put(ProcessTask(product))

    async def process(self, client: BaseClient, tasks: List[ProcessTask]):
        results: List[ProductPriceUpdateResult] = await client.get_batch_product_prices([pt.product for pt in tasks])
        task_mapping = {pt.product.id: pt for pt in tasks}
        for process_result in results:
            product = process_result.product
            r = process_result.result
            if r.is_ok():
                self.statbuffer.add_item(True)
                await self.update_price(product, r.value)
            else:
                exc = process_result.result.value
                if isinstance(exc, TooManyRequests):
                    attempt = task_mapping[product.id].attempt + 1
                    self.statbuffer.add_item(False)
                    await self.reschedule(ProcessTask(product, attempt))
                elif isinstance(exc, EmptyResults):
                    logger.debug("Marking product %s as empty", product.id)
                    self.statbuffer.add_item(True)
                    await self.mark_status(product, STATUS_UNAVAILABLE)
                else:
                    attempt = task_mapping[product.id].attempt + 1
                    self.statbuffer.add_item(True)
                    await self.reschedule(ProcessTask(product, attempt))
            task_mapping.pop(product.id)

        for _, pt in task_mapping.items():
            await self.mark_status(pt.product, pt.product.product_vendor_status)
        for _ in tasks:
            self.to_process.task_done()

    async def reschedule(self, pt: ProcessTask):
        if pt.attempt > self.attempt_threshold:
            logger.warning("Too many attempts updating product %s. Giving up", pt.product.id)
            await self.mark_status(pt.product, STATUS_EXHAUSTED)
        else:
            logger.debug("Rescheduling fetching product price for %s. Attempt #%s", pt.product.id, pt.attempt)
            await self.to_process.put(pt)

    async def mark_status(self, product: Union[Product, OfficeProduct], status: str):
        current_time = timezone.now()
        update_fields = {
            "product_vendor_status": status,
            "last_price_updated": current_time,
            "price_expiration": current_time + get_vendor_age(self.vendor, product),
        }
        if isinstance(product, Product):
            await Product.objects.filter(
                pk=product.pk,
            ).aupdate(**update_fields)
            await OfficeProduct.objects.filter(product_id=product.pk).aupdate(**update_fields)
        else:
            await OfficeProduct.objects.filter(id=product.pk).aupdate(**update_fields)

    async def update_price(self, product: Union[Product, OfficeProduct], price_info: PriceInfo):
        update_time = timezone.now()
        update_fields = {
            "price": price_info.price,
            "last_price_updated": update_time,
            "product_vendor_status": price_info.product_vendor_status,
            "price_expiration": timezone.now() + get_vendor_age(self.vendor, product),
        }
        if isinstance(product, Product):
            logger.debug("Updating price for product %s: %s", product.id, price_info)
            await Product.objects.filter(pk=product.pk).aupdate(
                special_price=price_info.special_price, is_special_offer=price_info.is_special_offer, **update_fields
            )
            await OfficeProduct.objects.filter(product_id=product.pk).aupdate(**update_fields)
        elif isinstance(product, OfficeProduct):
            await OfficeProduct.objects.filter(id=product.pk).aupdate(**update_fields)

    async def get_batch(self) -> List[ProcessTask]:
        batch = []
        sleeps = 0
        while len(batch) < self.batch_size:
            await asyncio.sleep(random.uniform(0.5, 1.5) / self.target_rate)
            if sleeps > 3 and batch:
                break
            if not self.to_process.empty():
                item = await self.to_process.get()
                batch.append(item)
                sleeps = 0
            else:
                sleeps += 1
        return batch

    async def get_client(self, session):
        credentials = await self.get_credentials()
        logger.debug("Making handler")
        client = BaseClient.make_handler(
            vendor_slug=self.vendor.slug,
            session=session,
            username=credentials["username"],
            password=credentials["password"],
        )
        if self.vendor_params.needs_login:
            await client.login()
        return client

    async def consumer(self):
        logger.debug("Getting credentials")
        async with ClientSession() as session:
            client = await self.get_client(session)
            while True:
                batch = await self.get_batch()
                asyncio.create_task(self.process(client, batch))
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


async def fetch_for_vendor(slug, office_id):
    vendor = await Vendor.objects.aget(slug=slug)
    office = await Office.objects.aget(pk=office_id)
    updater = Updater(vendor=vendor, office=office)
    worker_task = asyncio.create_task(updater.consumer())
    asyncio.create_task(updater.producer())
    await asyncio.sleep(1)
    await updater.complete()
    worker_task.cancel()
