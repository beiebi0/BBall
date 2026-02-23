import os
import sys
import cv2
import numpy as np

# Add current directory to path so it can find 'pipeline'
sys.path.append(os.getcwd())

from pipeline.detection.player_detector import PlayerDetector
from pipeline.detection.ball_detector import BallDetector
from pipeline.detection.hoop_detector import HoopDetector

VIDEO_PATH = "pickup_game.mp4"
if not os.path.exists(VIDEO_PATH):
    VIDEO_PATH = "../pickup_game.mp4"

OUTPUT_DIR = "test_output"

def test_full_detection():
    print(f"--- Full Detection Integration Test (Visual): {VIDEO_PATH} ---")
    
    # 0. Check if video exists
    if not os.path.exists(VIDEO_PATH):
        print(f"ERROR: Video file not found at {VIDEO_PATH}")
        print("Please ensure you have a 'pickup_game.mp4' in the project root.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 1. Initialize Detectors
    try:
        # Use existing models in root
        player_det = PlayerDetector(model_path="../yolo11m.pt", tracker_config="models/botsort.yaml")
        ball_det = BallDetector(model_path="../yolo11m.pt", pose_model_path="../yolo11n-pose.pt")
        # HoopDetector uses Roboflow API (configured via ROBOFLOW_API_KEY env var)
        hoop_det = HoopDetector()
    except Exception as e:
        print(f"ERROR: Failed to initialize detectors: {e}")
        return
    
    # 2. Process first 2 frames for better visual confirmation
    frame_count = 0
    max_frames = 2

    for idx, players, frame in player_det.track_video(VIDEO_PATH):
        if frame_count >= max_frames:
            break
            
        # Run detection
        ball = ball_det.detect(frame)
        hoop = hoop_det.detect(frame)
        
        # --- Draw Results on Frame ---
        annotated_frame = frame.copy()
        
        # Draw Players (Green)
        for p in players:
            x1, y1, x2, y2 = [int(c) for c in [p.bbox.x1, p.bbox.y1, p.bbox.x2, p.bbox.y2]]
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # Draw Ball (Red)
        if ball:
            bx1, by1, bx2, by2 = [int(c) for c in [ball.x1, ball.y1, ball.x2, ball.y2]]
            cv2.rectangle(annotated_frame, (bx1, by1), (bx2, by2), (0, 0, 255), 3)

        # Draw Hoop Rim (Cyan)
        if hoop:
            hx1, hy1, hx2, hy2 = [int(c) for c in [hoop.x1, hoop.y1, hoop.x2, hoop.y2]]
            cv2.rectangle(annotated_frame, (hx1, hy1), (hx2, hy2), (255, 255, 0), 4)
            cv2.putText(annotated_frame, "RIM", (hx1, hy1 - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        
        # Save Frame
        out_path = os.path.join(OUTPUT_DIR, f"hoop_test_{idx:04d}.jpg")
        cv2.imwrite(out_path, annotated_frame)
        
        print(f"Frame {idx}: Players={len(players)}, Ball={'Yes' if ball else 'No'}, Hoop={'Yes' if hoop else 'No'}. Saved to {out_path}")
        frame_count += 1

    print(f"\n--- Visual Test Complete. Check frames in {OUTPUT_DIR}/ ---")

if __name__ == "__main__":
    test_full_detection()
