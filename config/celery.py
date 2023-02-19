import logging
import logging.handlers
import os

from celery import Celery
from celery.app.log import TaskFormatter
from celery.signals import setup_logging, worker_process_init

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("FORKED_BY_MULTIPROCESSING", "1")


@setup_logging.connect
def config_loggers(*args, **kwargs):
    logging.basicConfig(level="DEBUG")
    logger = logging.getLogger()
    formatter = TaskFormatter("%(asctime)s - %(task_id)s - %(task_name)s - %(name)s - %(levelname)s - %(message)s")
    for handler in logger.handlers:
        handler.setFormatter(formatter)


@worker_process_init.connect
def setup_task_logger(*args, **kwargs):
    logging.basicConfig(level="DEBUG")
    logger = logging.getLogger()
    formatter = TaskFormatter("%(asctime)s - %(task_id)s - %(task_name)s - %(name)s - %(levelname)s - %(message)s")
    for handler in logger.handlers:
        logger.removeHandler(handler)
    stream_handler = logging.StreamHandler()
    rotating_file_handler = logging.handlers.TimedRotatingFileHandler(
        os.getenv("CELERY_WORKER_LOG_FILE", "worker.log"),
    )
    for handler in (stream_handler, rotating_file_handler):
        handler.setFormatter(formatter)
        handler.setLevel("DEBUG")
        logger.addHandler(handler)


app = Celery("ordo-back")
app.config_from_object("config.celeryconfig")
app.autodiscover_tasks()
