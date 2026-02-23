import pytest
import cv2
import os
import numpy as np
from pipeline.detection.hoop_detector import HoopDetector
from pipeline.models import BoundingBox

@pytest.fixture
def detector():
    """Initialize detector with Roboflow API key from env."""
    api_key = os.getenv("ROBOFLOW_API_KEY")
    return HoopDetector(api_key=api_key, conf_thresh=0.2)

def test_detect_hoop_from_image(detector):
    """Detect hoop from an image in the test_output directory."""
    image_path = "/Users/beiebi0/BBall/backend/test_output/frame_0000.jpg"
    if not os.path.exists(image_path):
        pytest.skip(f"Image {image_path} not found.")

    frame = cv2.imread(image_path)
    assert frame is not None, "Failed to load test image."

    # First detection - should hit the API (or local model)
    hoop = detector.detect(frame, use_cache=False)
    
    # We expect a hoop to be detected in this frame
    assert hoop is not None, "Hoop should be detected in the test frame."
    assert isinstance(hoop, BoundingBox)
    print(f"Hoop detected at: {hoop}")

def test_hoop_caching(detector):
    """Verify that caching works for the static hoop."""
    image_path = "/Users/beiebi0/BBall/backend/test_output/frame_0000.jpg"
    if not os.path.exists(image_path):
        pytest.skip(f"Image {image_path} not found.")

    frame = cv2.imread(image_path)
    
    # Detect first time
    hoop1 = detector.detect(frame, use_cache=True)
    if hoop1 is None:
        pytest.skip("No hoop detected, cannot test caching.")
    
    # Detect second time - should return cached value
    hoop2 = detector.detect(frame, use_cache=True)
    
    assert hoop1 == hoop2, "Cached hoop should be identical."

def test_detect_black_frame(detector):
    """Test on a solid black frame (should return None)."""
    # Note: Roboflow might return a false positive if the model is overfit, 
    # but normally it should return None.
    black_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    # We clear the cache first
    detector.clear_cache()
    result = detector.detect(black_frame, use_cache=False)
    # This might depend on the model's performance on blank images
    # but we'll assert it's None if the model is decent.
    # If this fails, we can adjust.
    assert result is None or (result.width == 0 and result.height == 0)
