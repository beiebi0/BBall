import logging
from typing import Optional

import numpy as np
from ultralytics import YOLO

from pipeline.models import BoundingBox

logger = logging.getLogger(__name__)


class BallDetector:
    """Custom YOLO model for basketball detection."""

    def __init__(
        self,
        model_path: str = "models/ball_detector_model.pt",
        conf_thresh: float = 0.10,
    ):
        self.model = YOLO(model_path)
        self.conf_thresh = conf_thresh

    def detect(self, frame: np.ndarray) -> Optional[BoundingBox]:
        """Detect ball in a single frame. Returns highest-confidence ball bbox or None."""
        preds = self.model.predict(source=frame, conf=self.conf_thresh, verbose=False)

        for pred in preds:
            boxes = pred.boxes.xyxy.cpu().numpy()
            classes = pred.boxes.cls.cpu().numpy()
            confs = pred.boxes.conf.cpu().numpy()

            best_conf = -1.0
            best_box = None

            for i, cls in enumerate(classes):
                if int(cls) == 0 and confs[i] > best_conf:  # Class 0 = Ball
                    best_conf = float(confs[i])
                    best_box = BoundingBox(
                        x1=float(boxes[i][0]),
                        y1=float(boxes[i][1]),
                        x2=float(boxes[i][2]),
                        y2=float(boxes[i][3]),
                    )

            if best_box is not None:
                return best_box

        return None
