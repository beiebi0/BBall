import logging
from typing import Optional

import cv2
import numpy as np

from pipeline.models import BoundingBox

logger = logging.getLogger(__name__)


class RimDetector:
    """Detects the basketball rim position using a Roboflow model.

    Since the rim is static in fixed-camera footage, we only need to detect
    it on a few sampled frames and reuse that position for the entire video.
    """

    def __init__(
        self,
        model_id: str,
        api_key: str,
        conf_thresh: float = 0.30,
    ):
        self.model_id = model_id
        self.api_key = api_key
        self.conf_thresh = conf_thresh
        self._model = None

    def _load_model(self):
        if self._model is None:
            from inference import get_model

            self._model = get_model(self.model_id, api_key=self.api_key)

    def detect_from_samples(
        self, video_path: str, num_samples: int = 10
    ) -> Optional[BoundingBox]:
        """Sample N evenly-spaced frames from the video and detect the rim.

        Returns the median bounding box after IQR outlier filtering,
        or None if no detections were found.
        """
        self._load_model()

        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if total_frames <= 0:
            cap.release()
            return None

        # Skip first/last 5% of the video
        start_frame = int(total_frames * 0.05)
        end_frame = int(total_frames * 0.95)
        usable = end_frame - start_frame

        if usable <= 0:
            cap.release()
            return None

        step = max(1, usable // num_samples)
        sample_indices = list(range(start_frame, end_frame, step))[:num_samples]

        detections: list[BoundingBox] = []
        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue

            det = self.detect_single_frame(frame)
            if det is not None:
                detections.append(det)

        cap.release()

        if not detections:
            logger.warning("No rim detected in any of %d sampled frames", len(sample_indices))
            return None

        result = self._compute_stable_position(detections)
        if result is not None:
            cx, cy = result.center
            logger.info(
                "Rim detected at center (%.0f, %.0f) from %d/%d frames",
                cx, cy, len(detections), len(sample_indices),
            )
        return result

    def detect_single_frame(self, frame: np.ndarray) -> Optional[BoundingBox]:
        """Run inference on a single frame, return highest-confidence detection."""
        results = self._model.infer(frame, confidence=self.conf_thresh)

        # The inference SDK returns a list of results per image
        if not results or not hasattr(results[0], "predictions"):
            return None

        preds = results[0].predictions
        if not preds:
            return None

        # Pick highest confidence
        best = max(preds, key=lambda p: p.confidence)

        # Roboflow returns center-x, center-y, width, height
        cx, cy = best.x, best.y
        w, h = best.width, best.height
        return BoundingBox(
            x1=cx - w / 2,
            y1=cy - h / 2,
            x2=cx + w / 2,
            y2=cy + h / 2,
        )

    def _compute_stable_position(
        self, detections: list[BoundingBox]
    ) -> Optional[BoundingBox]:
        """Filter outliers via IQR on center coordinates and return median bbox."""
        if len(detections) < 2:
            return detections[0] if detections else None

        centers_x = np.array([d.center[0] for d in detections])
        centers_y = np.array([d.center[1] for d in detections])

        mask_x = self._iqr_mask(centers_x)
        mask_y = self._iqr_mask(centers_y)
        mask = mask_x & mask_y

        filtered = [d for d, m in zip(detections, mask) if m]
        if not filtered:
            # Fall back to all detections if IQR removes everything
            filtered = detections

        # Compute median bounding box
        x1 = float(np.median([d.x1 for d in filtered]))
        y1 = float(np.median([d.y1 for d in filtered]))
        x2 = float(np.median([d.x2 for d in filtered]))
        y2 = float(np.median([d.y2 for d in filtered]))

        return BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)

    @staticmethod
    def _iqr_mask(values: np.ndarray, factor: float = 1.5) -> np.ndarray:
        """Return boolean mask where True = inlier (within IQR bounds)."""
        q1 = np.percentile(values, 25)
        q3 = np.percentile(values, 75)
        iqr = q3 - q1
        lower = q1 - factor * iqr
        upper = q3 + factor * iqr
        return (values >= lower) & (values <= upper)
