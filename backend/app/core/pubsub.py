import json
import logging
import os

from google.cloud import pubsub_v1

from app.config import settings

logger = logging.getLogger(__name__)

_publisher = None


def get_publisher() -> pubsub_v1.PublisherClient:
    global _publisher
    if _publisher is None:
        # The client auto-detects PUBSUB_EMULATOR_HOST env var
        if settings.pubsub_emulator_host:
            os.environ["PUBSUB_EMULATOR_HOST"] = settings.pubsub_emulator_host
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def _topic_path(topic_name: str) -> str:
    return get_publisher().topic_path(settings.pubsub_project_id, topic_name)


def publish_detection_task(job_id: str) -> None:
    topic = _topic_path(settings.pubsub_topic_detection)
    data = json.dumps({"job_id": job_id}).encode("utf-8")
    future = get_publisher().publish(topic, data)
    future.result()  # block until published
    logger.info("Published detection task for job %s", job_id)


def publish_highlights_task(job_id: str) -> None:
    topic = _topic_path(settings.pubsub_topic_highlights)
    data = json.dumps({"job_id": job_id}).encode("utf-8")
    future = get_publisher().publish(topic, data)
    future.result()
    logger.info("Published highlights task for job %s", job_id)
