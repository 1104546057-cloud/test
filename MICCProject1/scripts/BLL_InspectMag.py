import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QByteArray, QBuffer, QIODevice, Qt, QTimer
from PyQt5.QtGui import QCloseEvent, QIcon, QImage, QPixmap
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

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEngineView = None

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
    def __init__(self, owner: "BLL_InspectMag"):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("Patrol Execution Window")
        self.resize(980, 660)
        self.web_view = None
        self._map_placeholder = None
        self._map_ready = False
        self._map_meta = None
        self._pending_route_points = []
        self._current_plan = None
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
        self.frmMap.setMinimumHeight(280)
        root.addWidget(self.frmMap, 1)

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

        self._init_map_panel()

    def _emit_log(self, message: str) -> None:
        if hasattr(self, "txtLog"):
            self.txtLog.appendPlainText(message)
        if self.owner is not None:
            try:
                self.owner._append_runtime_log(message)
            except Exception:
                pass

    def _candidate_map_yamls(self):
        candidates = []
        env_yaml = (os.getenv("UAV_MAP_YAML", "") or "").strip()
        if env_yaml:
            candidates.append(Path(env_yaml).expanduser())
        candidates.extend(
            [
                Path("/home/wheeltec/sysu_ws/src/turn_on_wheeltec_robot/map/my_new_map_319.yaml"),
                Path("/home/wheeltec/sysu_ws/src/turn_on_wheeltec_robot/map/my_new_map_319.yaml"),
                Path("/home/wheeltec/wheeltec_robot/src/turn_on_wheeltec_robot/map/my_new_map_319.yaml"),
            ]
        )
        existing = [p for p in candidates if p.exists()]
        existing.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return existing

    def _parse_map_yaml(self, yaml_path: Path):
        content = yaml_path.read_text(encoding="utf-8", errors="ignore")
        image_value = None
        resolution = None
        origin = None
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("image:"):
                image_value = line.split(":", 1)[1].strip().strip("\"'")
            elif line.startswith("resolution:"):
                resolution = float(line.split(":", 1)[1].strip())
            elif line.startswith("origin:"):
                match = re.search(r"\[([^\]]+)\]", line)
                if match:
                    parts = [p.strip() for p in match.group(1).split(",")]
                    if len(parts) >= 2:
                        origin = (
                            float(parts[0]),
                            float(parts[1]),
                            float(parts[2]) if len(parts) >= 3 else 0.0,
                        )

        if not image_value or resolution is None or origin is None:
            raise ValueError(f"invalid map yaml: {yaml_path}")

        image_path = Path(image_value)
        if not image_path.is_absolute():
            image_path = (yaml_path.parent / image_path).resolve()
        if not image_path.exists():
            fallback = (yaml_path.parent / Path(image_value).name).resolve()
            if fallback.exists():
                image_path = fallback
        if not image_path.exists():
            raise FileNotFoundError(f"map image not found: {image_path}")

        qimg = QImage(str(image_path))
        if qimg.isNull():
            raise ValueError(f"failed to read map image: {image_path}")

        png_bytes = QByteArray()
        buffer = QBuffer(png_bytes)
        if not buffer.open(QIODevice.WriteOnly):
            raise ValueError("open memory buffer failed")
        if not qimg.save(buffer, "PNG"):
            buffer.close()
            raise ValueError("convert map image to PNG failed")
        buffer.close()

        return {
            "yaml_path": str(yaml_path),
            "map_name": yaml_path.name,
            "image_data_url": "data:image/png;base64," + bytes(png_bytes.toBase64()).decode("ascii"),
            "width": int(qimg.width()),
            "height": int(qimg.height()),
            "resolution": float(resolution),
            "origin_x": float(origin[0]),
            "origin_y": float(origin[1]),
        }

    def _try_pick_map_meta(self) -> bool:
        self._map_meta = None
        for yaml_path in self._candidate_map_yamls():
            try:
                self._map_meta = self._parse_map_yaml(yaml_path)
                return True
            except Exception:
                continue
        return False

    def _init_map_panel(self) -> None:
        layout = self.frmMap.layout()
        if layout is None:
            layout = QVBoxLayout(self.frmMap)
            layout.setContentsMargins(0, 0, 0, 0)
        else:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        if QWebEngineView is None:
            self._map_placeholder = QLabel("地图预览需要安装 PyQtWebEngine", self.frmMap)
            self._map_placeholder.setAlignment(Qt.AlignCenter)
            layout.addWidget(self._map_placeholder)
            self._map_ready = False
            self._emit_log("地图组件不可用：未安装 PyQtWebEngine")
            return

        self.web_view = QWebEngineView(self.frmMap)
        layout.addWidget(self.web_view)
        self.web_view.loadFinished.connect(self._on_map_load_finished)
        if self._try_pick_map_meta():
            self._emit_log(f"已加载执行地图: {self._map_meta.get('yaml_path', '')}")
        else:
            self._emit_log("未找到地图 YAML，将仅显示路线示意")
        self._load_route_map_html()

    def _load_route_map_html(self) -> None:
        if self.web_view is None:
            return

        meta = self._map_meta
        meta_json = json.dumps(meta, ensure_ascii=False) if meta else "null"
        legend = f"Patrol Preview | {(meta or {}).get('map_name', 'none')}"
        html = f"""
        <!DOCTYPE html><html><head><meta charset='UTF-8'>
        <style>
        html,body,#root{{margin:0;width:100%;height:100%;overflow:hidden;background:#0f1722}}
        #cv{{width:100%;height:100%;display:block;background:#0f1722;cursor:grab}}
        #bar{{position:absolute;top:8px;right:8px;display:flex;gap:6px;background:rgba(10,22,35,.72);padding:5px;border:1px solid rgba(127,174,214,.35);border-radius:8px}}
        #bar button{{height:24px;min-width:30px;border:1px solid #4a6f93;background:#16304a;color:#dcefff;border-radius:5px}}
        #legend{{position:absolute;left:8px;top:8px;padding:4px 8px;border-radius:4px;background:rgba(0,0,0,.5);color:#dce7f3;font:12px Microsoft YaHei}}
        </style></head><body><div id='root'><canvas id='cv'></canvas><div id='legend'>{legend}</div>
        <div id='bar'><button id='fit'>F</button><button id='zin'>+</button><button id='zout'>-</button></div></div>
        <script>
        const meta={meta_json},hasMap=!!meta,cv=document.getElementById('cv'),ctx=cv.getContext('2d');
        const st={{s:1,ox:0,oy:0,drag:false,sx:0,sy:0,aox:0,aoy:0}},pts=[]; let img=null;
        if(hasMap){{img=new Image();img.src=meta.image_data_url;img.onload=()=>draw();}}
        function fit(){{
          if(!hasMap){{draw();return;}}
          const fs=Math.min(cv.width/meta.width,cv.height/meta.height); st.s=fs; st.ox=(cv.width-meta.width*fs)/2; st.oy=(cv.height-meta.height*fs)/2; draw();
        }}
        function m2p(x,y){{return {{x:(x-meta.origin_x)/meta.resolution,y:meta.height-1-((y-meta.origin_y)/meta.resolution)}};}}
        function p2s(p){{return {{x:st.ox+p.x*st.s,y:st.oy+p.y*st.s}};}}
        function draw(){{
          cv.width=cv.clientWidth; cv.height=cv.clientHeight; ctx.fillStyle='#0f1722'; ctx.fillRect(0,0,cv.width,cv.height);
          if(hasMap&&img&&img.complete) ctx.drawImage(img,st.ox,st.oy,meta.width*st.s,meta.height*st.s);
          if(pts.length<1) return;
          ctx.strokeStyle='#3a8dff'; ctx.lineWidth=3; ctx.beginPath();
          for(let i=0;i<pts.length;i++){{const ps=p2s(hasMap?m2p(pts[i].x,pts[i].y):{{x:pts[i].x,y:pts[i].y}}); if(i===0)ctx.moveTo(ps.x,ps.y); else ctx.lineTo(ps.x,ps.y);}}
          if(pts.length>1) ctx.stroke();
          ctx.font='12px Microsoft YaHei';
          for(let i=0;i<pts.length;i++){{const ps=p2s(hasMap?m2p(pts[i].x,pts[i].y):{{x:pts[i].x,y:pts[i].y}}); ctx.beginPath();ctx.arc(ps.x,ps.y,5,0,Math.PI*2);ctx.fillStyle='#ffd34d';ctx.fill();ctx.fillStyle='#fff';ctx.fillText((i+1)+' '+(pts[i].name||''),ps.x+7,ps.y-8);}}
        }}
        function zoom(k,cx,cy){{if(!hasMap)return; const prev=st.s; st.s=Math.max(0.02,Math.min(200,st.s*k)); st.ox=cx-(cx-st.ox)*(st.s/prev); st.oy=cy-(cy-st.oy)*(st.s/prev); draw();}}
        document.getElementById('fit').onclick=fit; document.getElementById('zin').onclick=()=>zoom(1.2,cv.width/2,cv.height/2); document.getElementById('zout').onclick=()=>zoom(0.84,cv.width/2,cv.height/2);
        cv.onwheel=e=>{{e.preventDefault();const r=cv.getBoundingClientRect();zoom(e.deltaY<0?1.15:0.87,e.clientX-r.left,e.clientY-r.top)}};
        cv.onmousedown=e=>{{if(e.button!==0)return;st.drag=true;st.sx=e.clientX;st.sy=e.clientY;st.aox=st.ox;st.aoy=st.oy;cv.style.cursor='grabbing';}};
        window.onmousemove=e=>{{if(!st.drag)return;st.ox=st.aox+(e.clientX-st.sx);st.oy=st.aoy+(e.clientY-st.sy);draw();}};
        window.onmouseup=()=>{{st.drag=false;cv.style.cursor='grab';}};
        window.onresize=()=>{{draw(); if(hasMap&&(!img||!img.complete))return; }};
        window.showRoutePreview=function(arr){{pts.length=0;(arr||[]).forEach(p=>{{const x=Number(p.x),y=Number(p.y);if(Number.isFinite(x)&&Number.isFinite(y))pts.push({{x,y,name:p.name||''}});}}); if(hasMap)fit(); else draw();}};
        window.clearRoutePreview=function(){{pts.length=0; if(hasMap)fit(); else draw();}};
        draw(); if(hasMap)fit();
        </script></body></html>
        """
        self._map_ready = False
        self.web_view.setHtml(html)

    def _on_map_load_finished(self, ok: bool) -> None:
        self._map_ready = bool(ok)
        if not self._map_ready:
            return
        if self._pending_route_points:
            self._apply_route_map_points(self._pending_route_points)
        else:
            self._clear_route_map()

    def _clear_route_map(self) -> None:
        self._pending_route_points = []
        if self.web_view is None or not self._map_ready:
            return
        self.web_view.page().runJavaScript("if(window.clearRoutePreview){window.clearRoutePreview();}")

    def _apply_route_map_points(self, points) -> None:
        self._pending_route_points = list(points or [])
        if self.web_view is None or not self._map_ready:
            return
        payload = json.dumps(self._pending_route_points, ensure_ascii=False)
        self.web_view.page().runJavaScript(
            f"if(window.showRoutePreview){{window.showRoutePreview({payload});}}"
        )

    def set_plan(self, plan) -> None:
        self._current_plan = plan
        if plan is None:
            self._clear_route_map()
            return
        points = []
        for wp in getattr(plan, "waypoints", []) or []:
            x = getattr(wp, "map_x", None)
            y = getattr(wp, "map_y", None)
            if x is None or y is None:
                x = getattr(wp, "longitude", None)
                y = getattr(wp, "latitude", None)
            if x is None or y is None:
                continue
            points.append({"x": float(x), "y": float(y), "name": str(getattr(wp, "point_name", ""))})
        self._apply_route_map_points(points)

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
        self._tune_window_size()
        self._apply_form_style()
        self._replace_buttons()
        self._build_runtime_panel()
        self._polish_summary_layout()
        self._bind_actions()
        self.load_inspectarea()

        self._patrol_service = PatrolService(self.db)
        self._executor = create_executor(self._executor_mode(), self)
        self._bind_executor_events()

    def _tune_window_size(self) -> None:
        self.resize(1024, 646)
        self.setMinimumSize(980, 620)

    def _apply_form_style(self) -> None:
        self.setStyleSheet(
            "QMainWindow {"
            "background: #f7f9fc;"
            "}"
            "QWidget#centralWidget {"
            "background: #f7f9fc;"
            "}"
            "QLabel#titleLabel {"
            "font: 600 16px 'Microsoft YaHei';"
            "color: #2f3a4a;"
            "padding: 6px 0 2px 0;"
            "}"
            "QGroupBox {"
            "font: 600 13px 'Microsoft YaHei';"
            "border: 1px solid #dbe3ef;"
            "border-radius: 10px;"
            "margin-top: 10px;"
            "padding: 10px;"
            "background: #ffffff;"
            "}"
            "QGroupBox::title {"
            "subcontrol-origin: margin;"
            "left: 10px;"
            "padding: 0 6px;"
            "color: #2f3a4a;"
            "}"
            "QLabel {"
            "font: 13px 'Microsoft YaHei';"
            "color: #2f3a4a;"
            "}"
            "QComboBox, QPlainTextEdit, QProgressBar {"
            "font: 13px 'Microsoft YaHei';"
            "border: 1px solid #cfd7e3;"
            "border-radius: 6px;"
            "background: #ffffff;"
            "}"
            "QComboBox {"
            "padding: 6px 10px;"
            "}"
            "QComboBox::drop-down {"
            "border: none;"
            "width: 28px;"
            "}"
            "QComboBox QAbstractItemView {"
            "border: 1px solid #cfd7e3;"
            "background: #ffffff;"
            "selection-background-color: #eaf2ff;"
            "selection-color: #20324d;"
            "}"
            "QProgressBar {"
            "text-align: center;"
            "padding: 2px;"
            "min-height: 28px;"
            "}"
            "QProgressBar::chunk {"
            "border-radius: 4px;"
            "background: #4a90ff;"
            "}"
            "QPlainTextEdit {"
            "padding: 10px;"
            "selection-background-color: #d8e8ff;"
            "}"
            "QFrame#runtimePanel {"
            "background: #ffffff;"
            "border: 1px solid #dbe3ef;"
            "border-radius: 10px;"
            "}"
            "QLabel#lblRuntime, QLabel#statusLabel {"
            "font: 600 13px 'Microsoft YaHei';"
            "color: #2f3a4a;"
            "}"
        )

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
            btn.setMinimumHeight(42)
            btn.setMinimumWidth(0)
            layout.insertWidget(idx, btn, 1)
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

    def _polish_summary_layout(self) -> None:
        layout = getattr(self.ui, "verticalLayout", None)
        if layout is not None:
            layout.setContentsMargins(20, 18, 20, 20)
            layout.setSpacing(14)

        self.ui.titleLabel.setFixedHeight(34)

        button_row = getattr(self.ui, "buttonRow", None)
        if button_row is not None:
            button_row.setSpacing(12)

        for btn in (
            self.ui.btn_InspectArea,
            self.ui.btn_InspectPoint,
            self.ui.btn_InspectRoute,
        ):
            btn.setMinimumHeight(42)

        self.ui.infoGroup.setMinimumHeight(120)
        self.ui.formLayout.setContentsMargins(16, 16, 16, 14)
        self.ui.formLayout.setHorizontalSpacing(16)
        self.ui.formLayout.setVerticalSpacing(12)

        for combo in (self.ui.txt_InspectArea, self.ui.txt_InspectRoute):
            combo.setMinimumHeight(36)

        self.ui.statusLabel.setContentsMargins(6, 0, 0, 0)

        self.cmbExecutorMode.setMinimumHeight(36)
        self.cmbExecutorMode.setMinimumWidth(140)
        self.lbl_Runtime.setContentsMargins(6, 0, 0, 0)
        self.progressPatrol.setMinimumHeight(28)
        self.txt_RuntimeLog.setMinimumHeight(150)

        runtime_panel = getattr(self, "txt_RuntimeLog", None)
        runtime_panel = runtime_panel.parentWidget() if runtime_panel is not None else None
        if runtime_panel is not None and runtime_panel.layout() is not None:
            runtime_panel.layout().setContentsMargins(14, 14, 14, 14)
            runtime_panel.layout().setSpacing(10)

        for btn in (
            self.btn_StartPatrol,
            self.btn_PausePatrol,
            self.btn_ResumePatrol,
            self.btn_StopPatrol,
            self.btn_Emergency,
            self.btnOpenExecWindow,
        ):
            btn.setMinimumHeight(38)

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

    def _show_execution_window(self, plan=None) -> None:
        if self._exec_win is None:
            self._exec_win = PatrolExecutionWindow(self)
        area = self.ui.txt_InspectArea.currentText()
        route = self.ui.txt_InspectRoute.currentText()
        self._exec_win.set_route_info(area, route)
        if plan is not None:
            self._exec_win.set_plan(plan)
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

        self._show_execution_window(plan)
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
