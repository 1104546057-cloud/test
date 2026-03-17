import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QCloseEvent, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QVBoxLayout,
)
from qfluentwidgets import PushButton

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from MICCProject1.scripts.BLL_InspectArea import BLL_InspectArea
from MICCProject1.scripts.BLL_InspectPoint_V4 import BLL_InspectPoint
from MICCProject1.scripts.BLL_InspectRoute_V1 import BLL_InspectRoute
from MICCProject1.scripts.DBHelper import DBHelper
from MICCProject1.scripts.patrol_runtime import PatrolService, PatrolState, create_executor
from MICCProject1.ui.Frm_InspectMag import Ui_Frm_InspectMag


class PatrolExecutionWindow(QDialog):
    RVIZ_CONFIG_PATH = os.getenv(
        "UAV_RVIZ_CONFIG",
        str(Path(__file__).resolve().parent.parent / "rviz" / "patrol_map.rviz"),
    )
    RVIZ_BIN = os.getenv("UAV_RVIZ_BIN", "rviz")

    def __init__(self, owner: "BLL_InspectMag"):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("Patrol Execution Window")
        self.resize(980, 660)
        self._rviz_process = None
        self._rviz_started_by_self = False
        self._build_ui()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._on_refresh_tick)
        self._on_rate_changed(self.cmbRefreshRate.currentIndex())

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.lblTitle = QLabel("Patrol Summary", self)
        self.lblTitle.setAlignment(Qt.AlignCenter)
        root.addWidget(self.lblTitle)

        self.grpMeta = QFrame(self)
        meta_layout = QGridLayout(self.grpMeta)
        meta_layout.setContentsMargins(8, 8, 8, 8)
        meta_layout.addWidget(QLabel("Area"), 0, 0)
        self.lblArea = QLabel("-", self.grpMeta)
        meta_layout.addWidget(self.lblArea, 0, 1)
        meta_layout.addWidget(QLabel("Route"), 1, 0)
        self.lblRoute = QLabel("-", self.grpMeta)
        meta_layout.addWidget(self.lblRoute, 1, 1)
        root.addWidget(self.grpMeta)

        self.lblCurrent = QLabel("Running: -", self)
        root.addWidget(self.lblCurrent)

        self.frmMap = QFrame(self)
        map_layout = QVBoxLayout(self.frmMap)
        map_layout.setContentsMargins(8, 8, 8, 8)
        self.lblMap = QLabel("?????? RViz ?????", self.frmMap)
        self.lblMap.setMinimumHeight(220)
        self.lblMap.setAlignment(Qt.AlignCenter)
        map_layout.addWidget(self.lblMap)
        root.addWidget(self.frmMap)

        ctrl = QHBoxLayout()
        self.btnStart = PushButton("Start", self)
        self.btnPause = PushButton("Pause", self)
        self.btnResume = PushButton("Resume", self)
        self.btnStop = PushButton("Stop", self)
        self.btnEmergency = PushButton("Emergency", self)
        self.cmbRefreshRate = QComboBox(self)
        self.cmbRefreshRate.addItem("1s", userData=1000)
        self.cmbRefreshRate.addItem("2s", userData=2000)
        self.cmbRefreshRate.addItem("5s", userData=5000)
        self.cmbRefreshRate.addItem("10s", userData=10000)
        self.cmbRefreshRate.setCurrentIndex(2)

        for b in (self.btnStart, self.btnPause, self.btnResume, self.btnStop, self.btnEmergency):
            b.setMinimumHeight(34)
            ctrl.addWidget(b)
        ctrl.addWidget(QLabel("Refresh", self))
        ctrl.addWidget(self.cmbRefreshRate)
        root.addLayout(ctrl)

        self.lblState = QLabel("State: IDLE", self)
        root.addWidget(self.lblState)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.txtLog = QPlainTextEdit(self)
        self.txtLog.setReadOnly(True)
        self.txtLog.setMinimumHeight(140)
        root.addWidget(self.txtLog)

        self.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.9); border:1px solid rgba(34,64,112,18); border-radius:8px; }"
            "QLabel { font: 12px 'Microsoft YaHei'; color:#273849; }"
        )

        self.btnStart.clicked.connect(self.owner._start_patrol)
        self.btnPause.clicked.connect(self.owner._pause_patrol)
        self.btnResume.clicked.connect(self.owner._resume_patrol)
        self.btnStop.clicked.connect(self.owner._stop_patrol)
        self.btnEmergency.clicked.connect(self.owner._emergency_stop)
        self.cmbRefreshRate.currentIndexChanged.connect(self._on_rate_changed)

        self._launch_external_rviz()

    def _emit_log(self, message: str) -> None:
        if hasattr(self, "txtLog"):
            self.txtLog.appendPlainText(message)
        if self.owner is not None:
            try:
                self.owner._append_runtime_log(message)
            except Exception:
                pass

    def _launch_external_rviz(self) -> None:
        if self._rviz_process is not None and self._rviz_process.poll() is None:
            return

        config_path = Path(self.RVIZ_CONFIG_PATH).expanduser()
        cmd = [self.RVIZ_BIN]
        if config_path.exists():
            cmd.extend(["-d", str(config_path)])

        try:
            self._rviz_process = subprocess.Popen(cmd)
            self._rviz_started_by_self = True
            if config_path.exists():
                self._emit_log(f"RViz ????????: {config_path}")
            else:
                self._emit_log(f"??? RViz ?????????: {config_path}")
            self.lblMap.setText("?????? RViz ?????")
        except Exception as exc:
            self._rviz_process = None
            self._rviz_started_by_self = False
            self.lblMap.setText("?? RViz ???????? ROS ??")
            self._emit_log(f"?? RViz ??: {exc}")

    def _on_rate_changed(self, _idx: int) -> None:
        interval = int(self.cmbRefreshRate.currentData() or 5000)
        self._refresh_timer.setInterval(interval)
        if self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _on_refresh_tick(self) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        self.lblCurrent.setToolTip(f"Last refresh: {now}")

    def start_refresh(self) -> None:
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()
            self._on_refresh_tick()

    def stop_refresh(self) -> None:
        self._refresh_timer.stop()

    def set_route_info(self, area_name: str, route_name: str) -> None:
        self.lblArea.setText(area_name or "-")
        self.lblRoute.setText(route_name or "-")

    def set_state(self, state: str) -> None:
        self.lblState.setText(f"State: {state}")

    def set_progress(self, current: int, total: int, point_name: str) -> None:
        pct = int((current / total) * 100) if total else 0
        self.progress.setValue(pct)
        self.lblCurrent.setText(f"Running: point {current}/{total} - {point_name}")

    def append_log(self, msg: str) -> None:
        self.txtLog.appendPlainText(msg)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.owner and self.owner._executor.state == PatrolState.RUNNING:
            ans = QMessageBox.question(
                self,
                "Prompt",
                "Patrol is still running. Close this window only?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                event.ignore()
                return

        if self._rviz_started_by_self and self._rviz_process is not None and self._rviz_process.poll() is None:
            close_rviz = QMessageBox.question(
                self,
                "Prompt",
                "???????? RViz ???",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if close_rviz == QMessageBox.Yes:
                try:
                    self._rviz_process.terminate()
                    self._rviz_process.wait(timeout=3)
                except Exception:
                    try:
                        self._rviz_process.kill()
                    except Exception:
                        pass

        super().closeEvent(event)


class BLL_InspectMag(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_Frm_InspectMag()
        self.ui.setupUi(self)
        self.db = DBHelper()

        self._inspect_area = None
        self._inspect_point = None
        self._inspect_route = None
        self._runtime_controls_ready = False
        self._exec_win = None

        self._apply_window_icon()
        self._replace_buttons()
        self._build_runtime_panel()
        self._bind_actions()
        self.load_inspectarea()

        self._patrol_service = PatrolService(self.db)
        self._executor = create_executor(self._executor_mode(), self)
        self._bind_executor_events()

    def _apply_window_icon(self) -> None:
        icon_path = Path(__file__).resolve().parents[2] / "assets" / "robot.png"
        if not icon_path.exists():
            return
        pix = QPixmap(str(icon_path))
        if pix.isNull():
            return
        icon = QIcon(pix.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.setWindowIcon(icon)

    def _replace_buttons(self) -> None:
        for name, text in (
            ("btn_InspectArea", "巡检区域"),
            ("btn_InspectPoint", "巡检点位"),
            ("btn_InspectRoute", "巡检路线"),
        ):
            old = getattr(self.ui, name)
            parent = old.parentWidget()
            layout = old.parentWidget().layout()
            idx = layout.indexOf(old)
            old.hide()
            btn = PushButton(text, parent)
            btn.setMinimumHeight(40)
            layout.insertWidget(idx, btn)
            setattr(self.ui, name, btn)

    def _build_runtime_panel(self) -> None:
        if self._runtime_controls_ready:
            return
        self._runtime_controls_ready = True

        panel = QFrame(self.ui.centralWidget)
        panel.setObjectName("runtimePanel")
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(10, 10, 10, 10)
        vbox.setSpacing(8)

        top = QHBoxLayout()

        self.cmbExecutorMode = QComboBox(panel)
        self.cmbExecutorMode.addItem("Windows模拟", userData="mock")
        self.cmbExecutorMode.addItem("ROS执行器(预留)", userData="ros")
        if self._executor_mode() == "ros":
            self.cmbExecutorMode.setCurrentIndex(1)
        top.addWidget(self.cmbExecutorMode)

        self.btn_StartPatrol = PushButton("开始巡逻", panel)
        self.btn_PausePatrol = PushButton("暂停", panel)
        self.btn_ResumePatrol = PushButton("恢复", panel)
        self.btn_StopPatrol = PushButton("停止", panel)
        self.btn_Emergency = PushButton("紧急制动", panel)
        self.btnOpenExecWindow = PushButton("打开执行窗体", panel)
        for b in (
            self.btn_StartPatrol,
            self.btn_PausePatrol,
            self.btn_ResumePatrol,
            self.btn_StopPatrol,
            self.btn_Emergency,
            self.btnOpenExecWindow,
        ):
            b.setMinimumHeight(36)
            top.addWidget(b)
        vbox.addLayout(top)

        self.lbl_Runtime = QLabel("状态：IDLE", panel)
        self.lbl_Runtime.setObjectName("lblRuntime")
        vbox.addWidget(self.lbl_Runtime)

        self.progressPatrol = QProgressBar(panel)
        self.progressPatrol.setRange(0, 100)
        self.progressPatrol.setValue(0)
        vbox.addWidget(self.progressPatrol)

        self.txt_RuntimeLog = QPlainTextEdit(panel)
        self.txt_RuntimeLog.setReadOnly(True)
        self.txt_RuntimeLog.setPlaceholderText("巡逻执行日志...")
        self.txt_RuntimeLog.setMinimumHeight(120)
        vbox.addWidget(self.txt_RuntimeLog)

        self.ui.verticalLayout.addWidget(panel)

        panel.setStyleSheet(
            "QFrame#runtimePanel {"
            "background: rgba(255,255,255,0.85);"
            "border: 1px solid rgba(34,64,112,18);"
            "border-radius: 10px;"
            "}"
            "QLabel#lblRuntime {"
            "font: 600 12px 'Microsoft YaHei';"
            "color: #2f3a4a;"
            "}"
        )

    def _bind_actions(self) -> None:
        self.ui.btn_InspectArea.clicked.connect(self.on_btn_InspectArea_click)
        self.ui.btn_InspectPoint.clicked.connect(self.on_btn_InspectPoint_click)
        self.ui.btn_InspectRoute.clicked.connect(self.on_btn_InspectRoute_click)
        self.ui.txt_InspectArea.currentIndexChanged.connect(self._on_area_changed)
        self.ui.txt_InspectRoute.currentIndexChanged.connect(self._on_route_changed)

        self.btn_StartPatrol.clicked.connect(self._start_patrol)
        self.btn_PausePatrol.clicked.connect(self._pause_patrol)
        self.btn_ResumePatrol.clicked.connect(self._resume_patrol)
        self.btn_StopPatrol.clicked.connect(self._stop_patrol)
        self.btn_Emergency.clicked.connect(self._emergency_stop)
        self.btnOpenExecWindow.clicked.connect(self._show_execution_window)
        self.cmbExecutorMode.currentIndexChanged.connect(self._on_executor_mode_changed)

    def _bind_executor_events(self) -> None:
        self._executor.state_changed.connect(self._on_executor_state_changed)
        self._executor.progress_changed.connect(self._on_executor_progress)
        self._executor.log_emitted.connect(self._append_runtime_log)
        self._executor.finished.connect(self._on_executor_finished)

    def _executor_mode(self) -> str:
        return os.getenv("UAV_PATROL_EXECUTOR", "mock")

    def _on_executor_mode_changed(self, _idx: int) -> None:
        mode = self.cmbExecutorMode.currentData() or "mock"
        if getattr(self._executor, "state", PatrolState.IDLE) == PatrolState.RUNNING:
            QMessageBox.warning(self, "提示", "请先停止巡逻，再切换执行器。")
            return
        self._executor = create_executor(mode, self)
        self._bind_executor_events()
        self._append_runtime_log(f"已切换执行器模式: {mode}")

    def _show_execution_window(self) -> None:
        if self._exec_win is None:
            self._exec_win = PatrolExecutionWindow(self)
        area = self.ui.txt_InspectArea.currentText()
        route = self.ui.txt_InspectRoute.currentText()
        self._exec_win.set_route_info(area, route)
        self._exec_win.set_state(self._executor.state.value)
        self._exec_win.show()
        self._exec_win.raise_()
        self._exec_win.activateWindow()

    def on_btn_InspectArea_click(self):
        if self._inspect_area is None or not self._inspect_area.isVisible():
            self._inspect_area = BLL_InspectArea()
        self._inspect_area.show()
        self._inspect_area.raise_()
        self._inspect_area.activateWindow()

    def on_btn_InspectPoint_click(self):
        if self._inspect_point is None or not self._inspect_point.isVisible():
            self._inspect_point = BLL_InspectPoint()
        self._inspect_point.show()
        self._inspect_point.raise_()
        self._inspect_point.activateWindow()

    def on_btn_InspectRoute_click(self):
        if self._inspect_route is None or not self._inspect_route.isVisible():
            self._inspect_route = BLL_InspectRoute()
        self._inspect_route.show()
        self._inspect_route.raise_()
        self._inspect_route.activateWindow()

    def load_inspectarea(self):
        self.ui.txt_InspectArea.clear()
        records = self.db.fetch_all("SELECT AreaId, AreaName FROM InspectArea ORDER BY AreaId")
        if not records:
            self.ui.txt_InspectArea.addItem("暂无巡检区域", userData=None)
            self.ui.txt_InspectRoute.clear()
            self.ui.txt_InspectRoute.addItem("暂无巡检路线", userData=None)
            self.ui.statusLabel.setText("当前没有可用巡检数据")
            return

        for row in records:
            self.ui.txt_InspectArea.addItem(row["AreaName"], userData=row["AreaId"])

        self._on_area_changed(0)

    def _on_area_changed(self, _idx: int):
        area_id = self.ui.txt_InspectArea.currentData()
        self.ui.txt_InspectRoute.clear()
        if area_id is None:
            self.ui.txt_InspectRoute.addItem("暂无巡检路线", userData=None)
            self.ui.statusLabel.setText("请选择要进入的模块")
            return

        routes = self.db.fetch_all(
            "SELECT RouteId, RouteName FROM InspectRoute WHERE AreaId=%s ORDER BY RouteId",
            (area_id,),
        )
        if not routes:
            self.ui.txt_InspectRoute.addItem("暂无巡检路线", userData=None)
            self.ui.statusLabel.setText("当前区域无可执行路线")
            return

        for row in routes:
            self.ui.txt_InspectRoute.addItem(row["RouteName"], userData=row["RouteId"])

        self._on_route_changed(self.ui.txt_InspectRoute.currentIndex())

    def _on_route_changed(self, _idx: int) -> None:
        route_id = self.ui.txt_InspectRoute.currentData()
        if route_id is None:
            self.ui.statusLabel.setText("请选择要进入的模块")
            return
        self.ui.statusLabel.setText(f"当前路线ID: {route_id}（可执行巡逻任务）")
        if self._exec_win is not None:
            self._exec_win.set_route_info(self.ui.txt_InspectArea.currentText(), self.ui.txt_InspectRoute.currentText())

    def _start_patrol(self) -> None:
        route_id = self.ui.txt_InspectRoute.currentData()
        if route_id is None:
            QMessageBox.warning(self, "提示", "请先选择一条路线。")
            return

        plan, err = self._patrol_service.load_plan(int(route_id))
        if err:
            QMessageBox.warning(self, "提示", err)
            return

        self.progressPatrol.setValue(0)
        self._executor.load_plan(plan)
        if not self._executor.start():
            QMessageBox.warning(self, "提示", "巡逻启动失败。")
            return

        self._show_execution_window()
        if self._exec_win is not None:
            self._exec_win.start_refresh()

    def _pause_patrol(self) -> None:
        self._executor.pause()

    def _resume_patrol(self) -> None:
        self._executor.resume()

    def _stop_patrol(self) -> None:
        self._executor.stop()
        if self._exec_win is not None:
            self._exec_win.stop_refresh()

    def _emergency_stop(self) -> None:
        self._executor.emergency_stop()
        if self._exec_win is not None:
            self._exec_win.stop_refresh()

    def _on_executor_state_changed(self, state: str) -> None:
        self.lbl_Runtime.setText(f"状态：{state}")
        if self._exec_win is not None:
            self._exec_win.set_state(state)

    def _on_executor_progress(self, current: int, total: int, point_name: str) -> None:
        pct = int((current / total) * 100) if total else 0
        self.progressPatrol.setValue(pct)
        self.ui.statusLabel.setText(f"执行中：点位 {current}/{total} - {point_name}")
        if self._exec_win is not None:
            self._exec_win.set_progress(current, total, point_name)

    def _append_runtime_log(self, message: str) -> None:
        self.txt_RuntimeLog.appendPlainText(message)
        if self._exec_win is not None:
            self._exec_win.append_log(message)

    def _on_executor_finished(self, success: bool, reason: str) -> None:
        if success:
            self.ui.statusLabel.setText("巡逻已完成")
            self.progressPatrol.setValue(100)
        else:
            self.ui.statusLabel.setText(f"巡逻结束：{reason}")
        if self._exec_win is not None:
            self._exec_win.stop_refresh()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = BLL_InspectMag()
    win.show()
    sys.exit(app.exec_())
