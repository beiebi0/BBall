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
from http.server import HTTPServer, BaseHTTPRequestHandler

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


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format, *args):
        pass  # suppress request logs


def _start_health_server(port: int = 8080) -> None:
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health server listening on port %d", port)


def main() -> None:
    # Start health endpoint FIRST so Cloud Run startup probe passes
    health_port = int(os.environ.get("PORT", "8080"))
    _start_health_server(health_port)

    # Graceful shutdown
    shutdown_event = threading.Event()
    futures = []

    def _shutdown(signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        for f in futures:
            f.cancel()
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Start Pub/Sub subscriber in a background thread so it doesn't block
    # the health check during credential/metadata server lookups
    def _start_subscriber():
        try:
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
            futures.append(future_det)

            logger.info("Subscribing to %s", highlights_sub)
            future_hl = subscriber.subscribe(
                highlights_sub, callback=_handle_highlights_message, flow_control=flow_control
            )
            futures.append(future_hl)

            logger.info("Worker listening for messages.")
        except Exception:
            logger.exception("Failed to start Pub/Sub subscriber")
            shutdown_event.set()

    threading.Thread(target=_start_subscriber, daemon=True).start()

    shutdown_event.wait()
    logger.info("Worker shut down.")


if __name__ == "__main__":
    main()
