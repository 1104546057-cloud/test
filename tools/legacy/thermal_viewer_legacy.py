import sys
import time
import struct
import serial
import numpy as np
import cv2

HEADER = b"\x5A\x5A\x06\x02"
PAYLOAD_WORDS = 770
FRAME_LEN = 4 + PAYLOAD_WORDS * 2  # 1544 bytes


class ThermalViewerFast:
    def __init__(self, port="COM3", baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.buffer = bytearray()

        self.scale = 10
        self.window_name = "IR_FAST"

        self.use_fixed_range = True
        self.fixed_min = 15.0
        self.fixed_max = 40.0

        self.src_last = None
        self.src_fps = 0.0

        self.disp_last = None
        self.disp_fps = 0.0

    def open(self):
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0.005,
        )
        try:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        except Exception:
            pass

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    def update_src_fps(self):
        now = time.time()
        if self.src_last is None:
            self.src_last = now
            return
        dt = now - self.src_last
        self.src_last = now
        if dt > 0:
            fps = 1.0 / dt
            self.src_fps = fps if self.src_fps == 0 else (0.8 * self.src_fps + 0.2 * fps)

    def update_disp_fps(self):
        now = time.time()
        if self.disp_last is None:
            self.disp_last = now
            return
        dt = now - self.disp_last
        self.disp_last = now
        if dt > 0:
            fps = 1.0 / dt
            self.disp_fps = fps if self.disp_fps == 0 else (0.8 * self.disp_fps + 0.2 * fps)

    def get_latest_frame(self):
        # 尽量把串口缓存吃掉
        while True:
            chunk = self.ser.read(4096)
            if not chunk:
                break
            self.buffer.extend(chunk)

        # 找所有帧头
        positions = []
        start = 0
        while True:
            idx = self.buffer.find(HEADER, start)
            if idx < 0:
                break
            positions.append(idx)
            start = idx + 1

        if not positions:
            if len(self.buffer) > FRAME_LEN * 8:
                del self.buffer[:-FRAME_LEN]
            return None

        # 只取最后一个完整帧
        last_idx = positions[-1]
        if len(self.buffer) < last_idx + FRAME_LEN:
            if len(positions) >= 2:
                last_idx = positions[-2]
            else:
                return None

        if len(self.buffer) < last_idx + FRAME_LEN:
            return None

        frame = bytes(self.buffer[last_idx:last_idx + FRAME_LEN])

        # 丢掉旧数据
        del self.buffer[:last_idx + FRAME_LEN]

        self.update_src_fps()
        return frame

    @staticmethod
    def parse_frame(frame: bytes):
        payload = frame[4:]
        words = struct.unpack(">" + "H" * PAYLOAD_WORDS, payload)
        temp_map = np.array(words[:768], dtype=np.float32).reshape(24, 32) / 100.0
        return temp_map

    def render(self, temp_map):
        tmin = float(np.min(temp_map))
        tmax = float(np.max(temp_map))

        if self.use_fixed_range:
            dmin = self.fixed_min
            dmax = self.fixed_max
        else:
            dmin = tmin
            dmax = tmax

        if dmax - dmin < 0.01:
            norm = np.zeros_like(temp_map, dtype=np.uint8)
        else:
            norm = ((temp_map - dmin) * 255.0 / (dmax - dmin)).clip(0, 255).astype(np.uint8)

        # 尽量轻：LINEAR、小尺寸、少文字
        img = cv2.resize(
            norm,
            (32 * self.scale, 24 * self.scale),
            interpolation=cv2.INTER_LINEAR
        )
        img = cv2.applyColorMap(img, cv2.COLORMAP_JET)

        h, w = img.shape[:2]
        cy, cx = temp_map.shape[0] // 2, temp_map.shape[1] // 2
        center_temp = float(temp_map[cy, cx])

        hot_y, hot_x = np.unravel_index(np.argmax(temp_map), temp_map.shape)
        hot_temp = float(temp_map[hot_y, hot_x])

        cold_y, cold_x = np.unravel_index(np.argmin(temp_map), temp_map.shape)
        cold_temp = float(temp_map[cold_y, cold_x])

        hot_px = int((hot_x + 0.5) * self.scale)
        hot_py = int((hot_y + 0.5) * self.scale)

        cv2.drawMarker(img, (w // 2, h // 2), (255, 255, 255),
                       markerType=cv2.MARKER_CROSS, markerSize=14, thickness=2)
        cv2.drawMarker(img, (hot_px, hot_py), (255, 255, 255),
                       markerType=cv2.MARKER_TILTED_CROSS, markerSize=12, thickness=2)

        # 左上角同时显示源帧率和显示帧率
        cv2.putText(img, f"SRC:{self.src_fps:.2f}  DISP:{self.disp_fps:.2f}",
                    (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # 底栏
        bar_h = 28
        canvas = np.zeros((h + bar_h, w, 3), dtype=np.uint8)
        canvas[:h] = img
        canvas[h:] = (30, 30, 30)

        cv2.putText(canvas, f"Max:{hot_temp:.1f}°", (8, h + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        cv2.putText(canvas, f"Mid:{center_temp:.1f}°", (w // 2 - 38, h + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        cv2.putText(canvas, f"Min:{cold_temp:.1f}°", (w - 95, h + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        return canvas

    def run(self):
        self.open()
        cv2.namedWindow(self.window_name, cv2.WINDOW_AUTOSIZE)

        try:
            while True:
                frame = self.get_latest_frame()
                if frame is not None:
                    temp_map = self.parse_frame(frame)
                    img = self.render(temp_map)
                    self.update_disp_fps()
                    cv2.imshow(self.window_name, img)

                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
                elif key == ord("f"):
                    self.use_fixed_range = not self.use_fixed_range

        finally:
            self.close()
            cv2.destroyAllWindows()


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM3"
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    viewer = ThermalViewerFast(port, baudrate)
    viewer.run()


if __name__ == "__main__":
    main()