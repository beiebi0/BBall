import logging
import os
import tempfile
from typing import Callable, Optional

import cv2

from pipeline.detection.ball_detector import BallDetector
from pipeline.detection.player_detector import PlayerDetector
from pipeline.detection.rim_detector import RimDetector
from pipeline.events.event_detector import EventDetector
from pipeline.models import BoundingBox, FrameData, GameEvent, ClipSpec
from pipeline.tracking.possession import PossessionTracker
from pipeline.video.clip_extractor import ClipExtractor

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """
    Runs the full video processing pipeline end-to-end.

    Stages:
      1. Setup (0-10%)
      2. Detection & Tracking per-frame (10-60%)
      3. Event Detection (60-75%)
      4. Clip Extraction (75-90%)
      5. Compile highlight reels (90-98%)
      6. Done (98-100%)
    """

    def __init__(
        self,
        player_model_path: str = "models/yolov8n.pt",
        ball_model_path: str = "models/ball_detector_model.pt",
        tracker_config_path: str = "models/botsort.yaml",
        player_conf: float = 0.25,
        ball_conf: float = 0.10,
        smoothing_window: int = 10,
        clip_padding_before: float = 3.0,
        clip_padding_after: float = 2.0,
        roboflow_api_key: str = "",
        rim_model_id: str = "basketball-xil7x/1",
        rim_conf: float = 0.30,
        rim_num_samples: int = 10,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ):
        self.player_model_path = player_model_path
        self.ball_model_path = ball_model_path
        self.tracker_config_path = tracker_config_path
        self.player_conf = player_conf
        self.ball_conf = ball_conf
        self.smoothing_window = smoothing_window
        self.clip_padding_before = clip_padding_before
        self.clip_padding_after = clip_padding_after
        self.roboflow_api_key = roboflow_api_key
        self.rim_model_id = rim_model_id
        self.rim_conf = rim_conf
        self.rim_num_samples = rim_num_samples
        self._progress = progress_callback or (lambda p, m: None)
        self._rim_position: Optional[BoundingBox] = None

    def _report(self, pct: int, msg: str):
        logger.info("Progress %d%%: %s", pct, msg)
        self._progress(pct, msg)

    def get_video_info(self, video_path: str) -> dict:
        """Extract basic video metadata."""
        cap = cv2.VideoCapture(video_path)
        info = {
            "fps": cap.get(cv2.CAP_PROP_FPS),
            "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        }
        info["duration"] = info["frame_count"] / info["fps"] if info["fps"] > 0 else 0
        cap.release()
        return info

    def extract_preview_frame(self, video_path: str, time_sec: float = 5.0) -> Optional[bytes]:
        """Extract a single frame from the video for preview. Returns JPEG bytes."""
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_num = int(time_sec * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            return None

        _, jpeg = cv2.imencode(".jpg", frame)
        return jpeg.tobytes()

    def run_rim_detection(self, video_path: str) -> Optional[BoundingBox]:
        """Detect the basketball rim position from sampled frames.

        Returns None if no API key is set or detection fails.
        """
        if not self.roboflow_api_key:
            logger.info("No Roboflow API key set, skipping rim detection")
            return None

        self._report(8, "Detecting rim position")
        try:
            detector = RimDetector(
                model_id=self.rim_model_id,
                api_key=self.roboflow_api_key,
                conf_thresh=self.rim_conf,
            )
            return detector.detect_from_samples(video_path, num_samples=self.rim_num_samples)
        except Exception:
            logger.exception("Rim detection failed, falling back to heuristic")
            return None

    def run_detection(self, video_path: str) -> list[FrameData]:
        """
        Stage 1-2: Run player + ball detection on all frames.
        Returns per-frame data with possession info.
        """
        # Detect rim position before main detection loop
        self._rim_position = self.run_rim_detection(video_path)

        self._report(5, "Loading models")
        player_detector = PlayerDetector(
            model_path=self.player_model_path,
            tracker_config=self.tracker_config_path,
            conf_thresh=self.player_conf,
        )
        ball_detector = BallDetector(
            model_path=self.ball_model_path,
            conf_thresh=self.ball_conf,
        )
        possession_tracker = PossessionTracker(smoothing_window=self.smoothing_window)

        video_info = self.get_video_info(video_path)
        fps = video_info["fps"]
        total_frames = video_info["frame_count"]
        width = video_info["width"]
        height = video_info["height"]

        self._report(10, "Starting detection")
        all_frames: list[FrameData] = []

        for frame_idx, players, orig_img in player_detector.track_video(video_path):
            timestamp = frame_idx / fps if fps > 0 else 0

            # Detect ball in frame
            ball = ball_detector.detect(orig_img)

            # Update possession
            possessor = possession_tracker.update(timestamp, players, ball)

            frame_data = FrameData(
                frame_index=frame_idx,
                timestamp=timestamp,
                players=players,
                ball=ball,
                possessor_id=possessor,
                frame_width=width,
                frame_height=height,
            )
            all_frames.append(frame_data)

            # Report progress (10-60% range)
            if total_frames > 0 and frame_idx % 100 == 0:
                pct = 10 + int(50 * frame_idx / total_frames)
                self._report(pct, f"Processing frame {frame_idx}/{total_frames}")

        # Finalize possession tracking
        if all_frames:
            possession_tracker.finalize(all_frames[-1].timestamp)

        self._report(60, "Detection complete")
        return all_frames

    def run_event_detection(
        self, frames: list[FrameData], fps: float, duration: float
    ) -> tuple[list[GameEvent], list[ClipSpec]]:
        """Stage 3: Detect events and create clip specs."""
        self._report(62, "Detecting events")

        detector = EventDetector(
            fps=fps,
            clip_padding_before=self.clip_padding_before,
            clip_padding_after=self.clip_padding_after,
            rim_position=self._rim_position,
        )

        events = detector.detect_events(frames)
        logger.info("Detected %d events", len(events))
        self._report(70, f"Found {len(events)} events")

        clip_specs = detector.create_clip_specs(events, duration)
        logger.info("Created %d clip specs", len(clip_specs))
        self._report(75, f"Created {len(clip_specs)} clips")

        return events, clip_specs

    def run_clip_extraction(
        self,
        video_path: str,
        clip_specs: list[ClipSpec],
        output_dir: str,
    ) -> dict[str, str]:
        """
        Stages 4-5: Extract clips and compile reels.
        Returns dict with paths: {"game_reel": path, "player_reel": path (if applicable)}
        """
        self._report(76, "Extracting clips")

        extractor = ClipExtractor(work_dir=os.path.join(output_dir, "clips"))
        clip_paths = extractor.extract_clips(video_path, clip_specs)

        self._report(90, "Compiling game reel")

        results = {}

        # Game reel
        game_reel_path = os.path.join(output_dir, "game_highlights.mp4")
        if clip_paths:
            extractor.concatenate_clips(clip_paths, game_reel_path)
            results["game_reel"] = game_reel_path

        self._report(98, "Reels compiled")
        return results

    def run_full_pipeline(
        self,
        video_path: str,
        output_dir: str,
        selected_player_id: Optional[int] = None,
    ) -> dict:
        """
        Run the complete pipeline end-to-end.
        Returns dict with reel paths and event count.
        """
        os.makedirs(output_dir, exist_ok=True)

        # Stage 1-2: Detection
        video_info = self.get_video_info(video_path)
        frames = self.run_detection(video_path)

        # Stage 3: Event detection
        events, clip_specs = self.run_event_detection(
            frames, video_info["fps"], video_info["duration"]
        )

        # Stage 4-5: Clip extraction + compilation
        reel_paths = self.run_clip_extraction(video_path, clip_specs, output_dir)

        # Player-specific reel
        if selected_player_id is not None and clip_specs:
            event_detector = EventDetector(
                fps=video_info["fps"],
                clip_padding_before=self.clip_padding_before,
                clip_padding_after=self.clip_padding_after,
                rim_position=self._rim_position,
            )
            player_clips = event_detector.filter_clips_for_player(
                clip_specs, selected_player_id
            )
            if player_clips:
                self._report(95, "Compiling player reel")
                extractor = ClipExtractor(
                    work_dir=os.path.join(output_dir, "player_clips")
                )
                player_clip_paths = extractor.extract_clips(video_path, player_clips)
                player_reel_path = os.path.join(output_dir, "player_highlights.mp4")
                extractor.concatenate_clips(player_clip_paths, player_reel_path)
                reel_paths["player_reel"] = player_reel_path

        self._report(100, "Pipeline complete")

        return {
            "video_info": video_info,
            "event_count": len(events),
            "clip_count": len(clip_specs),
            "reel_paths": reel_paths,
        }
