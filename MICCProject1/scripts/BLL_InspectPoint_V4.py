import os
import re
import sys
import math
import threading
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from PyQt5.QtWidgets import QApplication, QTableWidgetItem, QMessageBox, QLineEdit
from PyQt5.QtGui import QIcon, QPixmap, QImage
from MICCProject1.ui.Frm_InspectPoint import Ui_Frm_InspectPoint  # 导入自动生成的界面类
from MICCProject1.scripts.DBHelper import DBHelper
# 以下用于显示地图
from PyQt5.QtCore import (
    QObject,
    pyqtSlot,
    QUrl,
    pyqtSignal,
    QEasingCurve,
    QPropertyAnimation,
    QCoreApplication,
    QTimer,
    Qt,
    QByteArray,
    QBuffer,
    QIODevice,
)
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import QMainWindow, QSizePolicy, QVBoxLayout, QSplitter, QWidget, QHBoxLayout, QLabel, QFrame, \
    QGraphicsOpacityEffect, QStyle
from qfluentwidgets import TransparentToolButton, FluentIcon as FIF, PushButton, PrimaryPushButton, LineEdit
import requests
import json

class BLL_InspectPoint(QMainWindow):
    def __init__(self, on_prev=None, on_next=None, on_close=None, on_jump=None):
        super().__init__()
        self.ui = Ui_Frm_InspectPoint()
        self.ui.setupUi(self)
        self.db = DBHelper()
        self._on_prev = on_prev
        self._on_next = on_next
        self._on_close = on_close
        self._on_jump = on_jump
        self._active_step = 1
        self.pointid = None

        # 地图模式与坐标缓存
        self._map_mode = "amap"  # grid | amap
        self._map_meta = None
        self._map_yaml_path = None
        self.selected_lng = None
        self.selected_lat = None
        self.selected_map_x = None
        self.selected_map_y = None
        self.selected_yaw_deg = 0.0
        self.current_point_id = None
        self._ros_pose_bridge = None
        self._pose_timer = None
        self._last_robot_pose_sig = None

        self.init_ui()
        # 初始化地图通信（优先本地栅格地图）
        self.init_map_channel()
        self.load_inspectpoint() #加载巡检点位
        self.load_inspectarea() # 加载巡检区域

        #self.setFixedSize(1639, 636)

    def init_ui(self) -> None:
        self._apply_window_icon()
        self._tune_form_geometry()
        self._apply_form_style()
        self._replace_top_controls()
        self._inject_yaw_input()
        self._relayout_point_page()
        self.ui.btn_Save.clicked.connect(self.on_save)
        self.ui.btn_Clear.clicked.connect(self.on_clear)
        self.ui.btn_Delete.clicked.connect(self.on_delete)
        self.ui.btn_Enable.clicked.connect(self.on_enable)
        self.ui.btn_Disable.clicked.connect(self.on_disable)
        self.ui.tv_InspectPoint.clicked.connect(self.on_select)
        self.ui.btn_Search.clicked.connect(self.on_search_address)
        # 绑定回车搜索（可选）
        self.ui.txt_MapAddress.returnPressed.connect(self.on_search_address)
        #显示当前区域所有点位标注
        self.ui.btn_showMarkers.clicked.connect(self.on_show_batch_markers)
        self.ui.btn_RemoveMarkers.clicked.connect(self.on_clear_batch_markers)

        self.ui.txt_PointType.addItems(["设备巡检","环境巡检","通道巡检"])
        self.ui.txt_PointType.setCurrentIndex(0)  # 默认选中第一个选项
        #新增:地图
        self.ui.widget_Map = QWebEngineView()
        self.ui.widget_Map.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 为GroupBox设置垂直布局
        layout = QVBoxLayout(self.ui.groupBox)
        layout.setContentsMargins(0, 0, 0, 0)  # 去除内边距，让web_view填满GroupBox
        # 手动创建QWebEngineView实例
        self.web_view = QWebEngineView()
        # 设置自适应大小（填满GroupBox）
        self.web_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 将web_view添加到GroupBox的布局中
        layout.addWidget(self.web_view)
        # Remove step controls (区域->点位->路线 + arrows/close) per latest UI request.
        # Keep business flow callbacks, but no longer render this nav bar.
        # self._init_nav()

    def _inject_yaw_input(self) -> None:
        host = getattr(self.ui, "gbox_status", None)
        if host is None:
            return

        if hasattr(self.ui, "label_9"):
            self.ui.label_9.setText("朝向(°)：")

        self.txt_YawDeg = QLineEdit(host)
        self.txt_YawDeg.setObjectName("txt_YawDeg")
        self.txt_YawDeg.setGeometry(70, 224, 120, 30)
        self.txt_YawDeg.setPlaceholderText("例如: 90")

        self.lbl_YawReq = QLabel("(*)", host)
        self.lbl_YawReq.setObjectName("lbl_YawReq")
        self.lbl_YawReq.setGeometry(190, 231, 16, 16)
        self.lbl_YawReq.setStyleSheet("color: rgb(255, 0, 0);")

        if hasattr(self.ui, "txt_Remark"):
            self.ui.txt_Remark.setGeometry(200, 224, 191, 61)
        self.lbl_RemarkEx = QLabel("备注：", host)
        self.lbl_RemarkEx.setObjectName("lbl_RemarkEx")
        self.lbl_RemarkEx.setGeometry(200, 198, 61, 24)

    def _init_nav(self) -> None:
        self._nav_bar = QWidget(self)
        self._nav_bar.setObjectName("navBar")
        self._nav_bar.setFixedHeight(36)
        layout = QHBoxLayout(self._nav_bar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self._step_bar = self._build_step_bar(active_index=1)
        self._btn_prev = TransparentToolButton(FIF.LEFT_ARROW)
        self._btn_next = TransparentToolButton(FIF.RIGHT_ARROW)
        self._btn_close = TransparentToolButton(FIF.CLOSE)
        self._btn_prev.setToolTip("上一步")
        self._btn_next.setToolTip("下一步")
        self._btn_close.setToolTip("关闭")
        for btn in (self._btn_prev, self._btn_next, self._btn_close):
            btn.setFixedSize(28, 28)
            btn.setIconSize(btn.iconSize())
        self._btn_prev.clicked.connect(self._on_nav_prev)
        self._btn_next.clicked.connect(self._on_nav_next)
        self._btn_close.clicked.connect(self._on_nav_close)

        layout.addWidget(self._step_bar, 1)
        layout.addWidget(self._btn_prev)
        layout.addWidget(self._btn_next)
        layout.addWidget(self._btn_close)
        self._apply_nav_style()
        self._reposition_nav()

    def _build_step_bar(self, active_index: int) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("stepBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(10, 2, 10, 2)
        bar_layout.setSpacing(6)

        self._step_buttons = []
        labels = ["区域", "点位", "路线"]
        for i, name in enumerate(labels):
            btn = PushButton(name, bar)
            btn.setProperty("stepPill", True)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda _=False, idx=i: self._on_step_clicked(idx))
            if i == active_index:
                btn.setChecked(True)
            self._step_buttons.append(btn)
            bar_layout.addWidget(btn)
            if i < len(labels) - 1:
                arrow = QLabel("->", bar)
                arrow.setObjectName("stepArrow")
                bar_layout.addWidget(arrow)

        self._active_step = active_index
        if self._step_buttons:
            self._animate_step(self._step_buttons[active_index])
        return bar

    def _apply_nav_style(self) -> None:
        self._nav_bar.setStyleSheet(
            "QWidget#navBar {"
            "background: rgba(255,255,255,210);"
            "border: 1px solid rgba(32,56,96,18);"
            "border-radius: 14px;"
            "}"
            "QFrame#stepBar {"
            "background: rgba(255,255,255,0.85);"
            "border: 1px solid rgba(40,80,140,20);"
            "border-radius: 14px;"
            "}"
            "QPushButton[stepPill='true'] {"
            "padding: 0 12px;"
            "border-radius: 13px;"
            "border: 1px solid rgba(0,0,0,20);"
            "background: rgba(255,255,255,0.7);"
            "color: #55606d;"
            "}"
            "QPushButton[stepPill='true']:hover {"
            "background: rgba(74,144,255,0.08);"
            "}"
            "QPushButton[stepPill='true']:checked {"
            "border: 1px solid #4a90ff;"
            "background: rgba(74,144,255,0.18);"
            "color: #1f2d3d;"
            "}"
            "QLabel#stepArrow {"
            "color: #8a97a5;"
            "}"
        )

    def _animate_step(self, btn: PushButton) -> None:
        effect = btn.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(btn)
            btn.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", btn)
        anim.setStartValue(0.6)
        anim.setEndValue(1.0)
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        btn._step_anim = anim

    def _on_step_clicked(self, index: int) -> None:
        if index == self._active_step:
            return
        if getattr(self, "_step_buttons", None):
            if 0 <= index < len(self._step_buttons):
                self._animate_step(self._step_buttons[index])
        if callable(self._on_jump):
            self.close()
            self._on_jump(index)
            return
        if index < self._active_step and callable(self._on_prev):
            self.close()
            self._on_prev()
            return
        if index > self._active_step and callable(self._on_next):
            self.close()
            self._on_next()
            return

    def _reposition_nav(self) -> None:
        if self._dock_nav_bar():
            return
        w = self.width()
        title_h = self.style().pixelMetric(QStyle.PM_TitleBarHeight, None, self)
        self._nav_bar.adjustSize()
        self._nav_bar.move(w - self._nav_bar.width() - 12, max(8, title_h + 8))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout_point_page()
        if hasattr(self, "_nav_bar"):
            self._reposition_nav()

    def _tune_form_geometry(self) -> None:
        self.resize(1366, 820)
        self.setMinimumSize(1220, 760)

    def _relayout_point_page(self) -> None:
        margin = 12
        gap = 14
        content_width = self.width() - margin * 2
        content_height = self.height() - margin * 2

        left_width = max(430, min(500, int(content_width * 0.34)))
        right_width = max(640, content_width - left_width - gap)
        if left_width + right_width + gap > content_width:
            left_width = max(410, content_width - right_width - gap)

        status_height = max(420, min(500, int(content_height * 0.6)))
        list_height = max(230, content_height - status_height - gap)
        status_height = content_height - list_height - gap

        self.ui.gbox_status.setGeometry(margin, margin, left_width, status_height)
        self.ui.groupBox_2.setGeometry(margin, margin + status_height + gap, left_width, list_height)

        right_x = margin + left_width + gap
        search_height = 38
        search_gap = 12
        search_btn_width = min(230, max(180, int(right_width * 0.26)))
        self.ui.txt_MapAddress.setGeometry(
            right_x,
            margin,
            right_width - search_btn_width - search_gap,
            34,
        )
        self.ui.btn_Search.setGeometry(
            right_x + right_width - search_btn_width,
            margin,
            search_btn_width,
            search_height,
        )

        map_top = margin + search_height + 12
        marker_height = 38
        marker_y = self.height() - margin - marker_height
        map_height = max(360, marker_y - map_top - 12)
        self.ui.groupBox.setGeometry(right_x, map_top, right_width, map_height)

        show_width = max(320, int(right_width * 0.62))
        remove_width = max(170, right_width - show_width - 12)
        self.ui.btn_showMarkers.setGeometry(right_x, marker_y, show_width, marker_height)
        self.ui.btn_RemoveMarkers.setGeometry(
            right_x + right_width - remove_width,
            marker_y,
            remove_width,
            marker_height,
        )

        self._relayout_point_status(left_width, status_height)
        self._relayout_point_list(left_width, list_height)

    def _relayout_point_status(self, group_width: int, group_height: int) -> None:
        label_x = 18
        labels_width = 86
        field_x = 118
        right_margin = 18
        star_gap = 6
        row_height = 32
        field_width = group_width - field_x - right_margin - 18

        self.ui.layoutWidget1.setGeometry(label_x, 36, labels_width, 200)
        self.ui.gridLayout.setVerticalSpacing(12)

        self.ui.layoutWidget2.setGeometry(field_x, 36, field_width, 158)
        self.ui.gridLayout_4.setVerticalSpacing(12)

        star_x = field_x + field_width + star_gap
        self.ui.label_15.setGeometry(star_x, 43, 18, 18)
        self.ui.label_13.setGeometry(star_x, 87, 18, 18)
        self.ui.label_14.setGeometry(star_x, 131, 18, 18)

        geo_y = 212
        lon_width = max(130, (field_width - 88) // 2)
        lat_width = max(130, field_width - lon_width - 78)
        self.ui.txt_Longitude.setGeometry(field_x, geo_y, lon_width, row_height)
        self.ui.label_11.setGeometry(field_x + lon_width + 10, geo_y, 58, 24)
        self.ui.txt_Latitude.setGeometry(field_x + lon_width + 78, geo_y, lat_width, row_height)

        yaw_y = geo_y + row_height + 16
        if hasattr(self, "txt_YawDeg"):
            self.txt_YawDeg.setGeometry(field_x, yaw_y, 140, row_height)
        if hasattr(self, "lbl_YawReq"):
            self.lbl_YawReq.setGeometry(field_x + 146, yaw_y + 7, 18, 18)
        if hasattr(self, "lbl_RemarkEx"):
            self.lbl_RemarkEx.setGeometry(field_x + 184, yaw_y, 62, 24)

        buttons_height = 34
        note_height = 24
        buttons_y = group_height - buttons_height - 26
        note_y = buttons_y - note_height - 10
        remark_x = field_x + 184
        remark_width = max(180, group_width - remark_x - right_margin)
        remark_height = max(72, note_y - yaw_y - 8)
        self.ui.txt_Remark.setGeometry(remark_x, yaw_y, remark_width, remark_height)
        self.ui.lab_Note.setGeometry(label_x, note_y, group_width - label_x - right_margin, note_height)
        self.ui.layoutWidget_2.setGeometry(
            max(40, (group_width - 300) // 2),
            buttons_y,
            min(300, group_width - 80),
            buttons_height,
        )

    def _relayout_point_list(self, group_width: int, group_height: int) -> None:
        inner_margin = 14
        controls_width = min(270, group_width - inner_margin * 2)
        self.ui.layoutWidget.setGeometry(
            max(inner_margin, group_width - controls_width - inner_margin),
            16,
            controls_width,
            34,
        )
        self.ui.gridLayout_3.setHorizontalSpacing(10)
        for name in ("btn_Delete", "btn_Enable", "btn_Disable"):
            btn = getattr(self.ui, name, None)
            if btn:
                btn.setMinimumHeight(30)

        table_y = self.ui.layoutWidget.y() + self.ui.layoutWidget.height() + 14
        self.ui.tv_InspectPoint.setGeometry(
            inner_margin,
            table_y,
            group_width - inner_margin * 2,
            max(150, group_height - table_y - inner_margin),
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not getattr(self, "_maximized_once", False):
            self._maximized_once = True
            self.showMaximized()

    def _on_nav_prev(self) -> None:
        if callable(self._on_prev):
            self.close()
            self._on_prev()

    def _on_nav_next(self) -> None:
        if callable(self._on_next):
            self.close()
            self._on_next()

    def _on_nav_close(self) -> None:
        if callable(self._on_close):
            self._on_close()
        else:
            self.close()


    def load_inspectpoint(self) -> None:
        self.ui.tv_InspectPoint.setRowCount(0)
        if self._is_grid_mode():
            self.ui.tv_InspectPoint.horizontalHeaderItem(3).setText("MapX")
            self.ui.tv_InspectPoint.horizontalHeaderItem(4).setText("MapY")
        else:
            self.ui.tv_InspectPoint.horizontalHeaderItem(3).setText("经度")
            self.ui.tv_InspectPoint.horizontalHeaderItem(4).setText("纬度")

        recordlist = self.db.fetch_all("select *, ia.AreaName from InspectArea ia, InspectPoint ip where ip.AreaID = ia.AreaID")
        for row, record in enumerate(recordlist):
            self.ui.tv_InspectPoint.insertRow(row)
            x_val = record.get("MapX") if record.get("MapX") is not None else record.get("Longitude", "")
            y_val = record.get("MapY") if record.get("MapY") is not None else record.get("Latitude", "")
            self.ui.tv_InspectPoint.setItem(row, 0, QTableWidgetItem(str(record.get("PointId", ""))))  # 巡检点位ID
            self.ui.tv_InspectPoint.setItem(row, 1, QTableWidgetItem(str(record.get("PointName", ""))))  #点位名称
            self.ui.tv_InspectPoint.setItem(row, 2, QTableWidgetItem(str(record.get("AreaName", ""))))   #区域名称
            self.ui.tv_InspectPoint.setItem(row, 3, QTableWidgetItem(str(x_val)))
            self.ui.tv_InspectPoint.setItem(row, 4, QTableWidgetItem(str(y_val)))
            self.ui.tv_InspectPoint.setItem(row, 5, QTableWidgetItem("启用" if record.get("Status") == 1 else "禁用" )) #状态

        self.setup_table_view()


    def load_inspectarea(self):
        self.ui.txt_AreaId.clear()
        recordlist = self.db.fetch_all("SELECT AreaId, AreaName FROM InspectArea ORDER BY AreaId")
        if not recordlist:
            self.ui.txt_AreaId.addItem("暂无巡检区域")
            return
        for record in recordlist:
            areaid = record['AreaId']  # 通过键'AreaID'取对应值
            areaname = record['AreaName']  # 通过键'AreaName'取对应值
            self.ui.txt_AreaId.addItem(areaname,userData=areaid)

    def _is_grid_mode(self) -> bool:
        return self._map_mode == "grid"

    def _set_coordinate_labels(self) -> None:
        if self._is_grid_mode():
            self.ui.label_10.setText("Map X：")
            self.ui.label_11.setText("Map Y：")
            self.ui.txt_MapAddress.setPlaceholderText("当前使用本地栅格地图，地址搜索已禁用")
            self.ui.btn_Search.setText("地址搜索(AMap)")
        else:
            self.ui.label_10.setText("经度：")
            self.ui.label_11.setText("纬度：")
            self.ui.txt_MapAddress.setPlaceholderText("请输入地址（如：北京市朝阳区天安门）")
            self.ui.btn_Search.setText("搜索地址并定位")

    def _candidate_map_yamls(self):
        candidates = []
        env_yaml = os.getenv("UAV_MAP_YAML", "").strip()
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
                        origin = (float(parts[0]), float(parts[1]), float(parts[2]) if len(parts) >= 3 else 0.0)

        if not image_value or resolution is None or origin is None:
            raise ValueError(f"地图yaml缺少关键字段: {yaml_path}")

        image_path = Path(image_value)
        if not image_path.is_absolute():
            image_path = (yaml_path.parent / image_path).resolve()

        if not image_path.exists():
            local_fallback = (yaml_path.parent / Path(image_value).name).resolve()
            if local_fallback.exists():
                image_path = local_fallback

        if not image_path.exists():
            raise FileNotFoundError(f"地图图片不存在: {image_path}")

        qimg = QImage(str(image_path))
        if qimg.isNull():
            raise ValueError(f"无法读取地图图片: {image_path}")

        # QtWebEngine 对 PGM 支持不稳定，统一转成 PNG data URL 再给前端渲染。
        png_bytes = QByteArray()
        buffer = QBuffer(png_bytes)
        if not buffer.open(QIODevice.WriteOnly):
            raise ValueError("无法打开内存缓冲区用于地图编码。")
        if not qimg.save(buffer, "PNG"):
            buffer.close()
            raise ValueError("地图图片转 PNG 失败。")
        buffer.close()
        image_data_url = "data:image/png;base64," + bytes(png_bytes.toBase64()).decode("ascii")

        return {
            "yaml_path": str(yaml_path),
            "image_path": str(image_path),
            "image_url": Path(image_path).as_uri(),
            "image_data_url": image_data_url,
            "resolution": float(resolution),
            "origin_x": float(origin[0]),
            "origin_y": float(origin[1]),
            "origin_yaw": float(origin[2]),
            "width": int(qimg.width()),
            "height": int(qimg.height()),
        }

    def _load_grid_map_html(self, meta: dict) -> None:
        self._map_meta = meta
        map_name = Path(meta.get("yaml_path", "")).name
        image_url = meta.get("image_data_url") or meta["image_url"]
        html = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; background: #0e1621; color: #e6edf6; overflow: hidden; }}
                #root {{ width: 100%; height: 100%; display: flex; flex-direction: column; }}
                #meta {{
                    padding: 8px 10px;
                    font: 12px 'Microsoft YaHei';
                    background: #142235;
                    border-bottom: 1px solid #29435e;
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 10px;
                }}
                #metaText {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
                #metaStatus {{ color: #8fb8dc; white-space: nowrap; }}
                #wrap {{ flex: 1; position: relative; }}
                #canvas {{ position: absolute; inset: 0; width: 100%; height: 100%; cursor: grab; }}
                #toolbar {{
                    position: absolute;
                    right: 12px;
                    top: 12px;
                    z-index: 3;
                    display: flex;
                    gap: 8px;
                    align-items: center;
                    background: rgba(10, 22, 35, 0.72);
                    border: 1px solid rgba(127, 174, 214, 0.35);
                    border-radius: 8px;
                    padding: 6px 8px;
                }}
                #toolbar button {{
                    min-width: 34px;
                    height: 26px;
                    border: 1px solid #4a6f93;
                    border-radius: 5px;
                    background: #16304a;
                    color: #dcefff;
                    font: 12px 'Microsoft YaHei';
                    cursor: pointer;
                }}
                #toolbar button:hover {{ background: #204566; }}
                #hint {{ color: #9db9d4; font: 11px 'Microsoft YaHei'; }}
            </style>
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
        </head>
        <body>
            <div id="root">
                <div id="meta">
                    <div id="metaText">??: {map_name} | ???: {meta['resolution']} m/px | ??: ({meta['origin_x']:.3f}, {meta['origin_y']:.3f})</div>
                    <div id="metaStatus">??: 1.00x</div>
                </div>
                <div id="wrap">
                    <canvas id="canvas"></canvas>
                    <div id="toolbar">
                        <button id="btnPoseMode" title="朝向拖拽模式">Yaw:关</button>
                        <button id="btnFit" title="????">??</button>
                        <button id="btnZoomIn" title="??">+</button>
                        <button id="btnZoomOut" title="??">-</button>
                        <span id="hint">左键平移；开Yaw后拖拽箭头</span>
                    </div>
                </div>
            </div>
            <script>
                const meta = {{
                    width: {meta['width']},
                    height: {meta['height']},
                    resolution: {meta['resolution']},
                    originX: {meta['origin_x']},
                    originY: {meta['origin_y']}
                }};
                let pythonObj = null;
                new QWebChannel(qt.webChannelTransport, function(channel) {{
                    pythonObj = channel.objects.pythonObj;
                }});

                const canvas = document.getElementById('canvas');
                const ctx = canvas.getContext('2d');
                const statusEl = document.getElementById('metaStatus');
                const btnPoseMode = document.getElementById('btnPoseMode');
                const btnFit = document.getElementById('btnFit');
                const btnZoomIn = document.getElementById('btnZoomIn');
                const btnZoomOut = document.getElementById('btnZoomOut');
                const img = new Image();
                img.src = '{image_url}';
                img.onerror = function() {{
                    console.error('grid map image load failed', img.src);
                }};

                let points = [];
                let selected = null;
                let robotPose = null;
                let poseMode = false;
                const yawDrag = {{ active: false, yawDeg: 0 }};
                const view = {{ scale: 1, offsetX: 0, offsetY: 0 }};
                const drag = {{ active: false, moved: false, startX: 0, startY: 0, originOffsetX: 0, originOffsetY: 0 }};
                let inited = false;

                function mapToPixel(mapX, mapY) {{
                    const px = (mapX - meta.originX) / meta.resolution;
                    const py = meta.height - 1 - ((mapY - meta.originY) / meta.resolution);
                    return {{px, py}};
                }}

                function pixelToMap(px, py) {{
                    const mapX = meta.originX + px * meta.resolution;
                    const mapY = meta.originY + (meta.height - 1 - py) * meta.resolution;
                    return {{mapX, mapY}};
                }}

                function fitScale() {{
                    if (!canvas.width || !canvas.height) return 1;
                    return Math.min(canvas.width / meta.width, canvas.height / meta.height);
                }}

                function fitView() {{
                    const s = fitScale();
                    view.scale = s;
                    view.offsetX = (canvas.width - meta.width * s) / 2;
                    view.offsetY = (canvas.height - meta.height * s) / 2;
                }}

                function worldToScreen(px, py) {{
                    return {{ x: view.offsetX + px * view.scale, y: view.offsetY + py * view.scale }};
                }}

                function screenToWorld(x, y) {{
                    return {{ px: (x - view.offsetX) / view.scale, py: (y - view.offsetY) / view.scale }};
                }}

                function mapToScreen(mapX, mapY) {{
                    const pix = mapToPixel(mapX, mapY);
                    return worldToScreen(pix.px, pix.py);
                }}

                function screenToMap(x, y) {{
                    const w = screenToWorld(x, y);
                    if (w.px < 0 || w.py < 0 || w.px > meta.width || w.py > meta.height) {{
                        return null;
                    }}
                    return pixelToMap(w.px, w.py);
                }}

                function normalizeYawDeg(yawDeg) {{
                    let yaw = Number(yawDeg) || 0;
                    while (yaw > 180) yaw -= 360;
                    while (yaw <= -180) yaw += 360;
                    return yaw;
                }}

                function yawDegToScreenRad(yawDeg) {{
                    return -normalizeYawDeg(yawDeg) * Math.PI / 180.0;
                }}

                function computeYawDegFromClient(clientX, clientY) {{
                    if (!selected) return 0;
                    const rect = canvas.getBoundingClientRect();
                    const px = clientX - rect.left;
                    const py = clientY - rect.top;
                    const anchor = mapToScreen(selected.x, selected.y);
                    const dx = px - anchor.x;
                    const dy = py - anchor.y;
                    if ((dx * dx + dy * dy) < 9) {{
                        return normalizeYawDeg(selected.yawDeg || 0);
                    }}
                    return normalizeYawDeg(Math.atan2(-dy, dx) * 180.0 / Math.PI);
                }}

                function drawYawArrow(mapX, mapY, yawDeg, color) {{
                    const p = mapToScreen(mapX, mapY);
                    const rad = yawDegToScreenRad(yawDeg);
                    const len = 46;
                    const tx = p.x + Math.cos(rad) * len;
                    const ty = p.y + Math.sin(rad) * len;
                    ctx.strokeStyle = color || '#ff6b6b';
                    ctx.lineWidth = 2.2;
                    ctx.beginPath();
                    ctx.moveTo(p.x, p.y);
                    ctx.lineTo(tx, ty);
                    ctx.stroke();
                    ctx.fillStyle = color || '#ff6b6b';
                    const ah = 10;
                    const aw = 6;
                    const bx = tx - Math.cos(rad) * ah;
                    const by = ty - Math.sin(rad) * ah;
                    const lx = bx + Math.cos(rad + Math.PI / 2) * aw;
                    const ly = by + Math.sin(rad + Math.PI / 2) * aw;
                    const rx = bx + Math.cos(rad - Math.PI / 2) * aw;
                    const ry = by + Math.sin(rad - Math.PI / 2) * aw;
                    ctx.beginPath();
                    ctx.moveTo(tx, ty);
                    ctx.lineTo(lx, ly);
                    ctx.lineTo(rx, ry);
                    ctx.closePath();
                    ctx.fill();
                }}

                function refreshStatus() {{
                    const ratio = view.scale / Math.max(fitScale(), 1e-6);
                    let text = '??: ' + ratio.toFixed(2) + 'x';
                    text += ' | Yaw拖拽:' + (poseMode ? '开' : '关');
                    if (selected && Number.isFinite(selected.yawDeg)) {{
                        text += ' | 朝向: ' + normalizeYawDeg(selected.yawDeg).toFixed(1) + '°';
                    }}
                    if (robotPose) {{
                        text += ' | ??: (' + robotPose.x.toFixed(2) + ', ' + robotPose.y.toFixed(2) + ')';
                    }}
                    statusEl.textContent = text;
                }}

                function resizeCanvas() {{
                    let centerMap = null;
                    if (inited && canvas.width > 0 && canvas.height > 0) {{
                        centerMap = screenToMap(canvas.width / 2, canvas.height / 2);
                    }}

                    canvas.width = canvas.clientWidth;
                    canvas.height = canvas.clientHeight;

                    if (!inited) {{
                        fitView();
                        inited = true;
                    }} else if (centerMap) {{
                        const centerPix = mapToPixel(centerMap.mapX, centerMap.mapY);
                        view.offsetX = canvas.width / 2 - centerPix.px * view.scale;
                        view.offsetY = canvas.height / 2 - centerPix.py * view.scale;
                    }}
                    draw();
                }}

                function zoomAt(cx, cy, factor) {{
                    const prev = view.scale;
                    const baseFit = fitScale();
                    const minScale = Math.max(baseFit * 0.35, 0.05);
                    const maxScale = baseFit * 30.0;
                    let next = prev * factor;
                    next = Math.max(minScale, Math.min(maxScale, next));
                    if (Math.abs(next - prev) < 1e-8) return;

                    const world = screenToWorld(cx, cy);
                    view.scale = next;
                    view.offsetX = cx - world.px * next;
                    view.offsetY = cy - world.py * next;
                    draw();
                }}

                function drawPoint(mapX, mapY, color, label) {{
                    const p = mapToScreen(mapX, mapY);
                    ctx.fillStyle = color;
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
                    ctx.fill();
                    if (label) {{
                        ctx.fillStyle = '#ffffff';
                        ctx.font = "12px 'Microsoft YaHei'";
                        ctx.fillText(label, p.x + 8, p.y - 8);
                    }}
                }}

                function drawPath() {{
                    if (points.length < 2) return;
                    ctx.strokeStyle = '#2f93ff';
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    points.forEach((p, idx) => {{
                        const s = mapToScreen(p.x, p.y);
                        if (idx === 0) ctx.moveTo(s.x, s.y);
                        else ctx.lineTo(s.x, s.y);
                    }});
                    ctx.stroke();
                }}

                function drawRobot() {{
                    if (!robotPose) return;
                    const p = mapToScreen(robotPose.x, robotPose.y);
                    const yawRad = -robotPose.yawRad;
                    ctx.save();
                    ctx.translate(p.x, p.y);
                    ctx.rotate(yawRad);
                    ctx.beginPath();
                    ctx.moveTo(12, 0);
                    ctx.lineTo(-7, -6);
                    ctx.lineTo(-7, 6);
                    ctx.closePath();
                    ctx.fillStyle = '#ff5f5f';
                    ctx.fill();
                    ctx.beginPath();
                    ctx.arc(0, 0, 3.6, 0, Math.PI * 2);
                    ctx.fillStyle = '#ffe58f';
                    ctx.fill();
                    ctx.restore();
                }}

                function draw() {{
                    if (!canvas.width || !canvas.height) return;
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    ctx.fillStyle = '#0a111b';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);

                    if (img.complete && img.naturalWidth > 0 && img.naturalHeight > 0) {{
                        ctx.drawImage(img, view.offsetX, view.offsetY, meta.width * view.scale, meta.height * view.scale);
                    }} else {{
                        ctx.fillStyle = '#8ea6bf';
                        ctx.font = "13px 'Microsoft YaHei'";
                        ctx.fillText('????????????', 16, 24);
                    }}

                    drawPath();
                    points.forEach((p, idx) => drawPoint(p.x, p.y, '#ffcc33', String(idx + 1)));
                    if (selected) {{
                        drawPoint(selected.x, selected.y, '#ff4d4f', selected.name || '???');
                        if (Number.isFinite(selected.yawDeg)) {{
                            drawYawArrow(selected.x, selected.y, selected.yawDeg, '#ff6b6b');
                        }}
                    }}
                    drawRobot();
                    refreshStatus();
                }}

                function handleClick(clientX, clientY) {{
                    if (!pythonObj) return;
                    const r = canvas.getBoundingClientRect();
                    const x = clientX - r.left;
                    const y = clientY - r.top;
                    const m = screenToMap(x, y);
                    if (!m) return;
                    const baseYaw = robotPose ? robotPose.yawDeg : 0;
                    selected = {{x: m.mapX, y: m.mapY, yawDeg: normalizeYawDeg(baseYaw), name: '???'}};
                    draw();
                    pythonObj.receive_map_xy(Number(m.mapX.toFixed(3)), Number(m.mapY.toFixed(3)));
                }}

                canvas.addEventListener('mousedown', function(e) {{
                    if (e.button !== 0) return;
                    if (poseMode && selected) {{
                        const s = mapToScreen(selected.x, selected.y);
                        const r = canvas.getBoundingClientRect();
                        const cx = e.clientX - r.left;
                        const cy = e.clientY - r.top;
                        const dx = cx - s.x;
                        const dy = cy - s.y;
                        if ((dx * dx + dy * dy) <= 22 * 22) {{
                            yawDrag.active = true;
                            yawDrag.yawDeg = computeYawDegFromClient(e.clientX, e.clientY);
                            selected.yawDeg = yawDrag.yawDeg;
                            canvas.style.cursor = 'crosshair';
                            draw();
                            return;
                        }}
                    }}
                    drag.active = true;
                    drag.moved = false;
                    drag.startX = e.clientX;
                    drag.startY = e.clientY;
                    drag.originOffsetX = view.offsetX;
                    drag.originOffsetY = view.offsetY;
                    canvas.style.cursor = 'grabbing';
                }});

                window.addEventListener('mousemove', function(e) {{
                    if (yawDrag.active) {{
                        yawDrag.yawDeg = computeYawDegFromClient(e.clientX, e.clientY);
                        if (selected) selected.yawDeg = yawDrag.yawDeg;
                        draw();
                        return;
                    }}
                    if (!drag.active) return;
                    const dx = e.clientX - drag.startX;
                    const dy = e.clientY - drag.startY;
                    if (Math.abs(dx) + Math.abs(dy) > 3) {{
                        drag.moved = true;
                    }}
                    view.offsetX = drag.originOffsetX + dx;
                    view.offsetY = drag.originOffsetY + dy;
                    draw();
                }});

                window.addEventListener('mouseup', function(e) {{
                    if (yawDrag.active) {{
                        yawDrag.active = false;
                        canvas.style.cursor = 'grab';
                        if (selected) {{
                            selected.yawDeg = normalizeYawDeg(yawDrag.yawDeg);
                            if (pythonObj && typeof pythonObj.receive_map_pose === 'function') {{
                                pythonObj.receive_map_pose(
                                    Number(selected.x.toFixed(3)),
                                    Number(selected.y.toFixed(3)),
                                    Number(selected.yawDeg.toFixed(1))
                                );
                            }}
                        }}
                        draw();
                        return;
                    }}
                    if (!drag.active) return;
                    const moved = drag.moved;
                    drag.active = false;
                    canvas.style.cursor = 'grab';
                    if (!moved) {{
                        handleClick(e.clientX, e.clientY);
                    }}
                }});

                canvas.addEventListener('wheel', function(e) {{
                    e.preventDefault();
                    const r = canvas.getBoundingClientRect();
                    const cx = e.clientX - r.left;
                    const cy = e.clientY - r.top;
                    zoomAt(cx, cy, e.deltaY < 0 ? 1.15 : 0.87);
                }}, {{ passive: false }});

                btnPoseMode.addEventListener('click', function() {{
                    poseMode = !poseMode;
                    btnPoseMode.textContent = 'Yaw:' + (poseMode ? '开' : '关');
                    btnPoseMode.style.background = poseMode ? '#2f5f8c' : '#16304a';
                    draw();
                }});

                btnFit.addEventListener('click', function() {{
                    fitView();
                    draw();
                }});
                btnZoomIn.addEventListener('click', function() {{
                    zoomAt(canvas.width / 2, canvas.height / 2, 1.2);
                }});
                btnZoomOut.addEventListener('click', function() {{
                    zoomAt(canvas.width / 2, canvas.height / 2, 0.84);
                }});

                window.showMapMarkers = function(pointList) {{
                    points = (pointList || []).map(p => ({{x: Number(p.x), y: Number(p.y), name: p.name || ''}}));
                    draw();
                }};

                window.clearMapMarkers = function() {{
                    points = [];
                    selected = null;
                    draw();
                }};

                window.locateMapPoint = function(x, y, name, yawDeg) {{
                    const yaw = Number(yawDeg);
                    selected = {{
                        x: Number(x),
                        y: Number(y),
                        name: name || '???',
                        yawDeg: Number.isFinite(yaw) ? normalizeYawDeg(yaw) : 0
                    }};
                    draw();
                }};

                window.setPoseMode = function(enabled) {{
                    poseMode = !!enabled;
                    btnPoseMode.textContent = 'Yaw:' + (poseMode ? '开' : '关');
                    btnPoseMode.style.background = poseMode ? '#2f5f8c' : '#16304a';
                    draw();
                }};

                window.updateRobotPose = function(x, y, yawDeg) {{
                    const nx = Number(x);
                    const ny = Number(y);
                    const yaw = Number(yawDeg) || 0;
                    if (!Number.isFinite(nx) || !Number.isFinite(ny)) return;
                    robotPose = {{
                        x: nx,
                        y: ny,
                        yawDeg: yaw,
                        yawRad: yaw * Math.PI / 180.0
                    }};
                    draw();
                }};

                window.clearRobotPose = function() {{
                    robotPose = null;
                    draw();
                }};

                window.addEventListener('resize', resizeCanvas);
                img.onload = draw;
                resizeCanvas();
            </script>
        </body>
        </html>
        """
        self.web_view.setHtml(html, baseUrl=QUrl.fromLocalFile(str(Path(meta["image_path"]).parent) + "/"))

    def _try_init_grid_map(self) -> bool:
        for yaml_path in self._candidate_map_yamls():
            try:
                meta = self._parse_map_yaml(yaml_path)
                self._map_mode = "grid"
                self._map_yaml_path = str(yaml_path)
                self._load_grid_map_html(meta)
                return True
            except Exception:
                continue
        return False

    def _parse_optional_float(self, text: str):
        value = (text or "").strip()
        if not value:
            return None
        return float(value)

    def _normalize_yaw_deg(self, yaw: float) -> float:
        while yaw > 180.0:
            yaw -= 360.0
        while yaw <= -180.0:
            yaw += 360.0
        return yaw

    def _parse_required_yaw_deg(self) -> float:
        if not hasattr(self, "txt_YawDeg"):
            return float(self.selected_yaw_deg or 0.0)
        raw = self.txt_YawDeg.text().strip()
        if not raw:
            raise ValueError("empty yaw")
        yaw = float(raw)
        if not math.isfinite(yaw):
            raise ValueError("invalid yaw")
        yaw = self._normalize_yaw_deg(yaw)
        self.selected_yaw_deg = yaw
        self.txt_YawDeg.setText(f"{yaw:.2f}".rstrip("0").rstrip("."))
        return yaw


    def validate_required(self) -> bool:
        area_id = self.ui.txt_AreaId.currentData()
        if area_id is None:
            self.ui.lab_Note.setText("请先创建并选择巡检区域后再保存点位！")
            self.ui.lab_Note.setStyleSheet("color: red;")
            return False
        # 定义必填字段（控件变量 -> 字段名称）
        required = {
            self.ui.txt_PointName: "点位名称",
            self.ui.txt_PointCode: "点位编码"
        }
        for var, field_name in required.items():
            if not var.text().strip():
                self.ui.lab_Note.setText(f"{field_name}为必填项，请填写完整！")
                self.ui.lab_Note.setStyleSheet("color: red;")
                return False
        if hasattr(self, "txt_YawDeg") and not self.txt_YawDeg.text().strip():
            self.ui.lab_Note.setText("朝向为必填项，请填写车辆朝向角度(°)！")
            self.ui.lab_Note.setStyleSheet("color: red;")
            return False
        return True

    def setup_table_view(self) -> None:
        self.ui.tv_InspectPoint.resizeColumnsToContents()
        header = self.ui.tv_InspectPoint.horizontalHeader()
        header.setStretchLastSection(True)
        self.ui.tv_InspectPoint.setAlternatingRowColors(True)
        self.ui.tv_InspectPoint.setShowGrid(True)
        self.ui.tv_InspectPoint.setStyleSheet(
            "QTableView {gridline-color: #d0d0d0; alternate-background-color: #f8f8f8;}"
        )

    def _apply_form_style(self) -> None:
        self.setStyleSheet(
            "QMainWindow {"
            "background: #f7f9fc;"
            "}"
            "QGroupBox {"
            "font: 600 13px 'Microsoft YaHei';"
            "border: 1px solid #dbe3ef;"
            "border-radius: 8px;"
            "margin-top: 10px;"
            "padding: 8px;"
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
            "QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {"
            "font: 13px 'Microsoft YaHei';"
            "padding: 7px 9px;"
            "border: 1px solid #cfd7e3;"
            "border-radius: 6px;"
            "background: #ffffff;"
            "}"
            "QPushButton {"
            "font: 13px 'Microsoft YaHei';"
            "padding: 7px 16px;"
            "border-radius: 6px;"
            "border: 1px solid #cfd7e3;"
            "background: #ffffff;"
            "}"
            "QPushButton:hover {"
            "background: #eef4ff;"
            "border-color: #9bbcff;"
            "}"
            "QTableWidget {"
            "font: 13px 'Microsoft YaHei';"
            "gridline-color: #d0d7e2;"
            "background: #ffffff;"
            "}"
            "QHeaderView::section {"
            "font: 13px 'Microsoft YaHei';"
            "background: #f0f4fa;"
            "padding: 7px;"
            "border: 1px solid #dbe3ef;"
            "}"
        )
        for name in ("btn_Save", "btn_Clear", "btn_Delete", "btn_Enable", "btn_Disable", "btn_Search"):
            btn = getattr(self.ui, name, None)
            if btn:
                btn.setMinimumWidth(90)

    def _dock_nav_bar(self) -> bool:
        host = getattr(self.ui, "groupBox_2", None)
        table = getattr(self.ui, "tv_InspectPoint", None)
        if host is None or table is None:
            return False

        if not hasattr(self, "_table_base_rect"):
            self._table_base_rect = table.geometry()

        row_widget = getattr(self.ui, "layoutWidget", None)
        nav = self._nav_bar
        nav.setParent(host)
        nav.adjustSize()

        nav_y = 6
        nav_x = 8
        if row_widget is not None:
            row_rect = row_widget.geometry()
            row_widget.move(row_rect.x(), 6)
            row_rect = row_widget.geometry()
            nav_y = row_rect.y() + row_rect.height() + 4

        nav.resize(host.width() - 16, nav.height())
        nav.move(max(6, nav_x), max(0, nav_y))

        base = self._table_base_rect
        min_table_y = nav.y() + nav.height() + 8
        new_y = max(base.y(), min_table_y)
        delta = new_y - base.y()
        new_h = max(80, base.height() - delta)
        table.setGeometry(base.x(), new_y, base.width(), new_h)
        return True

    def _replace_top_controls(self) -> None:
        # Top buttons in list group box
        host = getattr(self.ui, "layoutWidget", None)
        layout = host.layout() if host is not None else None
        if layout is not None:
            for name in ("btn_Delete", "btn_Enable", "btn_Disable"):
                old = getattr(self.ui, name, None)
                if old:
                    old.hide()
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                if w:
                    w.setParent(None)

            btn_delete = PushButton("删除", host)
            btn_enable = PushButton("启用", host)
            btn_disable = PushButton("禁用", host)
            for btn in (btn_delete, btn_enable, btn_disable):
                btn.setFixedHeight(28)
                btn.setMinimumWidth(70)

            self.ui.btn_Delete = btn_delete
            self.ui.btn_Enable = btn_enable
            self.ui.btn_Disable = btn_disable

            layout.addWidget(btn_delete, 0, 0, 1, 1)
            layout.addWidget(btn_enable, 0, 1, 1, 1)
            layout.addWidget(btn_disable, 0, 2, 1, 1)

        # Top search controls
        old_input = getattr(self.ui, "txt_MapAddress", None)
        old_btn = getattr(self.ui, "btn_Search", None)
        if old_input is not None and old_btn is not None:
            old_input.hide()
            old_btn.hide()

            self._map_address = LineEdit(self)
            self._map_address.setPlaceholderText("输入地址（如：北京市朝阳区天安门）")
            self._map_address.setGeometry(old_input.geometry())
            self._map_address.setFixedHeight(old_input.height())

            self._btn_search = PrimaryPushButton("搜索地址并定位", self)
            self._btn_search.setGeometry(old_btn.geometry())
            self._btn_search.setFixedHeight(old_btn.height())

            self.ui.txt_MapAddress = self._map_address
            self.ui.btn_Search = self._btn_search

            self._btn_search.clicked.connect(self.on_search_address)
            self._map_address.returnPressed.connect(self.on_search_address)

    def _apply_window_icon(self) -> None:
        icon_path = Path(__file__).resolve().parents[2] / "assets" / "robot.png"
        if not icon_path.exists():
            return
        pix = QPixmap(str(icon_path))
        if pix.isNull():
            return
        icon = QIcon()
        for size in (16, 24, 32, 48, 64):
            icon.addPixmap(
                pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        self.setWindowIcon(icon)
        app = QApplication.instance()
        if app:
            app.setWindowIcon(icon)

    def on_save(self) -> None:
        if not self.validate_required():
            return
        areaId = self.ui.txt_AreaId.currentData()
        pointName = self.ui.txt_PointName.text().strip()
        pointCode = self.ui.txt_PointCode.text().strip()
        pointType = self.ui.txt_PointType.currentIndex()
        remark = self.ui.txt_Remark.text().strip()

        try:
            raw_x = self._parse_optional_float(self.ui.txt_Longitude.text())
            raw_y = self._parse_optional_float(self.ui.txt_Latitude.text())
        except ValueError:
            self.ui.lab_Note.setText("坐标格式错误，请输入数字。")
            self.ui.lab_Note.setStyleSheet("color: red;")
            return

        if self._is_grid_mode():
            map_x = raw_x
            map_y = raw_y
            if map_x is None or map_y is None:
                self.ui.lab_Note.setText("请先在地图上选择点位（MapX/MapY）。")
                self.ui.lab_Note.setStyleSheet("color: red;")
                return
            longitude = self.selected_lng
            latitude = self.selected_lat
        else:
            longitude = raw_x
            latitude = raw_y
            if longitude is None or latitude is None:
                self.ui.lab_Note.setText("请先选择经纬度。")
                self.ui.lab_Note.setStyleSheet("color: red;")
                return
            map_x = self.selected_map_x
            map_y = self.selected_map_y

        try:
            yaw_deg = self._parse_required_yaw_deg()
        except ValueError:
            self.ui.lab_Note.setText("朝向角度格式错误，请输入有效数字（单位：度）。")
            self.ui.lab_Note.setStyleSheet("color: red;")
            return

        try:
            if self.pointid:
                query = """
                UPDATE InspectPoint
                SET AreaId=%s, PointName=%s, PointCode=%s, PointType=%s,
                    Longitude=%s, Latitude=%s, MapX=%s, MapY=%s, YawDeg=%s, Remark=%s
                WHERE PointId=%s
                """
                params = (
                    areaId,
                    pointName,
                    pointCode,
                    pointType,
                    longitude,
                    latitude,
                    map_x,
                    map_y,
                    yaw_deg,
                    remark,
                    self.pointid,
                )
                i = self.db.execute_query(query, params)
                if i > 0:
                    self.ui.lab_Note.setText("巡检点位信息修改成功！")
                    self.clear_input()
                    self.load_inspectpoint()
                else:
                    self.ui.lab_Note.setText("巡检点位信息修改失败！")
            else:
                query = """
                INSERT INTO InspectPoint (AreaId, PointName, PointCode, PointType, Longitude, Latitude, MapX, MapY, YawDeg, Remark, Status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                """
                params = (areaId, pointName, pointCode, pointType, longitude, latitude, map_x, map_y, yaw_deg, remark)
                i = self.db.execute_query(query, params)
                if i > 0:
                    self.ui.lab_Note.setText("巡检点位信息添加成功！")
                    self.clear_input()
                    self.load_inspectpoint()
                else:
                    self.ui.lab_Note.setText("巡检点位信息添加失败！")
        except Exception as exc:
            self.ui.lab_Note.setText("巡检点位信息保存失败！" + str(exc))
            return

    # 选中某一项巡检点位数据
    def on_select(self, index) -> None:
        ins_item = self.ui.tv_InspectPoint.item(index.row(), 0)
        if ins_item is None:
            return
        self.pointid = int(ins_item.text())
        records = self.db.fetch_all("SELECT * FROM InspectPoint WHERE PointId = %s", (self.pointid,))
        if not records:
            return
        record = records[0]
        area_id = record.get("AreaId", record.get("AreaID", ""))
        for idx in range(self.ui.txt_AreaId.count()):
            if self.ui.txt_AreaId.itemData(idx) == area_id:
                self.ui.txt_AreaId.setCurrentIndex(idx)
                break

        self.ui.txt_PointName.setText(record.get("PointName", ""))
        self.ui.txt_PointCode.setText(record.get("PointCode", ""))
        self.ui.txt_PointType.setCurrentIndex(record.get("PointType", 0))
        map_x = record.get("MapX")
        map_y = record.get("MapY")
        lon = record.get("Longitude")
        lat = record.get("Latitude")
        display_x = map_x if map_x is not None else lon
        display_y = map_y if map_y is not None else lat
        self.ui.txt_Longitude.setText("" if display_x is None else str(display_x))
        self.ui.txt_Latitude.setText("" if display_y is None else str(display_y))
        self.ui.txt_Remark.setText(record.get("Remark", ""))
        self.selected_map_x = float(map_x) if map_x is not None else None
        self.selected_map_y = float(map_y) if map_y is not None else None
        self.selected_lng = float(lon) if lon is not None else None
        self.selected_lat = float(lat) if lat is not None else None
        self.selected_yaw_deg = float(record.get("YawDeg") or 0.0)
        if hasattr(self, "txt_YawDeg"):
            self.txt_YawDeg.setText(f"{self.selected_yaw_deg:.2f}".rstrip("0").rstrip("."))
        self.ui.gbox_status.setTitle("修改巡检点位")
        self.ui.lab_Note.clear()
        if self._is_grid_mode() and self.selected_map_x is not None and self.selected_map_y is not None:
            self.web_view.page().runJavaScript(
                f"if (typeof locateMapPoint === 'function') locateMapPoint({self.selected_map_x}, {self.selected_map_y}, {json.dumps(record.get('PointName', ''))}, {self.selected_yaw_deg});"
            )
        elif (not self._is_grid_mode()) and self.selected_lng is not None and self.selected_lat is not None:
            self.web_view.page().runJavaScript(
                f"locatePatrolMarker(1, {self.selected_lng}, {self.selected_lat}, {json.dumps(record.get('PointName', ''))})"
            )

        # 删除巡检点位
    def on_delete(self) -> None:
        selection = self.ui.tv_InspectPoint.selectedItems()
        if not selection:
            QMessageBox.warning(self, "操作提示", "请先选中要删除的巡检点位！")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除选中的巡检点位吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        ins_item = self.ui.tv_InspectPoint.item(self.ui.tv_InspectPoint.currentRow(), 0)
        if ins_item is None:
            return

        self.pointid = int(ins_item.text())

        # ????????????????????????????
        refs = self.db.fetch_all(
            "SELECT COUNT(1) AS Cnt FROM InspectRoutePoint WHERE PointId = %s",
            (self.pointid,),
        )
        ref_count = int((refs[0].get("Cnt", 0) if refs else 0) or 0)
        if ref_count > 0:
            msg = f"该巡检点已被 {ref_count} 条路线关联，请先在巡检路线管理中移除关联后再删除。"
            self.ui.lab_Note.setText(msg)
            QMessageBox.warning(self, "删除失败", msg)
            return

        rows = self.db.execute_query("DELETE FROM InspectPoint WHERE PointId = %s", (self.pointid,))
        affected = int(rows or 0)
        if affected > 0:
            self.ui.lab_Note.setText("巡检点位删除成功！")
            self.clear_input()
            self.load_inspectpoint()
        else:
            self.ui.lab_Note.setText("巡检点位删除失败！")

    def on_enable(self) -> None:
        selection = self.ui.tv_InspectPoint.selectedItems()
        if not selection:
            QMessageBox.warning(self, "操作提示", "请先选中要启用的巡检点位！")
            return
        else:
            ins_item = self.ui.tv_InspectPoint.item(self.ui.tv_InspectPoint.currentRow(), 0)
            if ins_item is None:
                return
            self.pointid = int(ins_item.text())
            i = self.db.execute_query("UPDATE InspectPoint SET Status = 1 WHERE PointId = %s", (self.pointid,))
            if (i > 0):
                self.ui.lab_Note.setText("巡检点位已启用！")
                self.clear_input()
                self.load_inspectpoint()
            else:
                self.ui.lab_Note.setText("巡检点位启用失败！")

    # 禁用巡检点位
    def on_disable(self) -> None:
        selection = self.ui.tv_InspectPoint.selectedItems()
        if not selection:
            QMessageBox.warning(self, "操作提示", "请先选中要禁用的巡检点位！")
            return
        else:
            ins_item = self.ui.tv_InspectPoint.item(self.ui.tv_InspectPoint.currentRow(), 0)
            if ins_item is None:
                return
            self.pointid = int(ins_item.text())
            i = self.db.execute_query("UPDATE InspectPoint SET Status = 0 WHERE PointId = %s", (self.pointid,))
            if (i > 0):
                self.ui.lab_Note.setText("巡检点位已禁用！")
                self.clear_input()
                self.load_inspectpoint()
            else:
                self.ui.lab_Note.setText("巡检点位禁用失败！")

    # 清空输入框和提示
    def on_clear(self):
        self.clear_input()
        self.ui.lab_Note.text()

    # 清空输入框
    def clear_input(self) -> None:
        self.ui.txt_PointName.clear()
        self.ui.txt_PointCode.clear()
        self.ui.txt_Latitude.clear()
        self.ui.txt_Longitude.clear()
        self.ui.txt_Remark.clear()
        if hasattr(self, "txt_YawDeg"):
            self.txt_YawDeg.clear()
        self.ui.gbox_status.setTitle("新增巡检点位")
        self.pointid = None
        self.selected_lng = None
        self.selected_lat = None
        self.selected_map_x = None
        self.selected_map_y = None
        self.selected_yaw_deg = 0.0

    def init_map_channel(self):
        """初始化地图通信通道（优先本地栅格地图，失败则回退AMap）"""
        self.channel = QWebChannel()
        self.map_communicator = MapCommunicator()
        self.channel.registerObject("pythonObj", self.map_communicator)
        self.web_view.page().setWebChannel(self.channel)

        self.map_communicator.point_selected.connect(self.on_map_point_selected)
        self.map_communicator.pose_selected.connect(self.on_map_pose_selected)
        self.map_communicator.marker_clicked.connect(self.on_marker_click)
        self.map_communicator.searchresult.connect(self.on_search_result)

        if not self._try_init_grid_map():
            self._map_mode = "amap"
            self.load_amap_html()

        self._set_coordinate_labels()
        self._init_robot_pose_sync()

    def _init_robot_pose_sync(self) -> None:
        self._last_robot_pose_sig = None
        self._pose_timer = QTimer(self)
        self._pose_timer.setInterval(500)
        self._pose_timer.timeout.connect(self._sync_robot_pose_overlay)
        try:
            self._ros_pose_bridge = RosPoseBridge()
        except Exception:
            self._ros_pose_bridge = None
            return
        if self._ros_pose_bridge.is_ready():
            self._pose_timer.start()

    def _sync_robot_pose_overlay(self) -> None:
        if not self._is_grid_mode():
            return
        bridge = self._ros_pose_bridge
        if bridge is None or not bridge.is_ready():
            return

        pose = bridge.latest_pose()
        if pose is None:
            return
        map_x, map_y, yaw_deg = pose
        sig = (round(map_x, 3), round(map_y, 3), round(yaw_deg, 1))
        if sig == self._last_robot_pose_sig:
            return
        self._last_robot_pose_sig = sig
        self.web_view.page().runJavaScript(
            f"if (typeof updateRobotPose === 'function') updateRobotPose({map_x:.3f}, {map_y:.3f}, {yaw_deg:.2f});"
        )

    def load_amap_html(self):
        """加载高德地图HTML页面 - 替换为你的高德Web API Key"""
        AMAP_KEY = "dcfef1b0386efcf3b898a1ca8c6b7a78"
        #AMAP_KEY = "972be3208e3a02cb10ca46c7116d20c3"
        html = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>高德地图</title>
            <style>
                html, body, #container {{ width: 100%; height: 100%; margin: 0; padding: 0; }}
            </style>
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            <script type="text/javascript" src="https://webapi.amap.com/maps?v=2.0&key={AMAP_KEY}"></script>
        </head>
        <body>
            <div id="container"></div>
            <script>
                // 初始化Python通信对象
                let pythonObj = null;
                let clickMarker = null;  // 全局单例标注（统一管理搜索/巡检点标注）
                let batchMarkers = new Map();   // 新增：批量标注映射表（独立管理，避免冲突）
                // 2. 巡检点标注映射表（PointId → Marker）
                let patrolMarkers = new Map();
                // 初始化通信
                new QWebChannel(qt.webChannelTransport, function(channel) {{
                    pythonObj = channel.objects.pythonObj;
                }});

                // 初始化地图
                var map = new AMap.Map('container', {{
                     zoom: 17,  // 缩放级别调16，校区显示更清晰（可选15/17）
                         center: [113.589038,22.347812] // 中山大学珠海校区精准坐标
                }});

                // 核心修改：点击地图→获取经纬度+显示同样式图标（单例，自动替换）
        map.on('click', function(e) {{
            var lng = e.lnglat.getLng().toFixed(6);
            var lat = e.lnglat.getLat().toFixed(6);
            var lnglat_str = lng + ", " + lat;
            // 1. 传递经纬度给Python
            pythonObj.receive_lnglat(lnglat_str);
            // 2. 移除旧的点击图标（确保仅显示一个）
            if (clickMarker) {{
                map.remove(clickMarker);
                clickMarker = null;
            }}
            // 3. 创建新的点击图标（同巡检点样式）
            clickMarker = new AMap.Marker({{
                position: e.lnglat,
                map: map
            }});
        }});

        // ========== 新增：接收Python传经纬度（Web服务解析后），定位并标注 ==========
        window.locateByLngLat = function(lng, lat, address) {{
            // 1. 移除旧标注（复用原有单例逻辑，和点击/巡检点标注统一）
            if (clickMarker) {{
                map.remove(clickMarker);
                clickMarker = null;
            }}
            // 2. 转换经纬度为数字类型，避免JS解析错误
            const lngNum = parseFloat(lng);
            const latNum = parseFloat(lat);
            // 3. 地图定位到该经纬度
            map.setCenter([lngNum, latNum]);
            map.setZoom(17);
            // 4. 创建标注（和原有点击标注样式一致）
            clickMarker = new AMap.Marker({{
                position: [lngNum, latNum],
                map: map,
                title: address || "搜索定位点"  // 鼠标悬停显示地址
            }});
        }};

        // 供Python调用：添加/更新巡检点标注（原有逻辑，完全不变）
        window.addPatrolMarker = function(pointId, lng, lat, name) {{
            if (patrolMarkers.has(pointId)) {{
                return;
            }}
            let marker = new AMap.Marker({{
                position: [lng, lat],
                map: map,
                title: name,
            }});
            patrolMarkers.set(pointId, marker);
        }};

        // 供Python调用：定位并高亮巡检点标注（UI选中时调用）（原有逻辑，完全不变）
        window.locatePatrolMarker = function(pointId, lng, lat, name) {{
            // 2. 移除旧的点击图标（确保仅显示一个）
            if (clickMarker) {{
                map.remove(clickMarker);
                clickMarker = null;
            }}

           clickMarker = new AMap.Marker({{
                position: [lng, lat],
                map: map,
                title: name,
            }});
            // 地图定位+缩放
            map.setCenter([lng, lat]);
            map.setZoom(17);
        }};

        // 供Python调用：移除单个巡检点标注（原有逻辑，完全不变）
        window.removePatrolMarker = function(pointId) {{
            if (patrolMarkers.has(pointId)) {{
                map.remove(patrolMarkers.get(pointId));
                patrolMarkers.delete(pointId);
            }}
        }};

        // 供Python调用：清空所有巡检点标注（原有逻辑，完全不变）
        window.clearAllPatrolMarkers = function() {{
            patrolMarkers.forEach(marker => map.remove(marker));
            patrolMarkers.clear();
        }};

        // 可选：清空表单时移除点击图标（按需添加）（原有逻辑，完全不变）
        window.clearClickMarker = function() {{
            if (clickMarker) {{
                map.remove(clickMarker);
                clickMarker = null;
            }}
        }};
        // ========== 新增：批量显示位置标注核心函数 ==========
        window.showBatchMarkers = function(positionList) {{
            // 1. 先清除旧的批量标注（避免重复）
            if (batchMarkers.size > 0) {{
                batchMarkers.forEach(marker => map.remove(marker));
                batchMarkers.clear();
            }}

             // 新增：创建marker数组，用于后续自动缩放
            let markerArray = [];
            
            // 2. 循环创建批量标注（positionList是经纬度列表）
            positionList.forEach((item, index) => {{
                // 解析每个位置的经纬度和名称
                const lng = parseFloat(item.lng);
                const lat = parseFloat(item.lat);
                const name = item.name || `批量标注${{index+1}}`;

                // 创建批量标注（用蓝色图标区分原有标注）
                const marker = new AMap.Marker({{
                    position: [lng, lat],
                    map: map
                }});

                // 存储批量标注（用index作为唯一标识）
                batchMarkers.set(`batch_${{index}}`, marker);
                // 新增：将marker加入数组
                markerArray.push(marker);
            }});

            // 3. 修复：自动缩放适配所有批量标注（核心修改）
            if (markerArray.length > 0) {{
                // 高德2.0正确用法：传递marker数组给setFitView
                map.setFitView(markerArray, {{
                    padding: [80, 80, 80, 80], // 边距（避免标注贴边）
                    duration: 800 // 缩放动画时长（毫秒），更流畅
                }});
            }} else {{
                console.warn("无有效批量标注，跳过自动缩放");
            }}
        }};

        // ========== 新增：清除批量标注（可选，方便用户操作） ==========
        window.clearBatchMarkers = function() {{
            batchMarkers.forEach(marker => map.remove(marker));
            batchMarkers.clear();
        }};
            </script>
        </body>
        </html>
        """
        self.web_view.setHtml(html, baseUrl=QUrl("https://webapi.amap.com/"))

    def on_map_point_selected(self, x, y):
        """地图选点成功 - 根据模式更新坐标"""
        if self._is_grid_mode():
            self.selected_map_x = float(x)
            self.selected_map_y = float(y)
            self.ui.txt_Longitude.setText(f"{self.selected_map_x:.3f}")
            self.ui.txt_Latitude.setText(f"{self.selected_map_y:.3f}")
        else:
            self.selected_lng = float(x)
            self.selected_lat = float(y)
            self.ui.txt_Longitude.setText(f"{self.selected_lng:.6f}")
            self.ui.txt_Latitude.setText(f"{self.selected_lat:.6f}")

        if hasattr(self, "txt_YawDeg") and not self.txt_YawDeg.text().strip():
            bridge = getattr(self, "_ros_pose_bridge", None)
            pose = bridge.latest_pose() if bridge is not None and bridge.is_ready() else None
            if pose is not None:
                self.selected_yaw_deg = self._normalize_yaw_deg(float(pose[2]))
                self.txt_YawDeg.setText(f"{self.selected_yaw_deg:.2f}".rstrip("0").rstrip("."))

    def on_map_pose_selected(self, x, y, yaw_deg):
        """地图拖拽朝向成功：同步点位与朝向"""
        self.on_map_point_selected(x, y)
        self.selected_yaw_deg = self._normalize_yaw_deg(float(yaw_deg))
        if hasattr(self, "txt_YawDeg"):
            self.txt_YawDeg.setText(f"{self.selected_yaw_deg:.2f}".rstrip("0").rstrip("."))

    def on_marker_click(self, point_id):
        """点击地图标记 - 自动选中右侧对应列表项"""
        for i in range(self.ui.tv_InspectPoint.count()):
            item = self.ui.tv_InspectPoint.item(i)
            if item.data(1)[0] == point_id:
                #self.ui.tv_InspectPoint.setCurrentItem(item)
                self.ui.txt_PointName.setText(item.data(1)[0])

                #self.on_select(item)
                break

    import requests
    from PyQt5.QtWidgets import QMessageBox

    # 在你的主窗口类中新增以下方法
    def call_amap_web_service(self, address):
        """调用高德Web服务API解析地址（地址→经纬度）"""
        AMAP_KEY = "972be3208e3a02cb10ca46c7116d20c3"  # 需开通地理编码服务
        url = "https://restapi.amap.com/v3/geocode/geo"
        params = {
            "key": AMAP_KEY,
            "address": address.strip(),
            "city": "全国"  # 适配你的地图中心（中山大学珠海校区），提升解析精度
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get("status") == "1" and len(result.get("geocodes", [])) > 0:
                geocode = result["geocodes"][0]
                lng, lat = geocode["location"].split(",")
                return True, lng, lat
            else:
                err_info = result.get("info", "地址解析失败")
                return False, err_info, ""
        except requests.exceptions.RequestException as e:
            return False, f"网络错误：{str(e)}", ""

    def on_search_address(self):
        """点击搜索按钮 - 仅在AMap模式下启用"""
        if self._is_grid_mode():
            QMessageBox.information(self, "提示", "当前是本地栅格地图模式，不支持地址搜索。")
            return

        address = self.ui.txt_MapAddress.text().strip()
        if not address:
            QMessageBox.warning(self, "提示", "请输入有效地址！")
            return

        success, res1, res2 = self.call_amap_web_service(address)
        if success:
            lng, lat = res1, res2
            self.ui.txt_Longitude.setText(lng)
            self.ui.txt_Latitude.setText(lat)
            self.web_view.page().runJavaScript(f"locateByLngLat('{lng}', '{lat}', '{address}')")
            QMessageBox.information(self, "成功", f"定位成功！\n{address}\n经纬度：{lng},{lat}")
        else:
            QMessageBox.warning(self, "失败", f"解析失败：{res1}")

    @pyqtSlot(str, str)
    def on_search_result(self, res_type, message):
        """接收JS返回的搜索结果（成功/失败）"""
        if res_type == "success":
            # 成功：显示提示
            QMessageBox.information(self, "成功", message)
            # 可选：将解析后的经纬度填充到表单（如果需要）
            # 示例：提取经纬度（message格式：定位成功：xxx，经纬度：116.xxx,39.xxx）
            import re
            lnglat_match = re.search(r'经纬度：([\d.]+),([\d.]+)', message)
            if lnglat_match:
                self.selected_lng = float(lnglat_match.group(1))
                self.selected_lat = float(lnglat_match.group(2))
                self.ui.txt_Longitude.setText(f"{self.selected_lng:.6f}")
                self.ui.txt_Latitude.setText(f"{self.selected_lat:.6f}")
                #self.lnglat_label.setText(f"坐标：{self.selected_lng:.6f}, {self.selected_lat:.6f}")
        else:
            # 失败：显示错误提示
            QMessageBox.warning(self, "失败", message)

    def on_show_batch_markers(self):
        area_id = self.ui.txt_AreaId.currentData()
        if area_id is None:
            QMessageBox.information(self, "提示", "当前没有可用的巡检区域。")
            return

        recordlist = self.db.fetch_all("SELECT * FROM InspectPoint WHERE AreaID=%s", (area_id,))

        if self._is_grid_mode():
            points = []
            for record in recordlist:
                x = record.get("MapX")
                y = record.get("MapY")
                if x is None or y is None:
                    continue
                points.append({"x": float(x), "y": float(y), "name": record.get("PointName", "")})
            payload = json.dumps(points, ensure_ascii=False)
            self.web_view.page().runJavaScript(
                f"if (typeof showMapMarkers === 'function') showMapMarkers({payload});"
            )
            return

        position_list = []
        for record in recordlist:
            lng = record.get("Longitude")
            lat = record.get("Latitude")
            if lng is None or lat is None:
                continue
            position_list.append({"lng": str(lng), "lat": str(lat), "name": record.get("PointName", "")})

        position_json = json.dumps(position_list, ensure_ascii=False)
        self.web_view.page().runJavaScript(f"showBatchMarkers({position_json})")

    def on_clear_batch_markers(self):
        """点击按钮：清除批量标注"""
        if self._is_grid_mode():
            self.web_view.page().runJavaScript("if (typeof clearMapMarkers === 'function') clearMapMarkers();")
            return
        self.web_view.page().runJavaScript("clearBatchMarkers()")

    def closeEvent(self, event):
        if self._pose_timer is not None:
            self._pose_timer.stop()
        super().closeEvent(event)


class RosPoseBridge:
    def __init__(self):
        self._ready = False
        self.error = ""
        self._latest_pose = None
        self._lock = threading.Lock()
        self._subscriber = None

        try:
            import rospy
            from geometry_msgs.msg import PoseWithCovarianceStamped

            self._rospy = rospy
            if not rospy.core.is_initialized():
                rospy.init_node("uav_point_pose_bridge", anonymous=True, disable_signals=True)
            self._subscriber = rospy.Subscriber(
                "/amcl_pose",
                PoseWithCovarianceStamped,
                self._on_amcl_pose,
                queue_size=1,
            )
            self._ready = True
        except Exception as exc:
            self.error = str(exc)

    def is_ready(self) -> bool:
        return self._ready

    def latest_pose(self):
        with self._lock:
            return self._latest_pose

    def _on_amcl_pose(self, msg):
        try:
            pose = msg.pose.pose
            x = float(pose.position.x)
            y = float(pose.position.y)
            q = pose.orientation
            yaw = math.atan2(
                2.0 * (q.w * q.z + q.x * q.y),
                1.0 - 2.0 * (q.y * q.y + q.z * q.z),
            )
            yaw_deg = float(yaw * 180.0 / math.pi)
            with self._lock:
                self._latest_pose = (x, y, yaw_deg)
        except Exception:
            pass
# ------------------------------ 以下代码完全不变（地图/通信/界面） ------------------------------
class MapCommunicator(QObject):
    point_selected = pyqtSignal(float, float)
    pose_selected = pyqtSignal(float, float, float)
    marker_clicked = pyqtSignal(int)
    searchresult = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()

    @pyqtSlot(str)
    def receive_lnglat(self, lnglat_str):
        parts = [x.strip() for x in lnglat_str.split(",")]
        if len(parts) < 2:
            return
        try:
            lng = float(parts[0])
            lat = float(parts[1])
        except Exception:
            return
        self.point_selected.emit(lng, lat)

    @pyqtSlot(float, float)
    def receive_map_xy(self, map_x, map_y):
        self.point_selected.emit(float(map_x), float(map_y))

    @pyqtSlot(float, float, float)
    def receive_map_pose(self, map_x, map_y, yaw_deg):
        self.pose_selected.emit(float(map_x), float(map_y), float(yaw_deg))

    @pyqtSlot(str)
    def on_map_click(self, lnglat_str):
        self.receive_lnglat(lnglat_str)

    @pyqtSlot(str)
    def on_marker_click(self, point_id_str):
        try:
            self.marker_clicked.emit(int(point_id_str))
        except Exception:
            pass

    @pyqtSlot(str, str)
    def search_result(self, res_type, message):
        self.searchresult.emit(res_type, message)


if __name__ == "__main__":
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    window = BLL_InspectPoint()
    window.show()
    sys.exit(app.exec())

