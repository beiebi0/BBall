import logging
from typing import Optional

import numpy as np
from ultralytics import YOLO

from pipeline.models import BoundingBox

logger = logging.getLogger(__name__)


class BallDetector:
    """Custom YOLO model for basketball detection with Zero-Face filtering."""

    def __init__(
        self,
        model_path: str = "yolo11m.pt",
        pose_model_path: str = "yolo11n-pose.pt",
        conf_thresh: float = 0.15,
        imgsz: int = 1280,
    ):
        self.model = YOLO(model_path)
        self.pose_model = YOLO(pose_model_path)
        self.conf_thresh = conf_thresh
        self.imgsz = imgsz

    def detect(self, frame: np.ndarray) -> Optional[BoundingBox]:
        """
        Detect ball in a single frame using Zero-Face Policy.
        Returns the highest-confidence non-face ball bbox or None.
        """
        # 1. Get ball candidates from main model (class 32)
        results = self.model.predict(
            source=frame, conf=self.conf_thresh, imgsz=self.imgsz, verbose=False
        )
        
        ball_candidates = []
        for r in results:
            if r.boxes is not None:
                boxes = r.boxes.xyxy.cpu().numpy()
                classes = r.boxes.cls.cpu().numpy()
                confs = r.boxes.conf.cpu().numpy()
                
                for i in range(len(boxes)):
                    if int(classes[i]) == 32:  # Sports ball
                        ball_candidates.append({
                            "box": boxes[i],
                            "conf": float(confs[i])
                        })

        if not ball_candidates:
            return None

        # 2. Extract player head keypoints using pose model
        pose_results = self.pose_model.predict(
            source=frame, conf=0.3, imgsz=self.imgsz, verbose=False
        )
        player_heads = []
        for pr in pose_results:
            if pr.keypoints is not None:
                # COCO head keypoints (nose, eyes, ears) are 0-4
                kpts = pr.keypoints.xy.cpu().numpy()
                for person_kpts in kpts:
                    head_kpts = person_kpts[0:5]
                    # Filter out [0,0] (not detected)
                    valid_head = head_kpts[np.any(head_kpts != 0, axis=1)]
                    if len(valid_head) > 0:
                        player_heads.append(valid_head)

        # 3. Filter ball candidates: discard if center is too close to a face
        # Sort by confidence so we check the most likely ball first
        ball_candidates.sort(key=lambda x: x["conf"], reverse=True)
        
        for ball in ball_candidates:
            bx1, by1, bx2, by2 = ball["box"]
            ball_center = np.array([(bx1 + bx2) / 2, (by1 + by2) / 2])
            is_face = False
            
            for head in player_heads:
                dists = np.linalg.norm(head - ball_center, axis=1)
                if np.any(dists < 30):  # 30 pixels threshold for "face overlap"
                    is_face = True
                    break
            
            if not is_face:
                return BoundingBox(
                    x1=float(bx1),
                    y1=float(by1),
                    x2=float(bx2),
                    y2=float(by2),
                )

        return None
