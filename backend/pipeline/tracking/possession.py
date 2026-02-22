import collections
import logging
from typing import Optional

from pipeline.models import BoundingBox, FrameData, GameEvent, PlayerDetection

logger = logging.getLogger(__name__)


class PossessionTracker:
    """
    Ball possession tracking with temporal smoothing.
    Refactored from the original possession_tracker.py.
    """

    def __init__(self, smoothing_window: int = 10):
        self.smoothing_window = smoothing_window
        self.history: collections.deque = collections.deque(maxlen=smoothing_window)
        self.current_possessor: Optional[int] = None
        self.possession_intervals: dict[int, list[list[float]]] = collections.defaultdict(list)

    def update(
        self,
        timestamp: float,
        players: list[PlayerDetection],
        ball: Optional[BoundingBox],
    ) -> Optional[int]:
        """
        Process one frame. Returns stable possessor track_id or None.
        Uses ball-in-box logic with temporal smoothing.
        """
        found = self._find_possessor(players, ball)
        self.history.append(found)

        # Majority vote over smoothing window
        mc = collections.Counter(self.history).most_common(1)
        stable = mc[0][0] if mc else None

        if stable != self.current_possessor:
            # Close previous interval
            if self.current_possessor is not None:
                self.possession_intervals[self.current_possessor][-1][1] = timestamp

            # Start new interval
            if stable is not None:
                self.possession_intervals[stable].append([timestamp, timestamp])

            self.current_possessor = stable

        return stable

    def _find_possessor(
        self, players: list[PlayerDetection], ball: Optional[BoundingBox]
    ) -> Optional[int]:
        """Check if ball center falls within any player's bounding box."""
        if ball is None:
            return None

        cx, cy = ball.center
        for player in players:
            if player.bbox.contains_point(cx, cy):
                return player.track_id
        return None

    def get_possession_changes(self) -> list[dict]:
        """Return possession interval data for all players."""
        return dict(self.possession_intervals)

    def finalize(self, final_timestamp: float) -> None:
        """Close the last open interval."""
        if self.current_possessor is not None:
            intervals = self.possession_intervals[self.current_possessor]
            if intervals and intervals[-1][1] == intervals[-1][0]:
                intervals[-1][1] = final_timestamp
