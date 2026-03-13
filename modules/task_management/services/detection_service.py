from __future__ import annotations

import random
import time
from typing import List

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

from modules.task_management.models.thermal_models import DetectionBatch, DetectionResult


class DetectionService:
    """Mock detection pipeline for Windows-side framework validation."""

    def __init__(self):
        self._battery = 85

    def infer(self, frame_bgr: np.ndarray, confidence_threshold: float) -> DetectionBatch:
        t0 = time.perf_counter()
        h, w = frame_bgr.shape[:2]
        results: List[DetectionResult] = []
        annotated = frame_bgr.copy()

        # Build 1~3 synthetic targets to keep UI and data flow active.
        count = random.randint(1, 3)
        for idx in range(count):
            x1 = random.randint(20, max(25, w - 150))
            y1 = random.randint(20, max(25, h - 120))
            bw = random.randint(60, 120)
            bh = random.randint(40, 100)
            x2 = min(w - 1, x1 + bw)
            y2 = min(h - 1, y1 + bh)
            conf = round(random.uniform(max(0.35, confidence_threshold), 0.95), 2)
            category = random.choice(["person", "vehicle", "heat-source"])

            if cv2 is not None:
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (28, 255, 188), 2)
                cv2.putText(
                    annotated,
                    f"{category} {conf:.2f}",
                    (x1, max(15, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    1,
                )

            center_x = int((x1 + x2) / 2)
            center_y = int((y1 + y2) / 2)
            results.append(
                DetectionResult(
                    target_id=idx + 1,
                    category=category,
                    confidence=conf,
                    position=f"({center_x},{center_y})",
                    distance_m=round(random.uniform(2.0, 25.0), 1),
                    speed_kmh=round(random.uniform(0.0, 8.5), 1),
                )
            )

        latency_ms = int((time.perf_counter() - t0) * 1000)
        self._battery = max(0, self._battery - random.randint(0, 1))
        return DetectionBatch(
            results=results,
            latency_ms=max(1, latency_ms),
            annotated_frame=annotated,
            steer_percent=random.randint(-70, 70),
            brake_percent=random.randint(0, 100),
            battery_percent=self._battery,
        )

