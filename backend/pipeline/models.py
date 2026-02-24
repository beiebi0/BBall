import json
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

    def to_dict(self) -> dict:
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}

    @classmethod
    def from_dict(cls, d: dict) -> "BoundingBox":
        return cls(x1=d["x1"], y1=d["y1"], x2=d["x2"], y2=d["y2"])


@dataclass
class PlayerDetection:
    track_id: int
    bbox: BoundingBox
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "bbox": self.bbox.to_dict(),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PlayerDetection":
        return cls(
            track_id=d["track_id"],
            bbox=BoundingBox.from_dict(d["bbox"]),
            confidence=d.get("confidence", 0.0),
        )


@dataclass
class FrameData:
    frame_index: int
    timestamp: float
    players: list[PlayerDetection] = field(default_factory=list)
    ball: Optional[BoundingBox] = None
    hoop: Optional[BoundingBox] = None
    possessor_id: Optional[int] = None
    frame_width: int = 0
    frame_height: int = 0

    def to_dict(self) -> dict:
        return {
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "players": [p.to_dict() for p in self.players],
            "ball": self.ball.to_dict() if self.ball else None,
            "hoop": self.hoop.to_dict() if self.hoop else None,
            "possessor_id": self.possessor_id,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FrameData":
        return cls(
            frame_index=d["frame_index"],
            timestamp=d["timestamp"],
            players=[PlayerDetection.from_dict(p) for p in d.get("players", [])],
            ball=BoundingBox.from_dict(d["ball"]) if d.get("ball") else None,
            hoop=BoundingBox.from_dict(d["hoop"]) if d.get("hoop") else None,
            possessor_id=d.get("possessor_id"),
            frame_width=d.get("frame_width", 0),
            frame_height=d.get("frame_height", 0),
        )


def serialize_detection_cache(
    frames: list["FrameData"],
    rim_position: Optional[BoundingBox] = None,
) -> str:
    """Serialize detection results to a JSON string for caching between phases."""
    return json.dumps({
        "rim_position": rim_position.to_dict() if rim_position else None,
        "frames": [f.to_dict() for f in frames],
    })


def deserialize_detection_cache(
    data: str,
) -> tuple[list["FrameData"], Optional[BoundingBox]]:
    """Deserialize cached detection results. Returns (frames, rim_position)."""
    parsed = json.loads(data)
    rim = BoundingBox.from_dict(parsed["rim_position"]) if parsed.get("rim_position") else None
    frames = [FrameData.from_dict(f) for f in parsed["frames"]]
    return frames, rim


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
