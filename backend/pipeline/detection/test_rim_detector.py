import pytest
import numpy as np
from unittest.mock import MagicMock, patch, PropertyMock

from pipeline.detection.rim_detector import RimDetector
from pipeline.models import BoundingBox


@pytest.fixture
def detector():
    """Create a RimDetector without loading the actual model."""
    d = RimDetector(
        model_id="basketball-xil7x/1",
        api_key="test-key",
        conf_thresh=0.30,
    )
    d._model = MagicMock()
    return d


# --- _iqr_mask tests ---

def test_iqr_mask_all_inliers():
    """All values within IQR bounds should be marked True."""
    values = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
    mask = RimDetector._iqr_mask(values)
    assert mask.all()


def test_iqr_mask_detects_outlier():
    """A value far from the cluster should be marked False."""
    values = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    mask = RimDetector._iqr_mask(values)
    assert mask[:4].all()
    assert not mask[4]


def test_iqr_mask_identical_values():
    """All identical values should be inliers (IQR = 0)."""
    values = np.array([50.0, 50.0, 50.0, 50.0])
    mask = RimDetector._iqr_mask(values)
    assert mask.all()


# --- _compute_stable_position tests ---

def test_compute_stable_single_detection(detector):
    """A single detection should be returned as-is."""
    bbox = BoundingBox(x1=100, y1=50, x2=200, y2=100)
    result = detector._compute_stable_position([bbox])
    assert result == bbox


def test_compute_stable_returns_none_empty(detector):
    """Empty list should return None."""
    result = detector._compute_stable_position([])
    assert result is None


def test_compute_stable_median_of_consistent_detections(detector):
    """Consistent detections should produce their median."""
    detections = [
        BoundingBox(x1=100, y1=50, x2=200, y2=100),
        BoundingBox(x1=102, y1=52, x2=202, y2=102),
        BoundingBox(x1=104, y1=54, x2=204, y2=104),
    ]
    result = detector._compute_stable_position(detections)
    assert result.x1 == 102.0
    assert result.y1 == 52.0
    assert result.x2 == 202.0
    assert result.y2 == 102.0


def test_compute_stable_filters_outlier(detector):
    """An outlier detection should be removed before computing median."""
    detections = [
        BoundingBox(x1=100, y1=50, x2=200, y2=100),
        BoundingBox(x1=102, y1=52, x2=202, y2=102),
        BoundingBox(x1=104, y1=54, x2=204, y2=104),
        BoundingBox(x1=106, y1=56, x2=206, y2=106),
        BoundingBox(x1=800, y1=600, x2=900, y2=700),  # outlier
    ]
    result = detector._compute_stable_position(detections)
    # Outlier should be excluded; median of first 4
    assert result.x1 == pytest.approx(103.0)
    assert result.y1 == pytest.approx(53.0)


# --- detect_single_frame tests ---

def _make_prediction(x, y, w, h, confidence):
    pred = MagicMock()
    pred.x = x
    pred.y = y
    pred.width = w
    pred.height = h
    pred.confidence = confidence
    return pred


def test_detect_single_frame_returns_best(detector):
    """Should return the highest-confidence detection as a BoundingBox."""
    pred1 = _make_prediction(x=300, y=100, w=60, h=40, confidence=0.5)
    pred2 = _make_prediction(x=310, y=105, w=62, h=42, confidence=0.9)

    mock_result = MagicMock()
    mock_result.predictions = [pred1, pred2]
    detector._model.infer.return_value = [mock_result]

    result = detector.detect_single_frame(np.zeros((720, 1280, 3), dtype=np.uint8))

    assert result is not None
    assert result.center[0] == pytest.approx(310.0)
    assert result.center[1] == pytest.approx(105.0)
    assert result.width == pytest.approx(62.0)
    assert result.height == pytest.approx(42.0)


def test_detect_single_frame_no_predictions(detector):
    """Should return None when model finds no predictions."""
    mock_result = MagicMock()
    mock_result.predictions = []
    detector._model.infer.return_value = [mock_result]

    result = detector.detect_single_frame(np.zeros((720, 1280, 3), dtype=np.uint8))
    assert result is None


def test_detect_single_frame_no_results(detector):
    """Should return None when model returns empty results."""
    detector._model.infer.return_value = []
    result = detector.detect_single_frame(np.zeros((720, 1280, 3), dtype=np.uint8))
    assert result is None


# --- detect_from_samples tests ---

def test_detect_from_samples_returns_stable_position(detector):
    """End-to-end test with mocked video and model."""
    pred = _make_prediction(x=300, y=100, w=60, h=40, confidence=0.8)
    mock_result = MagicMock()
    mock_result.predictions = [pred]
    detector._model.infer.return_value = [mock_result]

    # Mock cv2.VideoCapture
    mock_cap = MagicMock()
    mock_cap.get.side_effect = lambda prop: {
        0: 30.0,   # CAP_PROP_POS_MSEC (unused)
        3: 1280.0,  # CAP_PROP_FRAME_WIDTH
        4: 720.0,   # CAP_PROP_FRAME_HEIGHT
        5: 30.0,    # CAP_PROP_FPS
        7: 300.0,   # CAP_PROP_FRAME_COUNT
    }.get(prop, 0)
    mock_cap.read.return_value = (True, np.zeros((720, 1280, 3), dtype=np.uint8))

    with patch("cv2.VideoCapture", return_value=mock_cap):
        result = detector.detect_from_samples("dummy.mp4", num_samples=3)

    assert result is not None
    assert result.center[0] == pytest.approx(300.0)
    assert result.center[1] == pytest.approx(100.0)


def test_detect_from_samples_no_frames(detector):
    """Should return None for a video with no frames."""
    mock_cap = MagicMock()
    mock_cap.get.return_value = 0  # total_frames = 0

    with patch("cv2.VideoCapture", return_value=mock_cap):
        result = detector.detect_from_samples("empty.mp4")

    assert result is None


def test_detect_from_samples_no_detections(detector):
    """Should return None when model detects nothing in any frame."""
    mock_result = MagicMock()
    mock_result.predictions = []
    detector._model.infer.return_value = [mock_result]

    mock_cap = MagicMock()
    mock_cap.get.side_effect = lambda prop: {7: 300.0}.get(prop, 0)
    mock_cap.read.return_value = (True, np.zeros((720, 1280, 3), dtype=np.uint8))

    with patch("cv2.VideoCapture", return_value=mock_cap):
        result = detector.detect_from_samples("dummy.mp4", num_samples=3)

    assert result is None


# --- Constructor / lazy loading tests ---

def test_init_stores_config():
    """Verify constructor stores config without loading model."""
    d = RimDetector(model_id="test/1", api_key="key123", conf_thresh=0.5)
    assert d.model_id == "test/1"
    assert d.api_key == "key123"
    assert d.conf_thresh == 0.5
    assert d._model is None


def test_load_model_called_once(detector):
    """_load_model should not reload if model already set."""
    detector._model = MagicMock()
    existing_model = detector._model
    detector._load_model()
    assert detector._model is existing_model
