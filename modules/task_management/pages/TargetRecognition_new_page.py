from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QCloseEvent, QImage, QPixmap
from PyQt5.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QPushButton, QTableWidgetItem

from modules.task_management.services.detection_service import DetectionService
from modules.task_management.services.thermal_service import ThermalService
from modules.task_management.ui.generated.TargetRecognition_new import Ui_MainWindow


class TargetRecognitionNewPage(QMainWindow, Ui_MainWindow):
    """Target recognition page (UI + service/adaptor architecture)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self._thermal_service = ThermalService()
        self._detection_service = DetectionService()
        self._apply_fluent_style()
        self._bind_actions()
        self._init_runtime_state()

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
            """
        )

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
