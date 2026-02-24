"""Tests for detection cache serialization and orchestrator cache path."""

import json
from unittest.mock import MagicMock, patch

import pytest

from pipeline.models import (
    BoundingBox,
    FrameData,
    PlayerDetection,
    serialize_detection_cache,
    deserialize_detection_cache,
)


# --- Serialization round-trip tests ---


def test_bounding_box_roundtrip():
    bb = BoundingBox(x1=10.5, y1=20.3, x2=100.0, y2=200.7)
    d = bb.to_dict()
    restored = BoundingBox.from_dict(d)
    assert restored.x1 == bb.x1
    assert restored.y1 == bb.y1
    assert restored.x2 == bb.x2
    assert restored.y2 == bb.y2


def test_player_detection_roundtrip():
    pd = PlayerDetection(
        track_id=5,
        bbox=BoundingBox(x1=1, y1=2, x2=3, y2=4),
        confidence=0.87,
    )
    d = pd.to_dict()
    restored = PlayerDetection.from_dict(d)
    assert restored.track_id == 5
    assert restored.confidence == 0.87
    assert restored.bbox.x1 == 1


def test_frame_data_roundtrip_with_all_fields():
    frame = FrameData(
        frame_index=42,
        timestamp=1.4,
        players=[
            PlayerDetection(track_id=1, bbox=BoundingBox(0, 0, 50, 100), confidence=0.9),
            PlayerDetection(track_id=2, bbox=BoundingBox(60, 0, 110, 100), confidence=0.8),
        ],
        ball=BoundingBox(30, 30, 40, 40),
        hoop=BoundingBox(200, 50, 250, 80),
        possessor_id=1,
        frame_width=1920,
        frame_height=1080,
    )
    d = frame.to_dict()
    restored = FrameData.from_dict(d)
    assert restored.frame_index == 42
    assert restored.timestamp == 1.4
    assert len(restored.players) == 2
    assert restored.players[0].track_id == 1
    assert restored.ball is not None
    assert restored.ball.x1 == 30
    assert restored.hoop is not None
    assert restored.possessor_id == 1
    assert restored.frame_width == 1920


def test_frame_data_roundtrip_with_none_fields():
    frame = FrameData(frame_index=0, timestamp=0.0)
    d = frame.to_dict()
    restored = FrameData.from_dict(d)
    assert restored.players == []
    assert restored.ball is None
    assert restored.hoop is None
    assert restored.possessor_id is None


def test_serialize_deserialize_detection_cache():
    frames = [
        FrameData(
            frame_index=0,
            timestamp=0.0,
            players=[PlayerDetection(track_id=1, bbox=BoundingBox(0, 0, 50, 100))],
            ball=BoundingBox(20, 20, 30, 30),
            possessor_id=1,
            frame_width=1920,
            frame_height=1080,
        ),
        FrameData(
            frame_index=1,
            timestamp=0.033,
            players=[PlayerDetection(track_id=1, bbox=BoundingBox(2, 2, 52, 102))],
            frame_width=1920,
            frame_height=1080,
        ),
    ]
    rim = BoundingBox(400, 100, 450, 130)

    json_str = serialize_detection_cache(frames, rim)

    # Verify it's valid JSON
    parsed = json.loads(json_str)
    assert "frames" in parsed
    assert "rim_position" in parsed
    assert len(parsed["frames"]) == 2

    # Round-trip
    restored_frames, restored_rim = deserialize_detection_cache(json_str)
    assert len(restored_frames) == 2
    assert restored_frames[0].frame_index == 0
    assert restored_frames[0].players[0].track_id == 1
    assert restored_frames[0].ball is not None
    assert restored_frames[1].ball is None
    assert restored_rim is not None
    assert restored_rim.x1 == 400


def test_serialize_deserialize_no_rim():
    frames = [FrameData(frame_index=0, timestamp=0.0)]
    json_str = serialize_detection_cache(frames, rim_position=None)
    restored_frames, restored_rim = deserialize_detection_cache(json_str)
    assert restored_rim is None
    assert len(restored_frames) == 1


# --- Orchestrator cache path test ---


def test_run_highlights_from_cache_skips_detection():
    """Verify run_highlights_from_cache does not call run_detection."""
    # Mock heavy ML imports so test runs without ultralytics/cv2
    import sys
    from unittest.mock import MagicMock

    for mod in [
        "ultralytics", "cv2", "numpy", "inference",
        "pipeline.detection.ball_detector",
        "pipeline.detection.player_detector",
        "pipeline.detection.rim_detector",
    ]:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

    from pipeline.orchestrator import PipelineOrchestrator

    orchestrator = PipelineOrchestrator()

    cached_frames = [
        FrameData(
            frame_index=0, timestamp=0.0,
            players=[PlayerDetection(track_id=1, bbox=BoundingBox(0, 0, 50, 100))],
            frame_width=1920, frame_height=1080,
        ),
    ]
    rim = BoundingBox(400, 100, 450, 130)

    with patch.object(orchestrator, "run_detection") as mock_detect, \
         patch.object(orchestrator, "get_video_info", return_value={
             "fps": 30.0, "frame_count": 1, "width": 1920, "height": 1080, "duration": 0.033,
         }), \
         patch.object(orchestrator, "run_event_detection", return_value=([], [])), \
         patch.object(orchestrator, "run_clip_extraction", return_value={}):

        result = orchestrator.run_highlights_from_cache(
            video_path="/fake/video.mp4",
            output_dir="/tmp/test_output",
            cached_frames=cached_frames,
            rim_position=rim,
            selected_player_id=1,
        )

    # The key assertion: run_detection was never called
    mock_detect.assert_not_called()
    assert orchestrator._rim_position == rim
    assert result["event_count"] == 0
