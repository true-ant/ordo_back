web: gunicorn config.asgi:application -k config.uvicorn_worker.OrdoUvicornWorker --timeout 300
# celery_worker: celery -A config worker -c 100 --loglevel=INFO --pool=threads
# celery_beat: celery -A config beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
