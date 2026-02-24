"""Tests for Pub/Sub subscriber message handling."""

import json
from unittest.mock import MagicMock, patch

import pytest


def _make_message(data: dict) -> MagicMock:
    msg = MagicMock()
    msg.data = json.dumps(data).encode("utf-8")
    return msg


@patch("app.workers.subscriber.process_video_detection", create=True)
def test_handle_detection_message_success(mock_task):
    """On success, message is acked."""
    # Import after patching to avoid import-time issues
    from app.workers.subscriber import _handle_detection_message

    with patch("app.workers.tasks.process_video_detection", mock_task):
        msg = _make_message({"job_id": "job-001"})
        _handle_detection_message(msg)

    mock_task.assert_called_once_with("job-001")
    msg.ack.assert_called_once()
    msg.nack.assert_not_called()


@patch("app.workers.tasks.process_video_detection", side_effect=RuntimeError("boom"))
def test_handle_detection_message_failure(mock_task):
    """On failure, message is nacked."""
    from app.workers.subscriber import _handle_detection_message

    msg = _make_message({"job_id": "job-002"})
    _handle_detection_message(msg)

    msg.nack.assert_called_once()
    msg.ack.assert_not_called()


@patch("app.workers.subscriber.process_video_highlights", create=True)
def test_handle_highlights_message_success(mock_task):
    """On success, message is acked."""
    from app.workers.subscriber import _handle_highlights_message

    with patch("app.workers.tasks.process_video_highlights", mock_task):
        msg = _make_message({"job_id": "job-003"})
        _handle_highlights_message(msg)

    mock_task.assert_called_once_with("job-003")
    msg.ack.assert_called_once()
    msg.nack.assert_not_called()


@patch("app.workers.tasks.process_video_highlights", side_effect=RuntimeError("boom"))
def test_handle_highlights_message_failure(mock_task):
    """On failure, message is nacked."""
    from app.workers.subscriber import _handle_highlights_message

    msg = _make_message({"job_id": "job-004"})
    _handle_highlights_message(msg)

    msg.nack.assert_called_once()
    msg.ack.assert_not_called()
