import pytest
import numpy as np
import os
import sys
from unittest.mock import MagicMock, patch

# Add backend to path for imports
sys.path.append(os.getcwd())

from pipeline.detection.player_detector import PlayerDetector
from pipeline.models import BoundingBox, PlayerDetection

@pytest.fixture
def detector():
    """Initialize detector with real weights for testing."""
    # The weight file exists in root (../yolo11m.pt from the backend dir)
    return PlayerDetector(
        model_path="../yolo11m.pt",
        tracker_config="models/botsort.yaml"
    )

def test_parse_result_empty(detector):
    """Test parsing a result with no detections."""
    mock_result = MagicMock()
    mock_result.boxes.xyxy.cpu().numpy.return_value = np.array([])
    mock_result.boxes.cls.cpu().numpy.return_value = np.array([])
    mock_result.boxes.id.cpu().numpy.return_value = None
    mock_result.boxes.conf.cpu().numpy.return_value = np.array([])
    
    players = detector._parse_result(mock_result)
    assert players == []

def test_parse_result_with_players(detector):
    """Test parsing a result containing multiple persons."""
    mock_result = MagicMock()
    # Mock 2 persons (class 0) and 1 sports ball (class 32)
    mock_result.boxes.xyxy.cpu().numpy.return_value = np.array([
        [10, 10, 50, 50],   # Person 1
        [100, 100, 150, 200], # Person 2
        [30, 30, 40, 40]     # Not a person
    ])
    mock_result.boxes.cls.cpu().numpy.return_value = np.array([0, 0, 32])
    mock_result.boxes.id.cpu().numpy.return_value = np.array([1, 2, 3])
    mock_result.boxes.conf.cpu().numpy.return_value = np.array([0.9, 0.8, 0.7])
    
    players = detector._parse_result(mock_result)
    
    assert len(players) == 2
    assert players[0].track_id == 1
    assert players[1].track_id == 2
    assert isinstance(players[0].bbox, BoundingBox)
    assert players[0].confidence == 0.9

def test_track_video_yields(detector):
    """Test the track_video generator yields expected data."""
    mock_result = MagicMock()
    mock_result.orig_img = np.zeros((100, 100, 3))
    mock_result.boxes.xyxy.cpu().numpy.return_value = np.array([[0, 0, 10, 10]])
    mock_result.boxes.cls.cpu().numpy.return_value = np.array([0])
    mock_result.boxes.id.cpu().numpy.return_value = np.array([1])
    mock_result.boxes.conf.cpu().numpy.return_value = np.array([0.95])
    
    # Mock the YOLO.track method using patch.object
    with patch.object(detector.model, 'track', return_value=[mock_result]):
        gen = detector.track_video("dummy_path")
        idx, players, frame = next(gen)
        
        assert idx == 0
        assert len(players) == 1
        assert players[0].track_id == 1
        assert frame.shape == (100, 100, 3)
