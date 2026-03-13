from PyQt5 import QtWidgets
from PyQt5.QtCore import QTimer, QRectF, QSize
from PyQt5.QtGui import QColor, QPainterPath, QRegion, QTransform, QIcon
from qfluentwidgets import FluentIcon as FIF, ThemeColor
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from PyQt5.QtCore import Qt, QEvent
import threading
import random
import sys
from pathlib import Path

# === ROS ===
import roslibpy
import base64

import numpy as np

from PyQt5.QtGui import QImage, QPixmap


sys.path.append(str(Path(__file__).resolve().parents[2]))
from UI.generated.content import Ui_Form


class ContentPage(QtWidgets.QWidget, Ui_Form):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self._drag_active = False
        self._drag_pos = None

        # ===== Video display init =====
        self.label.setScaledContents(True)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setText("Waiting for camera...")


        # ===== UI 美化（原样保留）=====
        self.apply_glass_frames()
        self.apply_dpad_style()
        self.apply_dpad_icons()
        self.setup_window_controls()
        self.apply_section_labels()
        self.apply_topbar_style()
        self.apply_estop_style()
        self.setup_gauge_labels()

        # ===== ROS 控制初始化 =====
        self.ros = None
        self.cmd_vel_pub = None
        self.image_topic = None
        self.odom_topic = None
        self.power_topic = None
        self._ros_ready = False
        self._ros_check_timer = None
        self._ros_thread = None
        QTimer.singleShot(0, self._start_ros)


        # 当前速度状态
        self.current_linear_x = 0.0
        self.current_angular_z = 0.0

        self._latest_speed_mps = 0.0
        self._latest_voltage = 0.0

        self._latest_qimg = None
        self._latest_qimg_size = None
        self._latest_image_msg = None

        # 10Hz 发布（等价 rostopic pub -r 10）
        self.cmd_timer = QTimer(self)
        self.cmd_timer.setInterval(100)
        self.cmd_timer.timeout.connect(self._publish_cmd_vel)

        # ===== 按钮绑定（前进 / 后退 / 斜向）=====
        if hasattr(self, "btnUp"):
            self.btnUp.pressed.connect(self.start_forward)
            self.btnUp.released.connect(self.stop_motion)

        if hasattr(self, "btnDown"):
            self.btnDown.pressed.connect(self.start_backward)
            self.btnDown.released.connect(self.stop_motion)

        if hasattr(self, "btnUpLeft"):
            self.btnUpLeft.pressed.connect(self.start_forward_left)
            self.btnUpLeft.released.connect(self.stop_motion)

        if hasattr(self, "btnUpRight"):
            self.btnUpRight.pressed.connect(self.start_forward_right)
            self.btnUpRight.released.connect(self.stop_motion)

        if hasattr(self, "btnDownLeft"):
            self.btnDownLeft.pressed.connect(self.start_backward_left)
            self.btnDownLeft.released.connect(self.stop_motion)

        if hasattr(self, "btnDownRight"):
            self.btnDownRight.pressed.connect(self.start_backward_right)
            self.btnDownRight.released.connect(self.stop_motion)

        if hasattr(self, "btnStop"):
            self.btnStop.pressed.connect(self.stop_motion)

        # ===== mock 数据（原样保留）=====
        self._t = QTimer(self)
        self._t.timeout.connect(self._mock_update)
        # self._t.start(800)  # disabled: use real ROS status

        # Video refresh timer: only draw latest frame at fixed rate
        self._video_timer = QTimer(self)
        self._video_timer.setInterval(100)   # ~15 FPS
        self._video_timer.timeout.connect(self._refresh_video_frame)
        self._video_timer.start()

    def _refresh_control_ui(self):
        try:
            target_v = float(self.current_linear_x)

            # 速度条：显示目标速度，立即响应
            speed_value = int(min(200, abs(target_v) * 200))
            if hasattr(self, "speedBarPlaceholder"):
                self.speedBarPlaceholder.setValue(speed_value)

            # 文本：同时显示目标速度 + 实际速度
            if hasattr(self, "labelDriveInfo"):
                self.labelDriveInfo.setText(
                    f"目标速度: {target_v:.2f} m/s | 实际速度: {self._latest_speed_mps:.2f} m/s"
                )
        except Exception as e:
            print("UI refresh error:", e)

    def _publish_cmd_vel(self):
        if not self._ros_ready or not self.cmd_vel_pub:
            return
        msg = {
            'linear': {'x': self.current_linear_x, 'y': 0.0, 'z': 0.0},
            'angular': {'x': 0.0, 'y': 0.0, 'z': self.current_angular_z}
        }
        self.cmd_vel_pub.publish(roslibpy.Message(msg))

    def start_forward(self):
        print("DEBUG: start_forward called")
        if not self._require_ros():
            print("DEBUG: _require_ros returned False")
            return
        self.current_linear_x = 0.20
        self.current_angular_z = 0.0
        if not self.cmd_timer.isActive():
            self.cmd_timer.start()
        self._refresh_control_ui()

    def start_backward(self):
        if not self._require_ros():
            return
        self.current_linear_x = -0.20
        self.current_angular_z = 0.0
        if not self.cmd_timer.isActive():
            self.cmd_timer.start()
        self._refresh_control_ui()

    # ===== 斜向（阿克曼=前进/后退 + 转向）=====
    def start_forward_left(self):
        if not self._require_ros():
            return
        self.current_linear_x = 0.20
        self.current_angular_z = 0.6
        if not self.cmd_timer.isActive():
            self.cmd_timer.start()
        self._refresh_control_ui()

    def start_forward_right(self):
        if not self._require_ros():
            return
        self.current_linear_x = 0.20
        self.current_angular_z = -0.6
        if not self.cmd_timer.isActive():
            self.cmd_timer.start()
        self._refresh_control_ui()

    def start_backward_left(self):
        if not self._require_ros():
            return
        self.current_linear_x = -0.20
        self.current_angular_z = 0.6
        if not self.cmd_timer.isActive():
            self.cmd_timer.start()
        self._refresh_control_ui()

    def start_backward_right(self):
        if not self._require_ros():
            return
        self.current_linear_x = -0.20
        self.current_angular_z = -0.6
        if not self.cmd_timer.isActive():
            self.cmd_timer.start()
        self._refresh_control_ui()

    def stop_motion(self):
        if self.cmd_timer.isActive():
            self.cmd_timer.stop()

        self.current_linear_x = 0.0
        self.current_angular_z = 0.0

        msg = {
            'linear': {'x': 0.0, 'y': 0.0, 'z': 0.0},
            'angular': {'x': 0.0, 'y': 0.0, 'z': 0.0}
        }
        if self._ros_ready and self.cmd_vel_pub:
            self.cmd_vel_pub.publish(roslibpy.Message(msg))
        self._refresh_control_ui()

    def _require_ros(self) -> bool:
        print(f"DEBUG: _require_ros check, _ros_ready={self._ros_ready}, cmd_vel_pub={self.cmd_vel_pub is not None}")
        if self._ros_ready:
            return True
        if hasattr(self, "label"):
            self.label.setText("ROS 未连接")
        return False

    def _start_ros(self):
        try:
            self.ros = roslibpy.Ros(host="localhost", port=9090)
        except Exception as exc:
            if hasattr(self, "label"):
                self.label.setText(f"ROS 初始化失败: {exc}")
            return

        self._ros_thread = threading.Thread(target=self._run_ros, daemon=True)
        self._ros_thread.start()

        self._ros_check_timer = QTimer(self)
        self._ros_check_timer.setInterval(500)
        self._ros_check_timer.timeout.connect(self._check_ros_ready)
        self._ros_check_timer.start()

    def _run_ros(self):
        try:
            self.ros.run()
        except Exception as exc:
            print("ROS run failed:", exc)

    def _check_ros_ready(self):
        if self.ros and getattr(self.ros, "is_connected", False):
            self._ros_check_timer.stop()
            self._on_ros_ready()

    def _on_ros_ready(self):
        self._ros_ready = True
        if hasattr(self, "label"):
            self.label.setText("ROS 已连接，等待图像...")

        self.cmd_vel_pub = roslibpy.Topic(self.ros, "/cmd_vel", "geometry_msgs/Twist")
        self.cmd_vel_pub.advertise()
        self.image_topic = roslibpy.Topic(
            self.ros,
            "/camera/rgb/image_raw",
            "sensor_msgs/Image"
        )
        self.image_topic.subscribe(self._on_image_msg)

        self.odom_topic = roslibpy.Topic(
            self.ros,
            "/odom",
            "nav_msgs/Odometry"
        )
        self.odom_topic.subscribe(self._on_odom_msg)

        self.power_topic = roslibpy.Topic(
            self.ros,
            "/PowerVoltage",
            "std_msgs/Float32"
        )
        self.power_topic.subscribe(self._on_power_msg)

    def closeEvent(self, event):
        try:
            if self.image_topic:
                self.image_topic.unsubscribe()
        except Exception:
            pass
        try:
            if self.odom_topic:
                self.odom_topic.unsubscribe()
        except Exception:
            pass
        try:
            if self.power_topic:
                self.power_topic.unsubscribe()
        except Exception:
            pass
        try:
            if self.cmd_vel_pub:
                self.cmd_vel_pub.unadvertise()
        except Exception:
            pass
        try:
            if self.ros:
                self.ros.terminate()
        except Exception:
            pass
        event.accept()



    # =========================================================
    # ===== 以下是原 UI 逻辑 =====
    # =========================================================

    def apply_glass_frames(self) -> None:
        for name in ["frameVideo", "frameMap", "frameDriveInfo", "frameEStop"]:
            frame = getattr(self, name, None)
            if not frame:
                continue
            frame.setStyleSheet(
                "QFrame {"
                "background: rgba(255, 255, 255, 180);"
                "border: 1px solid rgba(255, 255, 255, 140);"
                "border-radius: 18px;"
                "}"
            )
            shadow = QGraphicsDropShadowEffect(frame)
            shadow.setBlurRadius(30)
            shadow.setOffset(0, 10)
            shadow.setColor(QColor(0, 0, 0, 45))
            frame.setGraphicsEffect(shadow)

    def apply_dpad_style(self) -> None:
        qss = """
        QPushButton {
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 170);
            background-color: rgba(255, 255, 255, 120);
            padding: 0px;
        }
        QPushButton:hover {
            background-color: rgba(255, 255, 255, 160);
            border: 1px solid rgba(255, 255, 255, 220);
        }
        QPushButton:pressed {
            background-color: rgba(255, 255, 255, 190);
            padding-top: 2px;
        }
        """
        buttons = [
            self.btnUpLeft, self.btnUp, self.btnUpRight,
            self.btnStop,
            self.btnDownLeft, self.btnDown, self.btnDownRight,
        ]
        for btn in buttons:
            if not btn:
                continue
            btn.setStyleSheet(qss)
            shadow = QGraphicsDropShadowEffect(btn)
            shadow.setBlurRadius(25)
            shadow.setOffset(0, 8)
            shadow.setColor(QColor(0, 0, 0, 45))
            btn.setGraphicsEffect(shadow)

    def apply_dpad_icons(self) -> None:
        accent = ThemeColor.PRIMARY.color()
        icon_size = QSize(20, 20)

        def rotated(icon, angle):
            pix = icon.pixmap(icon_size)
            pix = pix.transformed(QTransform().rotate(angle), Qt.SmoothTransformation)
            return QIcon(pix)

        base_icon = FIF.UP.icon(accent)

        mapping = {
            "btnUp": base_icon,
            "btnDown": rotated(base_icon, 180),
            "btnLeft": rotated(base_icon, -90),
            "btnRight": rotated(base_icon, 90),
            "btnUpLeft": rotated(base_icon, -45),
            "btnUpRight": rotated(base_icon, 45),
            "btnDownLeft": rotated(base_icon, -135),
            "btnDownRight": rotated(base_icon, 135),
            "btnStop": FIF.CLOSE.icon(accent),
        }

        for name, icon in mapping.items():
            btn = getattr(self, name, None)
            if not btn:
                continue
            btn.setText("")
            btn.setIcon(icon)
            btn.setIconSize(icon_size)

    def apply_section_labels(self) -> None:
        label_qss = """
        QLabel {
            color: #5f6b7a;
            font-size: 12px;
            font-weight: 600;
            padding: 6px 10px;
        }
        """
        for name in ["label", "label_2", "labelDriveInfo", "labelEStop"]:
            lbl = getattr(self, name, None)
            if lbl:
                lbl.setStyleSheet(label_qss)

    def apply_estop_style(self) -> None:
        if hasattr(self, "frameEStop"):
            self.frameEStop.setStyleSheet(
                "QFrame {"
                "background: rgba(255, 235, 235, 220);"
                "border: 1px solid rgba(255, 140, 140, 140);"
                "border-radius: 16px;"
                "}"
            )

    def setup_window_controls(self) -> None:
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_StyledBackground, True)

        if hasattr(self, "btnBack"):
            self.btnBack.clicked.connect(self.close)

        if hasattr(self, "btnMin"):
            self.btnMin.clicked.connect(self.showMinimized)

        self._ensure_fullscreen_button()

        if hasattr(self, "btnClose"):
            self.btnClose.clicked.connect(self.close)

    def setup_gauge_labels(self) -> None:
        pass

    def _ensure_fullscreen_button(self) -> None:
        if hasattr(self, "btnMax"):
            self.btnMax.clicked.connect(self._toggle_maximize)
            return

        layout = getattr(self, "topBarLayout", None)
        if layout is None:
            return

        btn_close = getattr(self, "btnClose", None)
        btn_max = QtWidgets.QPushButton(self.frameTopBar)
        btn_max.setObjectName("btnMax")
        btn_max.setMinimumSize(QSize(36, 36))
        btn_max.setMaximumSize(QSize(36, 36))
        btn_max.setText("")

        if btn_close:
            idx = layout.indexOf(btn_close)
            if idx >= 0:
                layout.insertWidget(idx, btn_max)
            else:
                layout.addWidget(btn_max)
        else:
            layout.addWidget(btn_max)

        self.btnMax = btn_max
        btn_max.clicked.connect(self._toggle_maximize)

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _mock_update(self):
        speed = random.randint(0, 200)
        battery = random.randint(0, 100)

        if hasattr(self, "speedBarPlaceholder"):
            self.speedBarPlaceholder.setValue(speed)
        if hasattr(self, "batteryBarPlaceholder"):
            self.batteryBarPlaceholder.setValue(battery)

    # ===== 修复缺失的 apply_topbar_style =====
    def apply_topbar_style(self) -> None:
        accent = ThemeColor.PRIMARY.color()
        r, g, b, _ = accent.getRgb()
        qss = """
        QPushButton {
            border-radius: 8px;
            border: 1px solid rgba(%d, %d, %d, 90);
            background-color: rgba(255, 255, 255, 180);
            padding: 0px;
        }
        QPushButton:hover {
            border: 1px solid rgba(%d, %d, %d, 160);
            background-color: rgba(%d, %d, %d, 28);
        }
        QPushButton:pressed {
            background-color: rgba(%d, %d, %d, 45);
            padding-top: 1px;
        }
        """ % (r, g, b, r, g, b, r, g, b, r, g, b)

        for btn in [
            getattr(self, "btnBack", None),
            getattr(self, "btnMin", None),
            getattr(self, "btnMax", None),
            getattr(self, "btnClose", None),
        ]:
            if btn:
                btn.setStyleSheet(qss)
                btn.setText("")

        icon_size = QSize(16, 16)
        icon_map = {
            "btnBack": FIF.LEFT_ARROW,
            "btnMin": FIF.MINIMIZE,
            "btnMax": FIF.FULL_SCREEN,
            "btnClose": FIF.CLOSE,
        }
        for name, icon in icon_map.items():
            btn = getattr(self, name, None)
            if btn:
                btn.setIcon(icon.icon(accent))
                btn.setIconSize(icon_size)

    def _on_odom_msg(self, msg):
        try:
            vx = float(msg["twist"]["twist"]["linear"]["x"])
            self._latest_speed_mps = vx

            # 直接用 /odom 的实际速度驱动速度条
            speed_value = int(min(200, abs(vx) * 200))
            if hasattr(self, "speedBarPlaceholder"):
                self.speedBarPlaceholder.setValue(speed_value)

            if hasattr(self, "labelDriveInfo"):
                self.labelDriveInfo.setText(f"实际速度: {vx:.2f} m/s")

            if hasattr(self, "label_2"):
                self.label_2.setText(f"位置地图    实际速度 {vx:.2f} m/s")
        except Exception as e:
            print("Odom error:", e)

    def _on_power_msg(self, msg):
        try:
            voltage = float(msg["data"])
            self._latest_voltage = voltage

            # 24V system provisional mapping
            percent = int(max(0, min(100, (voltage - 21.0) / (29.4 - 21.0) * 100)))

            if hasattr(self, "batteryBarPlaceholder"):
                self.batteryBarPlaceholder.setValue(percent)

            if hasattr(self, "labelEStop"):
                self.labelEStop.setText(f"电量: {voltage:.2f} V / {percent}%")
        except Exception as e:
            print("Power error:", e)

    def _refresh_video_frame(self):
        try:
            msg = self._latest_image_msg
            if msg is None:
                return

            width = msg['width']
            height = msg['height']
            encoding = msg['encoding']

            if encoding != 'rgb8':
                return

            data = base64.b64decode(msg['data'])
            img = np.frombuffer(data, dtype=np.uint8)
            img = img.reshape((height, width, 3))

            qimg = QImage(
                img.data,
                width,
                height,
                3 * width,
                QImage.Format_RGB888
            ).copy()

            self._latest_qimg = qimg
            self._latest_qimg_size = (width, height)
            self.label.setPixmap(QPixmap.fromImage(qimg))
        except Exception as e:
            print("Video refresh error:", e)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_active = True
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_active and event.buttons() & Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_active = False
            self._drag_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _on_image_msg(self, msg):
        try:
            self._latest_image_msg = msg
        except Exception as e:
            print("Camera cache error:", e)
