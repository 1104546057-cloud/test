import sys
import time
import serial

HEADER = b"\x5A\x5A\x06\x02"

port = sys.argv[1] if len(sys.argv) > 1 else "COM3"
baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

ser = serial.Serial(port, baud, timeout=0.1)
buf = bytearray()

count = 0
t0 = time.time()
last_print = t0

print(f"Listening on {port} @ {baud}")

while True:
    chunk = ser.read(4096)
    if chunk:
        buf.extend(chunk)

    # 数帧头出现次数
    while True:
        idx = buf.find(HEADER)
        if idx < 0:
            break
        count += 1
        del buf[:idx + len(HEADER)]

    now = time.time()
    if now - last_print >= 1.0:
        fps = count / (now - t0)
        print(f"avg fps: {fps:.2f}, frames: {count}, elapsed: {now - t0:.1f}s")
        last_print = now