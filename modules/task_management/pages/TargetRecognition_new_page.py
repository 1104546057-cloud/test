from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QCloseEvent, QImage, QPixmap
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.navigation import init_navigation, restore_previous_window
from modules.task_management.services.detection_service import DetectionService
from modules.task_management.services.thermal_service import ThermalService
from modules.task_management.ui.generated.TargetRecognition_new import Ui_MainWindow


class TargetRecognitionNewPage(QMainWindow, Ui_MainWindow):
    """Target recognition page (UI + service/adaptor architecture)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        init_navigation(self, parent)
        self._force_active_btn_name = "btnDetect"
        self._thermal_service = ThermalService()
        self._detection_service = DetectionService()
        self._setup_sidebar()
        self._apply_fluent_style()
        self._bind_actions()
        self._init_runtime_state()

    def _setup_sidebar(self) -> None:
        body_layout = getattr(self, "horizontalLayout_body", None)
        if body_layout is None or hasattr(self, "_sidebar_btns"):
            return

        self.sidebarFrame = QFrame(self.centralwidget)
        self.sidebarFrame.setObjectName("sidebarFrame")
        self.sidebarFrame.setMinimumWidth(96)
        self.sidebarFrame.setMaximumWidth(110)
        self.sidebarFrame.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        layout = QVBoxLayout(self.sidebarFrame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        button_defs = [
            ("btnMapBuild", "地图构建", "map"),
            ("btnPointPatrol", "定点巡逻", "patrol"),
            ("btnDetect", "目标识别", "detect"),
            ("btnTrack", "目标跟踪", "track"),
            ("btnExplore", "自主探索", "explore"),
            ("btnAvoid", "智能避障", "avoid"),
            ("btnAirGround", "空地协同", None),
            ("btnHumanMachine", "人机协同", None),
        ]

        self._sidebar_btns = []
        self._sidebar_routes = {}
        for obj_name, text, route in button_defs:
            btn = QPushButton(text, self.sidebarFrame)
            btn.setObjectName(obj_name)
            btn.setMinimumHeight(48)
            btn.setMaximumHeight(48)
            layout.addWidget(btn)
            self._sidebar_btns.append(btn)
            if route:
                self._sidebar_routes[obj_name] = route
            setattr(self, obj_name, btn)

        layout.addStretch(1)
        body_layout.insertWidget(0, self.sidebarFrame)

        if hasattr(self, "tabWidget_left"):
            self.tabWidget_left.setMinimumWidth(820)

    def _apply_fluent_style(self) -> None:
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._set_btn_role(self.pushButton_connect, "primary")
        self._set_btn_role(self.pushButton_start, "primary")
        self._set_btn_role(self.pushButton_disconnect, "subtle")
        self._set_btn_role(self.pushButton_stop, "subtle")
        self._set_btn_role(self.pushButton_snapshot, "subtle")
        self._set_btn_role(self.pushButton_record, "danger")

        self.setStyleSheet(
            """
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #f6faff, stop:1 #ecf3ff);
            }
            QFrame#frame_header {
                background: rgba(255, 255, 255, 220);
                border: 1px solid rgba(34, 64, 112, 18);
                border-radius: 12px;
            }
            QLabel#label_title {
                color: #243447;
                font: 700 20px "Microsoft YaHei";
            }
            QLabel#label_project, QLabel#label_time {
                color: #4a596d;
                font: 12px "Microsoft YaHei";
            }
            QTabWidget::pane {
                border: 1px solid rgba(34, 64, 112, 16);
                border-radius: 10px;
                background: rgba(255, 255, 255, 220);
            }
            QTabBar::tab {
                background: rgba(255, 255, 255, 180);
                border: 1px solid rgba(34, 64, 112, 18);
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 8px 16px;
                color: #44566c;
                min-width: 90px;
            }
            QTabBar::tab:selected {
                background: #dfeeff;
                color: #1f4f8f;
            }
            QGroupBox {
                background: rgba(255, 255, 255, 205);
                border: 1px solid rgba(34, 64, 112, 14);
                border-radius: 10px;
                margin-top: 10px;
                font: 600 12px "Microsoft YaHei";
                color: #2a3c52;
            }
            QGroupBox::title {
                left: 10px;
                padding: 0 6px;
            }
            QLineEdit, QComboBox, QPlainTextEdit, QTableWidget {
                background: rgba(255, 255, 255, 235);
                border: 1px solid #c8d8ee;
                border-radius: 8px;
                padding: 6px;
                color: #2b3b4f;
                font: 12px "Microsoft YaHei";
            }
            QHeaderView::section {
                background: #edf4ff;
                border: 1px solid #d2e2f5;
                padding: 6px;
            }
            QProgressBar {
                border: 1px solid #c8d8ee;
                border-radius: 6px;
                background: rgba(255,255,255,210);
                text-align: center;
                color: #33485e;
            }
            QProgressBar::chunk {
                background: #4a9cf0;
                border-radius: 5px;
            }
            QPushButton {
                border-radius: 8px;
                border: 1px solid #9ecaf0;
                background: rgba(255, 255, 255, 220);
                color: #274059;
                padding: 8px 12px;
                font: 12px "Microsoft YaHei";
            }
            QPushButton:hover {
                background: #e9f5ff;
            }
            QPushButton[role="primary"] {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #5cb8ff, stop:1 #2d8de0);
                color: white;
                border: 1px solid #2d8de0;
            }
            QPushButton[role="primary"]:hover {
                background: #1f86df;
            }
            QPushButton[role="danger"] {
                background: #ffeef0;
                border: 1px solid #ff9ca7;
                color: #d94b57;
            }
            QPushButton[role="danger"]:hover {
                background: #ffe2e6;
            }
            QStatusBar {
                background: rgba(255,255,255,215);
                color: #44566c;
                border-top: 1px solid rgba(34,64,112,16);
            }
            QFrame#sidebarFrame {
                background: rgba(255, 255, 255, 150);
                border: none;
                border-radius: 16px;
            }
            """
        )

        side_qss = (
            "QPushButton {"
            "border-radius: 10px;"
            "border: 1px solid rgba(0, 0, 0, 10);"
            "background-color: rgba(255, 255, 255, 200);"
            "padding: 6px 10px;"
            "color: #3b4552;"
            "font-size: 12px;"
            "}"
            "QPushButton:hover {"
            "border: 1px solid rgba(45, 141, 224, 140);"
            "background-color: rgba(45, 141, 224, 26);"
            "}"
            "QPushButton:pressed {"
            "background-color: rgba(45, 141, 224, 40);"
            "padding-top: 7px;"
            "}"
        )
        self._side_default_qss = side_qss
        self._side_active_qss = (
            "QPushButton {"
            "border-radius: 10px;"
            "border: 1px solid rgba(45, 141, 224, 160);"
            "background-color: rgba(45, 141, 224, 26);"
            "color: #2f3a46;"
            "font-size: 12px;"
            "font-weight: 600;"
            "}"
        )
        for btn in getattr(self, "_sidebar_btns", []):
            btn.setStyleSheet(side_qss)
        self._set_active_sidebar(self._force_active_btn_name)

    def _set_btn_role(self, button: QPushButton, role: str) -> None:
        button.setProperty("role", role)

    def _bind_actions(self) -> None:
        self.pushButton_connect.clicked.connect(self._connect_device)
        self.pushButton_disconnect.clicked.connect(self._disconnect_device)
        self.pushButton_start.clicked.connect(self._start_detect)
        self.pushButton_stop.clicked.connect(self._stop_detect)
        self.pushButton_snapshot.clicked.connect(self._snapshot)
        self.pushButton_record.clicked.connect(self._toggle_record)

        self.horizontalSlider_confidence.valueChanged.connect(
            lambda v: self.label_confidence_value.setText(f"{v}%")
        )
        self.horizontalSlider_iou.valueChanged.connect(
            lambda v: self.label_iou_value.setText(f"{v}%")
        )

        self.action_exit.triggered.connect(self.close)
        self.action_fullscreen.triggered.connect(self._toggle_fullscreen)
        self.action_about.triggered.connect(self._show_about)
        self.action_open_video.triggered.connect(self._choose_video_file)
        self.action_open_model.triggered.connect(self._choose_weight_file)
        self.action_export_result.triggered.connect(self._export_result)

        for btn in getattr(self, "_sidebar_btns", []):
            route = self._sidebar_routes.get(btn.objectName())
            if route:
                btn.clicked.connect(lambda _, k=route: self._switch_sidebar_page(k))
            else:
                btn.clicked.connect(lambda _, b=btn: self._set_active_sidebar(b.objectName()))

    def _set_active_sidebar(self, name: str) -> None:
        target = self._force_active_btn_name or name
        for btn in getattr(self, "_sidebar_btns", []):
            btn.setStyleSheet(self._side_active_qss if btn.objectName() == target else self._side_default_qss)

    def _switch_sidebar_page(self, key: str) -> None:
        route_to_btn = {
            "map": "btnMapBuild",
            "patrol": "btnPointPatrol",
            "detect": "btnDetect",
            "track": "btnTrack",
            "explore": "btnExplore",
            "avoid": "btnAvoid",
        }
        self._set_active_sidebar(route_to_btn.get(key, self._force_active_btn_name))

        parent = self.parent()
        if parent and hasattr(parent, "open_sidebar_page"):
            parent.open_sidebar_page(key, source=self)

    def _init_runtime_state(self) -> None:
        self._recording = False
        self._connected = False
        self._detecting = False

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._refresh_time)
        self._clock.start(1000)
        self._refresh_time()

        self._runtime_tick = QTimer(self)
        self._runtime_tick.timeout.connect(self._run_pipeline_tick)

        self.label_confidence_value.setText(f"{self.horizontalSlider_confidence.value()}%")
        self.label_iou_value.setText(f"{self.horizontalSlider_iou.value()}%")
        self.tableWidget_results.setRowCount(0)
        self._ensure_source_options()

    def _ensure_source_options(self) -> None:
        options = [self.comboBox_source.itemText(i) for i in range(self.comboBox_source.count())]
        if "热成像摄像头" not in options:
            self.comboBox_source.addItem("热成像摄像头")

    def _refresh_time(self) -> None:
        self.label_time.setText(f"时间：{datetime.now().strftime('%H:%M:%S')}")

    def _log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.plainTextEdit_log.appendPlainText(f"[{ts}] {msg}")

    def _connect_device(self) -> None:
        source = self.comboBox_source.currentText()
        addr = self.lineEdit_device.text().strip() or "默认设备"
        try:
            self._thermal_service.connect(source, addr)
        except Exception as exc:
            self._connected = False
            QMessageBox.warning(self, "提示", f"连接失败: {exc}")
            self._log(f"连接失败: {exc}")
            return

        self._connected = True
        self.statusbar.showMessage("设备已连接", 2500)
        self._log(f"已连接：{source} / {addr}")

    def _disconnect_device(self) -> None:
        self._connected = False
        self._detecting = False
        self._runtime_tick.stop()
        self._thermal_service.disconnect()
        self.statusbar.showMessage("设备已断开", 2500)
        self._log("设备已断开")

    def _start_detect(self) -> None:
        if not self._connected:
            QMessageBox.warning(self, "提示", "请先连接设备")
            return
        self._detecting = True
        self._runtime_tick.start(120)
        self.statusbar.showMessage("检测中...", 2500)
        self._log("开始检测")

    def _stop_detect(self) -> None:
        self._detecting = False
        self._runtime_tick.stop()
        self.statusbar.showMessage("检测已停止", 2500)
        self._log("停止检测")

    def _snapshot(self) -> None:
        pixmap = self.label_video.pixmap()
        if pixmap is None or pixmap.isNull():
            QMessageBox.information(self, "提示", "当前没有可保存画面。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存截图", "", "PNG 图片 (*.png);;JPG 图片 (*.jpg)")
        if not path:
            return
        pixmap.save(path)
        self._log(f"截图已保存: {path}")
        self.statusbar.showMessage("截图已保存", 2500)

    def _toggle_record(self) -> None:
        self._recording = not self._recording
        self.pushButton_record.setText("停止录制" if self._recording else "录制结果")
        self._log("开始录制" if self._recording else "停止录制")

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _show_about(self) -> None:
        QMessageBox.information(self, "关于", "无人车目标识别模块（热成像框架版）")

    def _run_pipeline_tick(self) -> None:
        if not self._detecting:
            return

        packet = self._thermal_service.read_frame()
        if packet is None:
            return

        source = self.comboBox_source.currentText()

        if source == "热成像摄像头":
            # 热成像模式：不走检测，只显示热图和温度信息
            self._render_video(packet.frame_bgr)

            self.tableWidget_results.setRowCount(3)
            self.tableWidget_results.setColumnCount(2)
            self.tableWidget_results.setHorizontalHeaderLabels(["温度项", "数值"])

            temps = [
                ("最高温度", f"{packet.max_temp:.2f} °C" if packet.max_temp is not None else "--"),
                ("最低温度", f"{packet.min_temp:.2f} °C" if packet.min_temp is not None else "--"),
                ("中心温度", f"{packet.center_temp:.2f} °C" if packet.center_temp is not None else "--"),
            ]

            for r, (k, v) in enumerate(temps):
                self.tableWidget_results.setItem(r, 0, QTableWidgetItem(k))
                self.tableWidget_results.setItem(r, 1, QTableWidgetItem(v))

            self.label_objects_value.setText("0")
            self.label_fps_value.setText(f"{packet.source_fps:.1f}")
            self.label_latency_value.setText("0 ms")
            self.label_speed_value.setText("0.0 km/h")

            self.progressBar_steer.setValue(0)
            self.progressBar_brake.setValue(0)
            self.progressBar_battery.setValue(100)

            if packet.max_temp is not None and packet.min_temp is not None:
                self.label_project.setText(
                    f"模式：热成像检测  Tmax={packet.max_temp:.1f}°C Tmin={packet.min_temp:.1f}°C"
                )
            return

        conf = self.horizontalSlider_confidence.value() / 100.0
        batch = self._detection_service.infer(packet.frame_bgr, conf)

        self._render_video(batch.annotated_frame)
        self._fill_result_table(batch.results)

        self.label_objects_value.setText(str(len(batch.results)))
        self.label_fps_value.setText(f"{packet.source_fps:.1f}")
        self.label_latency_value.setText(f"{batch.latency_ms} ms")
        self.label_speed_value.setText(f"{(len(batch.results) * 0.8):.1f} km/h")

        self.progressBar_steer.setValue(batch.steer_percent)
        self.progressBar_brake.setValue(batch.brake_percent)
        self.progressBar_battery.setValue(batch.battery_percent)

        if packet.max_temp is not None and packet.min_temp is not None:
            self.label_project.setText(
                f"模式：热成像检测  Tmax={packet.max_temp:.1f}°C Tmin={packet.min_temp:.1f}°C"
            )

    def _render_video(self, frame_bgr: np.ndarray) -> None:
        rgb = frame_bgr[:, :, ::-1].copy()
        h, w, c = rgb.shape
        qimg = QImage(rgb.data, w, h, c * w, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        self.label_video.setPixmap(pix.scaled(self.label_video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _fill_result_table(self, results) -> None:
        self.tableWidget_results.setRowCount(len(results))
        for row, item in enumerate(results):
            self.tableWidget_results.setItem(row, 0, QTableWidgetItem(str(item.target_id)))
            self.tableWidget_results.setItem(row, 1, QTableWidgetItem(item.category))
            self.tableWidget_results.setItem(row, 2, QTableWidgetItem(f"{item.confidence:.2f}"))
            self.tableWidget_results.setItem(row, 3, QTableWidgetItem(item.position))
            self.tableWidget_results.setItem(row, 4, QTableWidgetItem(f"{item.distance_m:.1f}"))
            self.tableWidget_results.setItem(row, 5, QTableWidgetItem(f"{item.speed_kmh:.1f}"))

    def _choose_video_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "", "视频文件 (*.mp4 *.avi *.mov *.mkv);;全部文件 (*.*)"
        )
        if not path:
            return
        self.comboBox_source.setCurrentText("本地视频文件")
        self.lineEdit_device.setText(path)
        self._log(f"已选择视频: {Path(path).name}")

    def _choose_weight_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择模型权重", "", "模型文件 (*.onnx *.pt);;全部文件 (*.*)"
        )
        if path:
            self.lineEdit_weight.setText(path)
            self._log(f"已加载模型路径: {Path(path).name}")

    def _export_result(self) -> None:
        if self.tableWidget_results.rowCount() == 0:
            QMessageBox.information(self, "提示", "当前无可导出结果。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出结果", "detect_result.csv", "CSV 文件 (*.csv)")
        if not path:
            return
        lines = ["id,category,confidence,position,distance,speed"]
        for row in range(self.tableWidget_results.rowCount()):
            vals = [self.tableWidget_results.item(row, i).text() for i in range(6)]
            lines.append(",".join(vals))
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        self._log(f"结果已导出: {path}")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._clock.stop()
        self._runtime_tick.stop()
        self._thermal_service.disconnect()
        super().closeEvent(event)
        restore_previous_window(self)
