from __future__ import annotations

from collections import deque
from datetime import datetime
import math
import os
import platform
import socket
import threading
import time
from typing import Any

try:
    import psutil
except ImportError:  # optional dependency during early setup
    psutil = None

try:
    from jtop import jtop as JTopClient
except ImportError:  # Jetson-only dependency
    JTopClient = None

try:
    import roslibpy
except ImportError:  # optional runtime dependency
    roslibpy = None


class MonitoringService:
    """Collect monitoring data from optional local providers."""

    def __init__(self, history_size: int = 30):
        self.history_size = max(5, history_size)
        self._speed_history: deque[float] = deque(maxlen=self.history_size)
        self._disk_prev = None
        self._disk_prev_ts = None
        self._net_prev = None
        self._net_prev_ts = None
        self._jtop = None
        self._jtop_connected = False
        self._system_info_cache: dict[str, Any] | None = None
        self._last_snapshot: dict[str, Any] | None = None
        self._last_error: dict[str, str] | None = None
        self._ros = None
        self._ros_thread = None
        self._ros_connected = False
        self._odom_topic = None
        self._odom_subscribed = False
        self._odom_last_at = 0.0
        self._latest_motion = {
            "speed_mps": 0.0,
            "position_text": "Telemetry pending",
            "map_status": "ROS unavailable",
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
        }

    def start(self) -> bool:
        self._ensure_jtop()
        self._start_ros()
        self._system_info_cache = self._collect_system_info()
        self.refresh()
        return True

    def stop(self) -> None:
        if self._jtop is not None:
            try:
                close = getattr(self._jtop, "close", None)
                if callable(close):
                    close()
            except Exception:
                pass
        self._jtop = None
        self._jtop_connected = False
        if self._odom_topic is not None:
            try:
                self._odom_topic.unsubscribe()
            except Exception:
                pass
        self._odom_topic = None
        self._odom_subscribed = False
        if self._ros is not None:
            try:
                self._ros.terminate()
            except Exception:
                pass
        self._ros = None
        self._ros_connected = False

    def refresh(self) -> dict[str, Any]:
        self._ensure_ros_subscription()
        snapshot = self._collect_snapshot()
        self._last_snapshot = snapshot
        return snapshot

    def get_snapshot(self) -> dict[str, Any]:
        if self._last_snapshot is None:
            return self.refresh()
        return self._last_snapshot

    def get_system_info(self) -> dict[str, Any]:
        if self._system_info_cache is None:
            self._system_info_cache = self._collect_system_info()
        return self._system_info_cache

    def get_status_items(self) -> list[tuple[str, str]]:
        snapshot = self.get_snapshot()
        items = []
        status = snapshot["status"]
        items.append(("OK", "Monitoring service ready"))
        items.append(("OK" if status["jtop"] == "connected" else "INFO", f"jtop: {status['jtop']}"))
        items.append(("OK" if status["telemetry"] == "online" else "INFO", f"Telemetry: {status['telemetry']}"))
        if status["errors"]:
            items.append(("INFO", status["errors"][-1]))
        else:
            items.append(("OK", f"Updated at {status['updated_at']}"))
        return items

    def get_speed_series(self) -> dict[str, Any]:
        snapshot = self.get_snapshot()
        return {
            "unit": "m/s",
            "points": list(self._speed_history),
            "max_points": self.history_size,
            "updated_at": snapshot["status"]["updated_at"],
        }

    def get_last_error(self) -> dict[str, str] | None:
        return self._last_error

    def _collect_snapshot(self) -> dict[str, Any]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        jtop_ok = self._ensure_jtop()

        cpu = self._collect_cpu()
        gpu = self._collect_gpu()
        memory = self._collect_memory()
        disk = self._collect_disk()
        network = self._collect_network()
        power = self._collect_power()
        fan = self._collect_fan()
        current_speed = round(float(self._latest_motion.get("speed_mps", 0.0)), 2)
        self._speed_history.append(current_speed)
        motion = self._collect_motion(network)
        system = self.get_system_info()

        errors = []
        if psutil is None:
            errors.append("psutil not installed; using limited fallback data")
        if not jtop_ok:
            errors.append("jtop unavailable; Jetson-specific metrics are limited")
        if roslibpy is None:
            errors.append("roslibpy unavailable; motion telemetry is disabled")
        elif self._ros is not None and not self._ros_connected:
            errors.append("ROS bridge disconnected; waiting for /odom")

        return {
            "status": {
                "service": "ok",
                "jtop": "connected" if jtop_ok else "unavailable",
                "telemetry": self._telemetry_status(),
                "updated_at": now,
                "errors": errors,
            },
            "cpu": cpu,
            "gpu": gpu,
            "memory": memory,
            "disk": disk,
            "network": network,
            "power": power,
            "fan": fan,
            "motion": motion,
            "system": system,
        }

    def _collect_system_info(self) -> dict[str, Any]:
        info = {
            "model": platform.node() or "Unknown device",
            "module": "Unknown",
            "jetpack": "Unavailable",
            "l4t": "Unavailable",
            "cuda": "Unavailable",
            "tensorrt": "Unavailable",
            "cudnn": "Unavailable",
            "python": platform.python_version(),
            "distribution": platform.platform(),
            "system": platform.system(),
        }

        board = self._get_jtop_attr("board", {})
        hardware = board.get("hardware", {}) if isinstance(board, dict) else {}
        libraries = board.get("libraries", {}) if isinstance(board, dict) else {}
        platform_info = board.get("platform", {}) if isinstance(board, dict) else {}

        info["model"] = hardware.get("Model", info["model"])
        info["module"] = hardware.get("Module", info["module"])
        info["jetpack"] = hardware.get("Jetpack", info["jetpack"])
        info["l4t"] = hardware.get("L4T", info["l4t"])
        info["cuda"] = libraries.get("CUDA", info["cuda"])
        info["tensorrt"] = libraries.get("TensorRT", info["tensorrt"])
        info["cudnn"] = libraries.get("cuDNN", info["cudnn"])
        info["distribution"] = platform_info.get("Distribution", info["distribution"])
        info["system"] = platform_info.get("System", info["system"])
        info["python"] = platform_info.get("Python", info["python"])
        return info

    def _collect_cpu(self) -> dict[str, Any]:
        usage = 0.0
        per_core_usage: list[float] = []
        freq_mhz = 0.0
        max_freq_mhz = 0.0
        temp_c = self._read_temperature("CPU")

        if psutil is not None:
            try:
                per_core_usage = [float(v) for v in psutil.cpu_percent(interval=None, percpu=True)]
                usage = float(sum(per_core_usage) / len(per_core_usage)) if per_core_usage else 0.0
                freq = psutil.cpu_freq()
                if freq:
                    freq_mhz = float(freq.current or 0.0)
                    max_freq_mhz = float(freq.max or 0.0)
            except Exception as exc:
                self._remember_error("psutil", str(exc))

        cpu_data = self._get_jtop_attr("cpu", {})
        if isinstance(cpu_data, dict):
            total = cpu_data.get("total", {})
            if isinstance(total, dict):
                usage = float(total.get("user", usage) + total.get("system", 0.0))
            cpu_list = cpu_data.get("cpu", [])
            if isinstance(cpu_list, list) and cpu_list:
                per_core_usage = []
                for core in cpu_list:
                    if isinstance(core, dict):
                        per_core_usage.append(float(core.get("user", 0.0) + core.get("system", 0.0)))
                        freq_mhz = max(freq_mhz, float(core.get("freq", {}).get("cur", 0.0)) / 1000.0)

        return {
            "usage": round(usage, 1),
            "freq_mhz": round(freq_mhz, 1),
            "max_freq_mhz": round(max_freq_mhz, 1),
            "temp_c": round(temp_c, 1),
            "per_core_usage": [round(v, 1) for v in per_core_usage],
        }

    def _collect_gpu(self) -> dict[str, Any]:
        usage = 0.0
        freq_mhz = 0.0
        max_freq_mhz = 0.0
        temp_c = self._read_temperature("GPU")

        gpu_data = self._get_jtop_attr("gpu", {})
        gpu_entry = self._pick_first_mapping(gpu_data)
        if isinstance(gpu_entry, dict):
            status = gpu_entry.get("status", {})
            freq = gpu_entry.get("freq", {})
            usage = float(status.get("load", usage))
            freq_mhz = float(freq.get("cur", 0.0)) / 1000.0
            max_freq_mhz = float(freq.get("max", 0.0)) / 1000.0

        return {
            "usage": round(usage, 1),
            "freq_mhz": round(freq_mhz, 1),
            "max_freq_mhz": round(max_freq_mhz, 1),
            "temp_c": round(temp_c, 1),
        }

    def _collect_memory(self) -> dict[str, Any]:
        percent = 0.0
        used_gb = 0.0
        total_gb = 0.0
        free_gb = 0.0

        if psutil is not None:
            try:
                mem = psutil.virtual_memory()
                percent = float(mem.percent)
                used_gb = mem.used / (1024 ** 3)
                total_gb = mem.total / (1024 ** 3)
                free_gb = mem.available / (1024 ** 3)
            except Exception as exc:
                self._remember_error("psutil", str(exc))

        memory_data = self._get_jtop_attr("memory", {})
        if isinstance(memory_data, dict):
            total_mb = float(memory_data.get("tot", memory_data.get("total", 0.0)) or 0.0)
            used_mb = float(memory_data.get("used", 0.0) or 0.0)
            free_mb = float(memory_data.get("free", 0.0) or 0.0)
            if total_mb > 0:
                total_gb = total_mb / 1024.0
                used_gb = used_mb / 1024.0
                free_gb = free_mb / 1024.0 if free_mb else max(total_gb - used_gb, 0.0)
                percent = used_gb / total_gb * 100.0

        return {
            "percent": round(percent, 1),
            "used_gb": round(used_gb, 2),
            "total_gb": round(total_gb, 2),
            "free_gb": round(free_gb, 2),
        }

    def _collect_disk(self) -> dict[str, Any]:
        percent = 0.0
        used_gb = 0.0
        total_gb = 0.0
        free_gb = 0.0
        read_mb_s = 0.0
        write_mb_s = 0.0

        if psutil is not None:
            try:
                usage = psutil.disk_usage(os.path.abspath(os.sep))
                percent = float(usage.percent)
                used_gb = usage.used / (1024 ** 3)
                total_gb = usage.total / (1024 ** 3)
                free_gb = usage.free / (1024 ** 3)

                io = psutil.disk_io_counters()
                ts = datetime.now().timestamp()
                if io is not None and self._disk_prev is not None and self._disk_prev_ts is not None:
                    elapsed = max(ts - self._disk_prev_ts, 1e-6)
                    read_mb_s = (io.read_bytes - self._disk_prev.read_bytes) / elapsed / (1024 ** 2)
                    write_mb_s = (io.write_bytes - self._disk_prev.write_bytes) / elapsed / (1024 ** 2)
                self._disk_prev = io
                self._disk_prev_ts = ts
            except Exception as exc:
                self._remember_error("psutil", str(exc))

        disk_data = self._get_jtop_attr("disk", {})
        if isinstance(disk_data, dict) and disk_data.get("total"):
            total_gb = float(disk_data.get("total", total_gb))
            used_gb = float(disk_data.get("used", used_gb))
            free_gb = float(disk_data.get("available", free_gb))
            if total_gb > 0:
                percent = used_gb / total_gb * 100.0

        return {
            "percent": round(percent, 1),
            "used_gb": round(used_gb, 2),
            "total_gb": round(total_gb, 2),
            "free_gb": round(free_gb, 2),
            "read_mb_s": round(max(read_mb_s, 0.0), 2),
            "write_mb_s": round(max(write_mb_s, 0.0), 2),
        }

    def _collect_network(self) -> dict[str, Any]:
        bandwidth_mb_s = 0.0
        ip = "Unavailable"
        signal_percent = 0
        latency_ms = 0

        interfaces = self._get_jtop_attr("local_interfaces", {})
        if isinstance(interfaces, dict):
            all_ifaces = interfaces.get("interfaces", {})
            if isinstance(all_ifaces, dict):
                for name in ("eth0", "wlan0"):
                    addr = all_ifaces.get(name)
                    if addr:
                        ip = str(addr)
                        break

        if ip == "Unavailable":
            try:
                ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                pass

        if psutil is not None:
            try:
                io = psutil.net_io_counters()
                ts = datetime.now().timestamp()
                if io is not None and self._net_prev is not None and self._net_prev_ts is not None:
                    elapsed = max(ts - self._net_prev_ts, 1e-6)
                    bytes_delta = (io.bytes_sent + io.bytes_recv) - (self._net_prev.bytes_sent + self._net_prev.bytes_recv)
                    bandwidth_mb_s = bytes_delta / elapsed / (1024 ** 2)
                self._net_prev = io
                self._net_prev_ts = ts
            except Exception as exc:
                self._remember_error("psutil", str(exc))

        return {
            "signal_percent": signal_percent,
            "latency_ms": latency_ms,
            "bandwidth_mb_s": round(bandwidth_mb_s, 2),
            "ip": ip,
        }

    def _collect_power(self) -> dict[str, Any]:
        power = {
            "total_w": 0.0,
            "voltage_v": 0.0,
            "cpu_gpu_cv_w": 0.0,
            "soc_w": 0.0,
            "nvpmodel": str(self._get_jtop_attr("nvpmodel", "Unavailable")),
        }

        jtop_power = self._get_jtop_attr("power", {})
        if isinstance(jtop_power, dict):
            total = jtop_power.get("tot", {})
            if isinstance(total, dict):
                power["total_w"] = float(total.get("power", 0.0)) / 1000.0
                power["voltage_v"] = float(total.get("volt", 0.0)) / 1000.0
            rail = jtop_power.get("rail", {})
            if isinstance(rail, dict):
                power["cpu_gpu_cv_w"] = float(rail.get("VDD_CPU_GPU_CV", {}).get("power", 0.0)) / 1000.0
                power["soc_w"] = float(rail.get("VDD_SOC", {}).get("power", 0.0)) / 1000.0
        return {k: round(v, 2) if isinstance(v, float) else v for k, v in power.items()}

    def _collect_fan(self) -> dict[str, Any]:
        fan = {
            "exists": False,
            "rpm": 0,
            "speed_percent": 0,
            "profile": "Unavailable",
        }
        jtop_fan = self._get_jtop_attr("fan", {})
        fan_entry = self._pick_first_mapping(jtop_fan)
        if isinstance(fan_entry, dict):
            fan["exists"] = True
            speed = fan_entry.get("speed", [0])
            rpm = fan_entry.get("rpm", [0])
            fan["speed_percent"] = int(speed[0]) if isinstance(speed, list) and speed else int(speed or 0)
            fan["rpm"] = int(rpm[0]) if isinstance(rpm, list) and rpm else int(rpm or 0)
            fan["profile"] = str(fan_entry.get("profile", fan["profile"]))
        return fan

    def _collect_motion(self, network: dict[str, Any]) -> dict[str, Any]:
        motion = dict(self._latest_motion)
        if not self._ros_connected:
            motion["position_text"] = f"ROS offline | Host {network['ip']}"
            motion["map_status"] = "ROS bridge unavailable"
        elif time.time() - self._odom_last_at > 2.5:
            motion["position_text"] = f"ROS connected | Host {network['ip']}"
            motion["map_status"] = "Waiting for /odom"
        else:
            motion["position_text"] = (
                f"x={motion['x']:.2f}, y={motion['y']:.2f}, z={motion['z']:.2f}"
            )
            motion["map_status"] = f"Speed {motion['speed_mps']:.2f} m/s | Host {network['ip']}"

        motion["speed_mps"] = round(float(motion.get("speed_mps", 0.0)), 2)
        motion["speed_series"] = [round(v, 2) for v in self._speed_history]
        return motion

    def _ensure_jtop(self) -> bool:
        if JTopClient is None:
            self._jtop_connected = False
            return False
        try:
            if self._jtop is None:
                self._jtop = JTopClient()
                start = getattr(self._jtop, "start", None)
                if callable(start):
                    start()
            ok = getattr(self._jtop, "ok", None)
            self._jtop_connected = bool(ok()) if callable(ok) else True
            return self._jtop_connected
        except Exception as exc:
            self._remember_error("jtop", str(exc))
            self._jtop = None
            self._jtop_connected = False
            return False

    def _start_ros(self) -> bool:
        if roslibpy is None:
            return False
        if self._ros is not None:
            self._ros_connected = bool(getattr(self._ros, "is_connected", False))
            return self._ros_connected

        try:
            self._ros = roslibpy.Ros(host="localhost", port=9090)
            self._ros_thread = threading.Thread(target=self._run_ros, daemon=True)
            self._ros_thread.start()
            return True
        except Exception as exc:
            self._remember_error("ros", str(exc))
            self._ros = None
            self._ros_connected = False
            return False

    def _run_ros(self) -> None:
        if self._ros is None:
            return
        try:
            self._ros.run()
        except Exception as exc:
            self._remember_error("ros", str(exc))
            self._ros_connected = False

    def _ensure_ros_subscription(self) -> bool:
        if not self._start_ros():
            return False
        self._ros_connected = bool(getattr(self._ros, "is_connected", False))
        if not self._ros_connected or self._odom_subscribed:
            return self._ros_connected

        try:
            self._odom_topic = roslibpy.Topic(self._ros, "/odom", "nav_msgs/Odometry")
            self._odom_topic.subscribe(self._on_odom_msg)
            self._odom_subscribed = True
            return True
        except Exception as exc:
            self._remember_error("ros", str(exc))
            self._odom_topic = None
            self._odom_subscribed = False
            return False

    def _on_odom_msg(self, msg: dict[str, Any]) -> None:
        try:
            twist = msg.get("twist", {}).get("twist", {})
            linear = twist.get("linear", {})
            vx = float(linear.get("x", 0.0) or 0.0)
            vy = float(linear.get("y", 0.0) or 0.0)
            vz = float(linear.get("z", 0.0) or 0.0)
            speed_mps = math.sqrt(vx * vx + vy * vy + vz * vz)

            pose = msg.get("pose", {}).get("pose", {})
            position = pose.get("position", {})
            x = float(position.get("x", 0.0) or 0.0)
            y = float(position.get("y", 0.0) or 0.0)
            z = float(position.get("z", 0.0) or 0.0)

            self._latest_motion.update(
                {
                    "speed_mps": speed_mps,
                    "x": x,
                    "y": y,
                    "z": z,
                    "position_text": f"x={x:.2f}, y={y:.2f}, z={z:.2f}",
                    "map_status": f"/odom active | speed {speed_mps:.2f} m/s",
                }
            )
            self._odom_last_at = time.time()
            self._ros_connected = True
        except Exception as exc:
            self._remember_error("odom", str(exc))

    def _telemetry_status(self) -> str:
        if roslibpy is None:
            return "unavailable"
        if not self._ros_connected:
            return "offline"
        if time.time() - self._odom_last_at <= 2.5:
            return "online"
        return "connected"

    def _get_jtop_attr(self, name: str, default: Any) -> Any:
        if not self._ensure_jtop():
            return default
        try:
            return getattr(self._jtop, name, default)
        except Exception as exc:
            self._remember_error("jtop", str(exc))
            return default

    def _read_temperature(self, name: str) -> float:
        temp_data = self._get_jtop_attr("temperature", {})
        if isinstance(temp_data, dict):
            entry = temp_data.get(name, {})
            if isinstance(entry, dict):
                return float(entry.get("temp", 0.0) or 0.0)
        return 0.0

    @staticmethod
    def _pick_first_mapping(value: Any) -> Any:
        if isinstance(value, dict):
            for item in value.values():
                if isinstance(item, dict):
                    return item
        return None

    def _remember_error(self, source: str, message: str) -> None:
        self._last_error = {
            "source": source,
            "message": message,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
