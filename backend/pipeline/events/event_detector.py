import logging
from typing import Optional

from pipeline.models import BoundingBox, ClipSpec, FrameData, GameEvent

logger = logging.getLogger(__name__)


class EventDetector:
    """
    MVP event detection from per-frame tracking data.
    Detects: possession changes, potential scores, fast breaks.
    """

    def __init__(
        self,
        fps: float,
        clip_padding_before: float = 3.0,
        clip_padding_after: float = 2.0,
        rim_position: Optional[BoundingBox] = None,
        rim_proximity_radius: float = 1.5,
    ):
        self.fps = fps
        self.padding_before = clip_padding_before
        self.padding_after = clip_padding_after
        self.rim_position = rim_position
        self.rim_proximity_radius = rim_proximity_radius

    def detect_events(self, frames: list[FrameData]) -> list[GameEvent]:
        """Analyze all frames and produce game events."""
        events: list[GameEvent] = []
        events.extend(self._detect_possession_changes(frames))
        events.extend(self._detect_potential_scores(frames))
        events.extend(self._detect_fast_breaks(frames))

        events.sort(key=lambda e: e.frame_start)
        return events

    def create_clip_specs(
        self,
        events: list[GameEvent],
        video_duration: float,
    ) -> list[ClipSpec]:
        """Convert events to clip specs with padding, merging overlapping clips."""
        if not events:
            return []

        raw_clips: list[ClipSpec] = []
        for event in events:
            start = max(0.0, event.time_start - self.padding_before)
            end = min(video_duration, event.time_end + self.padding_after)
            raw_clips.append(ClipSpec(start_time=start, end_time=end, events=[event]))

        # Merge overlapping clips
        raw_clips.sort(key=lambda c: c.start_time)
        merged: list[ClipSpec] = [raw_clips[0]]

        for clip in raw_clips[1:]:
            last = merged[-1]
            if clip.start_time <= last.end_time:
                last.end_time = max(last.end_time, clip.end_time)
                last.events.extend(clip.events)
            else:
                merged.append(clip)

        return merged

    def filter_clips_for_player(
        self, clips: list[ClipSpec], player_track_id: int
    ) -> list[ClipSpec]:
        """Filter clips to only those involving a specific player."""
        player_clips = []
        for clip in clips:
            involved = any(
                e.player_track_id == player_track_id
                or e.metadata.get("prev_possessor") == player_track_id
                or e.metadata.get("new_possessor") == player_track_id
                for e in clip.events
            )
            if involved:
                player_clips.append(clip)
        return player_clips

    def _detect_possession_changes(self, frames: list[FrameData]) -> list[GameEvent]:
        """Detect when ball possession changes between players."""
        events = []
        prev_possessor: Optional[int] = None

        for frame in frames:
            if frame.possessor_id is not None and frame.possessor_id != prev_possessor:
                if prev_possessor is not None:
                    events.append(
                        GameEvent(
                            event_type="possession_change",
                            frame_start=frame.frame_index,
                            frame_end=frame.frame_index,
                            time_start=frame.timestamp,
                            time_end=frame.timestamp,
                            player_track_id=frame.possessor_id,
                            metadata={
                                "prev_possessor": prev_possessor,
                                "new_possessor": frame.possessor_id,
                            },
                        )
                    )
                prev_possessor = frame.possessor_id

        return events

    def _detect_potential_scores(self, frames: list[FrameData]) -> list[GameEvent]:
        """Detect potential scores using rim proximity or upper-quarter fallback."""
        if self.rim_position is not None:
            return self._detect_scores_rim_proximity(frames)
        return self._detect_scores_upper_quarter_fallback(frames)

    def _is_near_rim(self, ball: BoundingBox) -> bool:
        """Check if ball center is within the expanded rim zone."""
        rim = self.rim_position
        # Expand rim bbox by the proximity radius factor
        rim_cx, rim_cy = rim.center
        half_w = rim.width / 2 * self.rim_proximity_radius
        half_h = rim.height / 2 * self.rim_proximity_radius

        bx, by = ball.center
        return (
            rim_cx - half_w <= bx <= rim_cx + half_w
            and rim_cy - half_h <= by <= rim_cy + half_h
        )

    def _detect_scores_rim_proximity(self, frames: list[FrameData]) -> list[GameEvent]:
        """Detect potential scores by checking ball proximity to detected rim."""
        events = []
        in_score_zone = False
        zone_start_frame: Optional[FrameData] = None

        for frame in frames:
            if frame.ball is not None:
                if self._is_near_rim(frame.ball):
                    if not in_score_zone:
                        in_score_zone = True
                        zone_start_frame = frame
                else:
                    if in_score_zone and zone_start_frame is not None:
                        events.append(
                            GameEvent(
                                event_type="potential_score",
                                frame_start=zone_start_frame.frame_index,
                                frame_end=frame.frame_index,
                                time_start=zone_start_frame.timestamp,
                                time_end=frame.timestamp,
                                confidence=0.8,
                                metadata={"detection_method": "rim_proximity"},
                            )
                        )
                        in_score_zone = False
                        zone_start_frame = None
            else:
                if in_score_zone and zone_start_frame is not None:
                    events.append(
                        GameEvent(
                            event_type="potential_score",
                            frame_start=zone_start_frame.frame_index,
                            frame_end=frame.frame_index,
                            time_start=zone_start_frame.timestamp,
                            time_end=frame.timestamp,
                            confidence=0.6,
                            metadata={"detection_method": "rim_proximity"},
                        )
                    )
                    in_score_zone = False
                    zone_start_frame = None

        return events

    def _detect_scores_upper_quarter_fallback(self, frames: list[FrameData]) -> list[GameEvent]:
        """Fallback: detect ball in upper quarter of frame as potential score."""
        events = []
        in_score_zone = False
        zone_start_frame: Optional[FrameData] = None

        for frame in frames:
            if frame.ball is not None and frame.frame_height > 0:
                ball_y = frame.ball.center[1]
                upper_quarter = frame.frame_height * 0.25

                if ball_y < upper_quarter:
                    if not in_score_zone:
                        in_score_zone = True
                        zone_start_frame = frame
                else:
                    if in_score_zone and zone_start_frame is not None:
                        events.append(
                            GameEvent(
                                event_type="potential_score",
                                frame_start=zone_start_frame.frame_index,
                                frame_end=frame.frame_index,
                                time_start=zone_start_frame.timestamp,
                                time_end=frame.timestamp,
                                confidence=0.5,
                                metadata={"detection_method": "upper_quarter"},
                            )
                        )
                        in_score_zone = False
                        zone_start_frame = None
            else:
                if in_score_zone and zone_start_frame is not None:
                    events.append(
                        GameEvent(
                            event_type="potential_score",
                            frame_start=zone_start_frame.frame_index,
                            frame_end=frame.frame_index,
                            time_start=zone_start_frame.timestamp,
                            time_end=frame.timestamp,
                            confidence=0.3,
                            metadata={"detection_method": "upper_quarter"},
                        )
                    )
                    in_score_zone = False
                    zone_start_frame = None

        return events

    def _detect_fast_breaks(self, frames: list[FrameData]) -> list[GameEvent]:
        """Detect rapid ball movement across frame (>60% width in <3s)."""
        events = []
        window_frames = int(self.fps * 3)  # 3 second window

        ball_positions = []
        for frame in frames:
            if frame.ball is not None:
                ball_positions.append(
                    (frame.frame_index, frame.timestamp, frame.ball.center[0], frame.frame_width)
                )

        for i, (idx, ts, x, w) in enumerate(ball_positions):
            if w == 0:
                continue
            for j in range(i + 1, len(ball_positions)):
                j_idx, j_ts, j_x, j_w = ball_positions[j]
                if j_idx - idx > window_frames:
                    break
                displacement = abs(j_x - x) / w
                if displacement > 0.6:
                    events.append(
                        GameEvent(
                            event_type="fast_break",
                            frame_start=idx,
                            frame_end=j_idx,
                            time_start=ts,
                            time_end=j_ts,
                            confidence=min(1.0, displacement),
                            metadata={"displacement_pct": displacement},
                        )
                    )
                    break  # One fast break per starting position

        return events
