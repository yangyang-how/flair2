from celery import Celery

from app.config import settings

celery_app = Celery("flair2")

celery_app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.redis_url,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
