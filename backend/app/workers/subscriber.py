"""
Pub/Sub pull subscriber — entry point for the worker process.

Usage:
    python -m app.workers.subscriber
"""

import json
import logging
import os
import signal
import sys
import threading

from google.cloud import pubsub_v1

from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _handle_detection_message(message: pubsub_v1.subscriber.message.Message) -> None:
    try:
        data = json.loads(message.data.decode("utf-8"))
        job_id = data["job_id"]
        logger.info("Received detection task for job %s", job_id)

        from app.workers.tasks import process_video_detection

        process_video_detection(job_id)
        message.ack()
        logger.info("Detection task completed and acked for job %s", job_id)
    except Exception:
        logger.exception("Detection task failed, nacking message")
        message.nack()


def _handle_highlights_message(message: pubsub_v1.subscriber.message.Message) -> None:
    try:
        data = json.loads(message.data.decode("utf-8"))
        job_id = data["job_id"]
        logger.info("Received highlights task for job %s", job_id)

        from app.workers.tasks import process_video_highlights

        process_video_highlights(job_id)
        message.ack()
        logger.info("Highlights task completed and acked for job %s", job_id)
    except Exception:
        logger.exception("Highlights task failed, nacking message")
        message.nack()


def main() -> None:
    if settings.pubsub_emulator_host:
        os.environ["PUBSUB_EMULATOR_HOST"] = settings.pubsub_emulator_host

    subscriber = pubsub_v1.SubscriberClient()

    flow_control = pubsub_v1.types.FlowControl(max_messages=1)

    detection_sub = subscriber.subscription_path(
        settings.pubsub_project_id, settings.pubsub_subscription_detection
    )
    highlights_sub = subscriber.subscription_path(
        settings.pubsub_project_id, settings.pubsub_subscription_highlights
    )

    logger.info("Subscribing to %s", detection_sub)
    future_det = subscriber.subscribe(
        detection_sub, callback=_handle_detection_message, flow_control=flow_control
    )

    logger.info("Subscribing to %s", highlights_sub)
    future_hl = subscriber.subscribe(
        highlights_sub, callback=_handle_highlights_message, flow_control=flow_control
    )

    logger.info("Worker listening for messages. Press Ctrl+C to exit.")

    # Graceful shutdown
    shutdown_event = threading.Event()

    def _shutdown(signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        future_det.cancel()
        future_hl.cancel()
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    shutdown_event.wait()
    logger.info("Worker shut down.")


if __name__ == "__main__":
    main()
