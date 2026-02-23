import logging
import os
from typing import Optional

import numpy as np
from roboflow import Roboflow
from dotenv import load_dotenv

from pipeline.models import BoundingBox

logger = logging.getLogger(__name__)


class HoopDetector:
    """
    Hoop and rim detector using Roboflow API.
    Optimized for static cameras by caching the detection.
    Project: basketball-project-zbcse (v3)
    Classes: 0: basket, 1: rim
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        conf_thresh: float = 0.3,
    ):
        """
        Args:
            api_key: Roboflow API Key. If None, looks for ROBOFLOW_API_KEY in env.
            conf_thresh: Confidence threshold (0-1).
        """
        load_dotenv()
        self.api_key = api_key or os.getenv("ROBOFLOW_API_KEY")
        self.conf_thresh = conf_thresh
        
        if not self.api_key:
            logger.warning("No Roboflow API key provided. Hoop detection will be disabled.")
            self.model = None
        else:
            try:
                rf = Roboflow(api_key=self.api_key)
                project = rf.workspace("figuring-out").project("basketball-project-zbcse")
                self.model = project.version(3).model
                logger.info("Initialized Roboflow hoop detection model.")
            except Exception as e:
                logger.error(f"Failed to initialize Roboflow model: {e}")
                self.model = None
            
        self._cached_hoop: Optional[BoundingBox] = None

    def detect(self, frame: np.ndarray, use_cache: bool = True) -> Optional[BoundingBox]:
        """
        Detect the rim using Roboflow hosted API.
        If use_cache is True and a hoop was previously detected,
        returns the cached bounding box to save computation/API costs.
        """
        if use_cache and self._cached_hoop is not None:
            return self._cached_hoop

        if not self.model:
            return None

        # Roboflow inference
        try:
            results = self.model.predict(frame, confidence=int(self.conf_thresh * 100)).json()
        except Exception as e:
            logger.error(f"Roboflow inference failed: {e}")
            return None
        
        predictions = results.get("predictions", [])
        if not predictions:
            return None

        # Filter for highest confidence prediction
        best_pred = None
        max_conf = 0

        for pred in predictions:
            if pred["confidence"] > max_conf:
                max_conf = pred["confidence"]
                best_pred = pred

        if best_pred:
            # Roboflow returns {x, y, width, height} (center-based)
            width = best_pred["width"]
            height = best_pred["height"]
            x_center = best_pred["x"]
            y_center = best_pred["y"]

            self._cached_hoop = BoundingBox(
                x1=float(x_center - width / 2),
                y1=float(y_center - height / 2),
                x2=float(x_center + width / 2),
                y2=float(y_center + height / 2),
            )
            return self._cached_hoop

        return None

    def clear_cache(self):
        """Reset the cached hoop position."""
        self._cached_hoop = None
