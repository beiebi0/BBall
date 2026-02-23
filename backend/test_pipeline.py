import os
import sys

# Add current directory to path so it can find 'pipeline'
sys.path.append(os.getcwd())

from pipeline.detection.player_detector import PlayerDetector
from pipeline.detection.ball_detector import BallDetector

VIDEO_PATH = "pickup_game.mp4"
if not os.path.exists(VIDEO_PATH):
    VIDEO_PATH = "../pickup_game.mp4"

def test_detectors():
    print(f"Testing ball detection coverage on {VIDEO_PATH}...")
    
    # 0. Check if video exists
    if not os.path.exists(VIDEO_PATH):
        print(f"ERROR: Video file not found at {VIDEO_PATH}")
        print("Please ensure you have a 'pickup_game.mp4' in the project root.")
        return

    # Initialize detectors (using model weights in root for now)
    player_det = PlayerDetector(model_path="yolo11m.pt", tracker_config="models/botsort.yaml")
    ball_det = BallDetector(model_path="yolo11m.pt", pose_model_path="yolo11n-pose.pt")
    
    # Run for 50 frames to ensure consistent detection
    frame_count = 0
    max_test_frames = 50
    missed_frames = []

    for idx, players, frame in player_det.track_video(VIDEO_PATH):
        if frame_count >= max_test_frames:
            break
            
        ball = ball_det.detect(frame)
        
        if not ball:
            print(f"FAILED: Ball NOT detected in Frame {idx}")
            missed_frames.append(idx)
        
        frame_count += 1

    if missed_frames:
        print(f"\nFAILURE: Ball missed in {len(missed_frames)}/{frame_count} frames.")
        print(f"Missed Frame indices: {missed_frames}")
        sys.exit(1)
    else:
        print(f"\nSUCCESS: Ball detected in all {frame_count} frames tested.")

if __name__ == "__main__":
    test_detectors()
