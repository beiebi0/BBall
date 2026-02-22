from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    def contains_point(self, x: float, y: float) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


@dataclass
class PlayerDetection:
    track_id: int
    bbox: BoundingBox
    confidence: float = 0.0


@dataclass
class FrameData:
    frame_index: int
    timestamp: float
    players: list[PlayerDetection] = field(default_factory=list)
    ball: Optional[BoundingBox] = None
    possessor_id: Optional[int] = None
    frame_width: int = 0
    frame_height: int = 0


@dataclass
class GameEvent:
    event_type: str
    frame_start: int
    frame_end: int
    time_start: float
    time_end: float
    player_track_id: Optional[int] = None
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)


@dataclass
class ClipSpec:
    start_time: float
    end_time: float
    events: list[GameEvent] = field(default_factory=list)
