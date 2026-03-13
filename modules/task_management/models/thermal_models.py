from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class DetectionResult:
    target_id: int
    category: str
    confidence: float
    position: str
    distance_m: float
    speed_kmh: float


@dataclass
class FramePacket:
    frame_bgr: np.ndarray
    source_fps: float = 0.0
    min_temp: Optional[float] = None
    max_temp: Optional[float] = None
    center_temp: Optional[float] = None
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class DetectionBatch:
    results: List[DetectionResult]
    latency_ms: int
    annotated_frame: np.ndarray
    steer_percent: int = 0
    brake_percent: int = 0
    battery_percent: int = 85

