import cv2
from ultralytics import YOLO
import collections
import numpy as np
import os
import json

# Create output directory for visualization frames
OUTPUT_DIR = "output_frames"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 1. Setup Models
# Use YOLO11m for better accuracy on players (class 0) and sports ball (class 32)
main_model = YOLO('yolo11m.pt')
# Use YOLO11n-pose for filtering ball detections near the face
pose_model = YOLO('yolo11n-pose.pt')

VIDEO_PATH = "pickup_game.mp4"
cap = cv2.VideoCapture(VIDEO_PATH)
fps = cap.get(cv2.CAP_PROP_FPS)

# Lower conf for ball (small/fast); 0.25 is default for players
BALL_CONF_THRESH = 0.15
PLAYER_CONF_THRESH = 0.25
IMG_SIZE = 1280 # High res for small ball detection

# possession_data: { player_id: [[start_time, end_time],...] }
possession_map = collections.defaultdict(list)
current_possessor = None
frame_count = 0
frames_with_ball = 0

# Track the last 10 frames to confirm stability
possession_history = collections.deque(maxlen=10)

# Main processing loop
# We track players using the main model
results_stream = main_model.track(
    source=VIDEO_PATH,
    tracker="botsort.yaml",
    persist=True,
    stream=True,
    conf=0.1, # Allow low conf detections for now, we filter later
    imgsz=IMG_SIZE
)

print(f"Processing {VIDEO_PATH} with YOLO11 + Pose Filtering...")

for result in results_stream:
    # For speed of testing, limit to 10 frames
    if frame_count >= 10:
        break
    
    frame_count += 1
    timestamp = frame_count / fps
    orig_img = result.orig_img
    annotated_frame = orig_img.copy()
    
    # --- 1. Extract Players & Ball ---
    players = []
    ball_candidates = []
    
    if result.boxes is not None:
        boxes = result.boxes.xyxy.cpu().numpy()
        ids = result.boxes.id.cpu().numpy() if result.boxes.id is not None else [None] * len(boxes)
        classes = result.boxes.cls.cpu().numpy()
        confs = result.boxes.conf.cpu().numpy()
        
        for i in range(len(boxes)):
            cls = int(classes[i])
            conf = confs[i]
            
            if cls == 0 and conf >= PLAYER_CONF_THRESH: # Person
                players.append({"id": ids[i], "box": boxes[i]})
            elif cls == 32 and conf >= BALL_CONF_THRESH: # Sports Ball
                ball_candidates.append({"box": boxes[i], "conf": conf})

    # --- 2. Pose Filtering (The Zero-Face Policy) ---
    # Get poses for all players in this frame
    pose_results = pose_model.predict(source=orig_img, conf=0.3, verbose=False, imgsz=IMG_SIZE)
    player_heads = [] # List of head bounding boxes or keypoint centers
    
    for pr in pose_results:
        if pr.keypoints is not None:
            # keypoints.xy: [num_persons, 17, 2]
            # COCO Keypoints: 0: nose, 1: l_eye, 2: r_eye, 3: l_ear, 4: r_ear
            kpts = pr.keypoints.xy.cpu().numpy()
            for person_kpts in kpts:
                # Get head keypoints (0-4)
                head_kpts = person_kpts[0:5]
                # Filter out [0,0] (not detected)
                valid_head = head_kpts[np.any(head_kpts != 0, axis=1)]
                if len(valid_head) > 0:
                    player_heads.append(valid_head)

    # Filter ball candidates: discard if center is too close to a nose/eye
    final_ball_box = None
    for ball in ball_candidates:
        bx1, by1, bx2, by2 = ball["box"]
        ball_center = np.array([(bx1 + bx2) / 2, (by1 + by2) / 2])
        is_face = False
        
        for head in player_heads:
            # Calculate distance from ball center to any head keypoint
            dists = np.linalg.norm(head - ball_center, axis=1)
            if np.any(dists < 30): # 30 pixels threshold for "face overlap"
                is_face = True
                break
        
        if not is_face:
            final_ball_box = ball["box"] # Take the most confident non-face ball
            frames_with_ball += 1
            break # Just take one ball for now

    # --- 3. Draw & Annotate ---
    # Draw players
    for p in players:
        px1, py1, px2, py2 = [int(c) for c in p["box"]]
        pid = p["id"] if p["id"] is not None else "?"
        cv2.rectangle(annotated_frame, (px1, py1), (px2, py2), (0, 255, 0), 2)
        cv2.putText(annotated_frame, f"P{pid}", (px1, py1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # Draw final ball
    if final_ball_box is not None:
        bx1, by1, bx2, by2 = [int(c) for c in final_ball_box]
        cv2.rectangle(annotated_frame, (bx1, by1), (bx2, by2), (0, 0, 255), 3)
        cv2.putText(annotated_frame, "BALL", (bx1, by1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    
    # Save frame
    cv2.imwrite(os.path.join(OUTPUT_DIR, f"frame_{frame_count:04d}.jpg"), annotated_frame)

    # --- 4. Possession Logic ---
    found_possessor_this_frame = None
    if final_ball_box is not None:
        bx1, by1, bx2, by2 = final_ball_box
        ball_center = ((bx1 + bx2) / 2, (by1 + by2) / 2)
    
        for p in players:
            px1, py1, px2, py2 = p["box"]
            # Ball center in player box
            if px1 <= ball_center[0] <= px2 and py1 <= ball_center[1] <= py2:
                found_possessor_this_frame = p["id"]
                break

    possession_history.append(found_possessor_this_frame)
    mc = collections.Counter(possession_history).most_common(1)
    stable_possessor = mc[0][0] if (mc and mc[0][1] >= 6) else None # 6/10 frames for stability
    
    if stable_possessor != current_possessor:
        if current_possessor is not None:
            possession_map[str(current_possessor)][-1][1] = timestamp
        if stable_possessor is not None:
            possession_map[str(stable_possessor)].append([timestamp, timestamp])
        current_possessor = stable_possessor

print(f"Finished processing {frame_count} frames.")
print(f"Ball detected in {frames_with_ball} frames.")
print(json.dumps(possession_map, indent=2))
