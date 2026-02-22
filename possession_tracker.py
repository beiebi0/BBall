import cv2
from ultralytics import YOLO
import collections
import numpy as np
import os

# Create output directory for visualization frames
OUTPUT_DIR = "output_frames"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 1. Setup Mac GPU (MPS)
player_model = YOLO('yolov8n.pt')
ball_model = YOLO('ball_detector_model.pt')


video_path = "pickup_game.mp4"
cap = cv2.VideoCapture(video_path)
fps = cap.get(cv2.CAP_PROP_FPS)

# Lower conf so small/fast ball detections are kept (default 0.25; ball often low-conf)
CONF_THRESH = 0.10

# Set to True to print how often the ball is detected (debug)
DEBUG_BALL_DETECTION = True

# possession_data: { player_id: [[start_time, end_time],...] }
possession_map = collections.defaultdict(list)
current_possessor = None
start_frame = 0
frame_count = 0
frames_with_ball = 0

# Track the last 10 frames to confirm stability (the "10-frame rule")
possession_history = collections.deque(maxlen=10)

player_results = player_model.track(
    source=video_path,
    tracker="botsort.yaml",
    persist=True,
    stream=True,
    conf=CONF_THRESH,
)

for player_result in player_results:
    if frame_count > 10 :
        break
    frame_count += 1
    timestamp = frame_count / fps
    
    # Extract player bounding boxes and IDs from player_model
    player_boxes = player_result.boxes.xyxy.cpu().numpy()
    player_ids = player_result.boxes.id.cpu().numpy() if player_result.boxes.id is not None else np.array([])
    player_classes = player_result.boxes.cls.cpu().numpy()
    
    players = []
    for i, cls in enumerate(player_classes):
        if int(cls) == 0:  # COCO class 0 = 'person'
            if player_ids is not None and i < len(player_ids):
                players.append({"id": int(player_ids[i]), "box": player_boxes[i]})

    ball_box = None
    # Detect ball using ball_model
    ball_preds = ball_model.predict(source=player_result.orig_img, conf=CONF_THRESH, verbose=False)
    for ball_pred in ball_preds:
        ball_boxes = ball_pred.boxes.xyxy.cpu().numpy()
        ball_classes = ball_pred.boxes.cls.cpu().numpy()
        
        for i, cls in enumerate(ball_classes):
            if int(cls) == 0:  # Class 'Ball'
                ball_box = ball_boxes[i]
                frames_with_ball += 1
                break # Found a ball, no need to check other classes in this prediction
        if ball_box is not None:
            break # Found a ball in this prediction, no need to check other predictions

    # Draw bounding boxes and save frame
    annotated_frame = player_result.orig_img.copy() # Make a copy to draw on

    # Draw player bounding boxes
    for player in players:
        px1, py1, px2, py2 = [int(c) for c in player["box"]]
        player_id = player["id"]
        cv2.rectangle(annotated_frame, (px1, py1), (px2, py2), (0, 255, 0), 2) # Green box for players
        cv2.putText(annotated_frame, f"P{player_id}", (px1, py1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # Draw ball bounding box
    if ball_box is not None:
        bx1, by1, bx2, by2 = [int(c) for c in ball_box]
        cv2.rectangle(annotated_frame, (bx1, by1), (bx2, by2), (0, 0, 255), 2) # Red box for ball
        cv2.putText(annotated_frame, "Ball", (bx1, by1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    
    # Save annotated frame
    frame_filename = os.path.join(OUTPUT_DIR, f"frame_{frame_count:04d}.jpg")
    cv2.imwrite(frame_filename, annotated_frame)

    if DEBUG_BALL_DETECTION:
        if ball_box is not None:
            print(f"Frame {frame_count}: Ball detected.")
        else:
            print(f"Frame {frame_count}: No ball detected.")

    # 2. Possession Logic: Ball-in-Box
    found_possessor_this_frame = None
    if ball_box is not None:
        bx1, by1, bx2, by2 = ball_box
        ball_center = ((bx1 + bx2) / 2, (by1 + by2) / 2)
        print(f"ball center:{ball_center}")
    
        for player in players:
            px1, py1, px2, py2 = player["box"]
            # Check if ball center is within player bounding box
            if px1 <= ball_center[0] <= px2 and py1 <= ball_center[1] <= py2:
                found_possessor_this_frame = player["id"]
                break

    # 3. Temporal Smoothing (Stability check)
    possession_history.append(found_possessor_this_frame)
    
    # If the same player has the ball for most of the last 10 frames
    # most_common(1) returns [(player_id, count)] or []; we need the player_id
    mc = collections.Counter(possession_history).most_common(1)
    stable_possessor = mc[0][0] if mc else None
    
    if stable_possessor != current_possessor:
        # Close the previous interval
        if current_possessor is not None:
            possession_map[current_possessor][-1][1] = timestamp
        
        # Start a new interval
        if stable_possessor is not None:
            possession_map[stable_possessor].append([timestamp, timestamp])
        
        current_possessor = stable_possessor

# Print final result
import json
if DEBUG_BALL_DETECTION:
    print(f"Ball detected in {frames_with_ball}/{frame_count} frames ({100.0 * frames_with_ball / max(1, frame_count):.1f}%)")
print(json.dumps(possession_map, indent=2))
