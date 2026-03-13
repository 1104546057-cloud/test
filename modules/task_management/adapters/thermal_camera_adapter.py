from __future__ import annotations

import struct
import time
from typing import Optional, Tuple

import numpy as np

try:
    import serial
except Exception:  # pragma: no cover
    serial = None


HEADER = b"\x5A\x5A\x06\x02"
PAYLOAD_WORDS = 770
FRAME_LEN = 4 + PAYLOAD_WORDS * 2


class ThermalCameraAdapter:
    """Read 24x32 thermal frames from UART sensor."""

    def __init__(self, port: str = "COM3", baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self._ser = None
        self._buffer = bytearray()
        self._last = None
        self._fps = 0.0

    @property
    def fps(self) -> float:
        return self._fps

    def connect(self) -> None:
        if serial is None:
            raise RuntimeError("未安装 pyserial，无法连接热成像串口设备。")
        self._ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0.005,
        )
        try:
            self._ser.reset_input_buffer()
            self._ser.reset_output_buffer()
        except Exception:
            pass

    def disconnect(self) -> None:
        if self._ser is not None and self._ser.is_open:
            self._ser.close()
        self._ser = None
        self._buffer.clear()

    def read_temperature_map(self) -> Optional[np.ndarray]:
        if self._ser is None:
            return None
        frame = self._read_latest_frame()
        if frame is None:
            return None
        return self._parse_frame(frame)

    def _read_latest_frame(self) -> Optional[bytes]:
        while True:
            chunk = self._ser.read(4096)
            if not chunk:
                break
            self._buffer.extend(chunk)

        positions = []
        start = 0
        while True:
            idx = self._buffer.find(HEADER, start)
            if idx < 0:
                break
            positions.append(idx)
            start = idx + 1

        if not positions:
            if len(self._buffer) > FRAME_LEN * 8:
                del self._buffer[:-FRAME_LEN]
            return None

        last_idx = positions[-1]
        if len(self._buffer) < last_idx + FRAME_LEN:
            if len(positions) >= 2:
                last_idx = positions[-2]
            else:
                return None

        if len(self._buffer) < last_idx + FRAME_LEN:
            return None

        frame = bytes(self._buffer[last_idx:last_idx + FRAME_LEN])
        del self._buffer[:last_idx + FRAME_LEN]
        self._update_fps()
        return frame

    @staticmethod
    def _parse_frame(frame: bytes) -> np.ndarray:
        payload = frame[4:]
        words = struct.unpack(">" + "H" * PAYLOAD_WORDS, payload)
        return np.array(words[:768], dtype=np.float32).reshape(24, 32) / 100.0

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

