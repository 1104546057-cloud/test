from __future__ import annotations

import math
import time
from typing import Optional, Tuple

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

from modules.task_management.adapters.thermal_camera_adapter import ThermalCameraAdapter
from modules.task_management.models.thermal_models import FramePacket


class ThermalService:
    """Unifies thermal sensor, camera stream and simulated source."""

    def __init__(self):
        self._mode = "sim"
        self._capture = None
        self._thermal_adapter: Optional[ThermalCameraAdapter] = None
        self._tick = 0
        self._last = None
        self._fps = 0.0

    @property
    def fps(self) -> float:
        if self._mode == "thermal" and self._thermal_adapter:
            return self._thermal_adapter.fps
        return self._fps

    def connect(self, source_text: str, device_text: str) -> None:
        self.disconnect()
        source = (source_text or "").strip()
        device = (device_text or "").strip()

        if source == "热成像摄像头" or device.upper().startswith("COM") or device.lower().startswith("serial://"):
            self._connect_thermal(device)
            return

        if source in {"本地摄像头", "网络摄像头", "本地视频文件"}:
            self._connect_video(source, device)
            return

        self._mode = "sim"

    def disconnect(self) -> None:
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception:
                pass
        self._capture = None
        if self._thermal_adapter is not None:
            self._thermal_adapter.disconnect()
        self._thermal_adapter = None
        self._mode = "sim"
        self._fps = 0.0
        self._last = None

    def read_frame(self) -> Optional[FramePacket]:
        if self._mode == "thermal":
            return self._read_thermal_frame()
        if self._mode == "video":
            return self._read_video_frame()
        return self._read_sim_frame()

    def _connect_thermal(self, device_text: str) -> None:
        port = device_text.replace("serial://", "").strip() or "/dev/ttyUSB0"
        self._thermal_adapter = ThermalCameraAdapter(port=port, baudrate=115200)
        self._thermal_adapter.connect()
        self._mode = "thermal"

    def _connect_video(self, source: str, device: str) -> None:
        if cv2 is None:
            raise RuntimeError("未安装 opencv-python，无法打开视频输入。")
        if source == "本地摄像头":
            index = int(device) if device.isdigit() else 0
            cap = cv2.VideoCapture(index)
        elif source == "网络摄像头":
            if not device:
                raise RuntimeError("网络摄像头请输入 rtsp/http 地址。")
            cap = cv2.VideoCapture(device)
        else:
            if not device:
                raise RuntimeError("本地视频文件请输入视频路径。")
            cap = cv2.VideoCapture(device)
        if not cap.isOpened():
            raise RuntimeError("视频输入打开失败，请检查设备或路径。")
        self._capture = cap
        self._mode = "video"

    def _read_video_frame(self) -> Optional[FramePacket]:
        if self._capture is None:
            return None
        ok, frame = self._capture.read()
        if not ok or frame is None:
            return None
        self._update_fps()
        return FramePacket(frame_bgr=frame, source_fps=self._fps)

    def _read_thermal_frame(self) -> Optional[FramePacket]:
        if self._thermal_adapter is None:
            return None
        temp_map = self._thermal_adapter.read_temperature_map()
        if temp_map is None:
            return None
        frame = self._thermal_to_colormap(temp_map)
        return FramePacket(
            frame_bgr=frame,
            source_fps=self._thermal_adapter.fps,
            min_temp=float(np.min(temp_map)),
            max_temp=float(np.max(temp_map)),
            center_temp=float(temp_map[temp_map.shape[0] // 2, temp_map.shape[1] // 2]),
            metadata={"mode": "thermal"},
        )

    def _read_sim_frame(self) -> FramePacket:
        self._tick += 1
        self._update_fps()
        temp_map = self._gen_sim_temp_map(self._tick)
        frame = self._thermal_to_colormap(temp_map)
        return FramePacket(
            frame_bgr=frame,
            source_fps=self._fps,
            min_temp=float(np.min(temp_map)),
            max_temp=float(np.max(temp_map)),
            center_temp=float(temp_map[temp_map.shape[0] // 2, temp_map.shape[1] // 2]),
            metadata={"mode": "simulation"},
        )

    def _update_fps(self) -> None:
        now = time.time()
        if self._last is None:
            self._last = now
            return
        dt = now - self._last
        self._last = now
        if dt > 0:
            fps = 1.0 / dt
            self._fps = fps if self._fps == 0.0 else (self._fps * 0.8 + fps * 0.2)

    @staticmethod
    def _gen_sim_temp_map(tick: int) -> np.ndarray:
        h, w = 24, 32
        y = np.linspace(0, h - 1, h)
        x = np.linspace(0, w - 1, w)
        yy, xx = np.meshgrid(y, x, indexing="ij")
        cx = 8 + 10 * (0.5 + 0.5 * math.sin(tick * 0.08))
        cy = 8 + 6 * (0.5 + 0.5 * math.cos(tick * 0.05))
        hotspot = np.exp(-(((xx - cx) ** 2) / 32 + ((yy - cy) ** 2) / 18)) * 17
        base = 22 + 2.2 * np.sin((xx + tick * 0.2) * 0.24) + 1.4 * np.cos((yy - tick * 0.13) * 0.35)
        noise = np.random.normal(0, 0.2, size=(h, w))
        return (base + hotspot + noise).astype(np.float32)

    @staticmethod
    def _thermal_to_colormap(temp_map: np.ndarray) -> np.ndarray:
        if cv2 is None:
            # fallback: 3-channel normalized frame
            norm = ((temp_map - temp_map.min()) / max(1e-6, temp_map.max() - temp_map.min()) * 255.0).astype(
                np.uint8
            )
            return np.dstack([norm, norm, norm])
        norm = ((temp_map - temp_map.min()) / max(1e-6, temp_map.max() - temp_map.min()) * 255.0).astype(np.uint8)
        img = cv2.resize(norm, (640, 480), interpolation=cv2.INTER_LINEAR)
        return cv2.applyColorMap(img, cv2.COLORMAP_JET)
