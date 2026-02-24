"""Tests for Pub/Sub publisher module."""

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_publisher():
    """Reset the module-level singleton before each test."""
    import app.core.pubsub as mod
    mod._publisher = None
    yield
    mod._publisher = None


@patch("app.core.pubsub.pubsub_v1.PublisherClient")
def test_publish_detection_task(mock_client_cls):
    mock_publisher = MagicMock()
    mock_client_cls.return_value = mock_publisher
    mock_publisher.topic_path.return_value = "projects/bball-local/topics/video-detection"
    mock_future = MagicMock()
    mock_publisher.publish.return_value = mock_future

    from app.core.pubsub import publish_detection_task

    publish_detection_task("job-123")

    mock_publisher.publish.assert_called_once()
    args, kwargs = mock_publisher.publish.call_args
    assert args[0] == "projects/bball-local/topics/video-detection"
    data = json.loads(args[1].decode("utf-8"))
    assert data == {"job_id": "job-123"}
    mock_future.result.assert_called_once()


@patch("app.core.pubsub.pubsub_v1.PublisherClient")
def test_publish_highlights_task(mock_client_cls):
    mock_publisher = MagicMock()
    mock_client_cls.return_value = mock_publisher
    mock_publisher.topic_path.return_value = "projects/bball-local/topics/video-highlights"
    mock_future = MagicMock()
    mock_publisher.publish.return_value = mock_future

    from app.core.pubsub import publish_highlights_task

    publish_highlights_task("job-456")

    mock_publisher.publish.assert_called_once()
    args, kwargs = mock_publisher.publish.call_args
    assert args[0] == "projects/bball-local/topics/video-highlights"
    data = json.loads(args[1].decode("utf-8"))
    assert data == {"job_id": "job-456"}
    mock_future.result.assert_called_once()


@patch("app.core.pubsub.pubsub_v1.PublisherClient")
def test_get_publisher_singleton(mock_client_cls):
    """Publisher client is created once and reused."""
    mock_publisher = MagicMock()
    mock_client_cls.return_value = mock_publisher

    from app.core.pubsub import get_publisher

    p1 = get_publisher()
    p2 = get_publisher()

    assert p1 is p2
    mock_client_cls.assert_called_once()
