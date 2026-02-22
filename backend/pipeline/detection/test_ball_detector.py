import pytest
import numpy as np
import os
import sys

# The pytest-specific unit test for BallDetector
from pipeline.detection.ball_detector import BallDetector
from pipeline.models import BoundingBox

@pytest.fixture
def detector():
    """Initialize detector with local weights for integration testing."""
    # Using relative paths from the backend/ directory
    return BallDetector(
        model_path="../yolo11m.pt",
        pose_model_path="../yolo11n-pose.pt",
        conf_thresh=0.15
    )

def test_detect_black_frame(detector):
    """Test detection on a solid black frame (should return None)."""
    black_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    result = detector.detect(black_frame)
    assert result is None

def test_bounding_box_logic():
    """Verify BoundingBox dataclass methods."""
    bbox = BoundingBox(x1=100, y1=100, x2=200, y2=300)
    assert bbox.center == (150, 200)
    assert bbox.width == 100
    assert bbox.height == 200
    assert bbox.contains_point(150, 250) is True
    assert bbox.contains_point(50, 50) is False

def test_detect_invalid_input(detector):
    """Test how the detector handles an empty array."""
    with pytest.raises(Exception):
        detector.detect(np.array([]))

def test_zero_face_threshold_logic(detector):
    """
    This is a structural test to ensure the detector 
    has the expected attributes after initialization.
    """
    assert detector.conf_thresh == 0.15
    assert detector.imgsz == 1280
    assert hasattr(detector, 'pose_model')
