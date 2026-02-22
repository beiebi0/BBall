import logging
from typing import Iterator

import numpy as np
from ultralytics import YOLO

from pipeline.models import BoundingBox, FrameData, PlayerDetection

logger = logging.getLogger(__name__)


class PlayerDetector:
    """YOLO11m + BotSORT player detection and tracking."""

    def __init__(
        self,
        model_path: str = "yolo11m.pt",
        tracker_config: str = "models/botsort.yaml",
        conf_thresh: float = 0.25,
        imgsz: int = 1280,
    ):
        self.model = YOLO(model_path)
        self.tracker_config = tracker_config
        self.conf_thresh = conf_thresh
        self.imgsz = imgsz

    def track_video(self, video_path: str) -> Iterator[tuple[int, list[PlayerDetection], np.ndarray]]:
        """
        Stream player detections frame-by-frame.
        Yields (frame_index, players, original_frame) tuples.
        """
        # Run tracking at 1280 resolution
        results = self.model.track(
            source=video_path,
            tracker=self.tracker_config,
            persist=True,
            stream=True,
            conf=self.conf_thresh,
            imgsz=self.imgsz,
        )

        for frame_idx, result in enumerate(results):
            players = self._parse_result(result)
            yield frame_idx, players, result.orig_img

    def _parse_result(self, result) -> list[PlayerDetection]:
        """Extract person detections with track IDs from a YOLO result."""
        players = []
        boxes = result.boxes.xyxy.cpu().numpy()
        classes = result.boxes.cls.cpu().numpy()
        ids = result.boxes.id.cpu().numpy() if result.boxes.id is not None else np.array([])
        confs = result.boxes.conf.cpu().numpy()

        for i, cls in enumerate(classes):
            if int(cls) == 0 and i < len(ids):  # COCO class 0 = person
                bbox = BoundingBox(
                    x1=float(boxes[i][0]),
                    y1=float(boxes[i][1]),
                    x2=float(boxes[i][2]),
                    y2=float(boxes[i][3]),
                )
                players.append(
                    PlayerDetection(
                        track_id=int(ids[i]),
                        bbox=bbox,
                        confidence=float(confs[i]),
                    )
                )

        return players
