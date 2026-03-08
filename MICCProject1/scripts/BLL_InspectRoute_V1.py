import math
import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, QCoreApplication, Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QApplication, QDialog, QAbstractItemView, QTableWidgetItem, QMessageBox, QHeaderView, \
    QWidget, QHBoxLayout, QLabel, QFrame, QGraphicsOpacityEffect, QStyle
from qfluentwidgets import TransparentToolButton, FluentIcon as FIF, PushButton
from MICCProject1.ui.Frm_InspectRoute import Ui_Frm_InspectRoute  # 导入自动生成的界面类
from MICCProject1.scripts.DBHelper import DBHelper


class BLL_InspectRoute(QDialog):
    def __init__(self, registration_mode: bool = False, on_prev=None, on_close=None, on_jump=None):
        super().__init__()
        self.ui = Ui_Frm_InspectRoute()
        self.ui.setupUi(self)
        self.db = DBHelper()
        self._on_prev = on_prev
        self._on_close = on_close
        self._on_jump = on_jump
        self._active_step = 2
        self.routeid = None
        self.init_ui()
        self.load_inspectroute() #加载巡检点位
        self.load_inspectarea() # 加载巡检区域
        self._init_nav()
        #self.setFixedSize(1639, 636)

    def _init_nav(self) -> None:
        self._nav_bar = QWidget(self)
        self._nav_bar.setObjectName("navBar")
        self._nav_bar.setFixedHeight(36)
        layout = QHBoxLayout(self._nav_bar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self._step_bar = self._build_step_bar(active_index=2)
        self._btn_prev = TransparentToolButton(FIF.LEFT_ARROW)
        self._btn_done = TransparentToolButton(FIF.ACCEPT)
        self._btn_close = TransparentToolButton(FIF.CLOSE)
        self._btn_prev.setToolTip("上一步")
        self._btn_done.setToolTip("完成")
        self._btn_close.setToolTip("关闭")
        for btn in (self._btn_prev, self._btn_done, self._btn_close):
            btn.setFixedSize(28, 28)
            btn.setIconSize(btn.iconSize())
        self._btn_prev.clicked.connect(self._on_nav_prev)
        self._btn_done.clicked.connect(self._on_nav_done)
        self._btn_close.clicked.connect(self._on_nav_close)

        layout.addWidget(self._step_bar, 1)
        layout.addWidget(self._btn_prev)
        layout.addWidget(self._btn_done)
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

    def _reposition_nav(self) -> None:
        if self._dock_nav_bar():
            return
        w = self.width()
        title_h = self.style().pixelMetric(QStyle.PM_TitleBarHeight, None, self)
        self._nav_bar.adjustSize()
        self._nav_bar.move(w - self._nav_bar.width() - 12, max(8, title_h + 8))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_nav_bar"):
            self._reposition_nav()

    def _on_nav_prev(self) -> None:
        if callable(self._on_prev):
            self.close()
            self._on_prev()

    def _on_nav_done(self) -> None:
        if callable(self._on_close):
            self._on_close()
        else:
            self.close()

    def _on_nav_close(self) -> None:
        if callable(self._on_close):
            self._on_close()
        else:
            self.close()

    def init_ui(self) -> None:
        self._apply_window_icon()
        self._apply_form_style()
        self._replace_top_controls()
        self._tune_form_geometry()
        self.ui.btn_Save.clicked.connect(self.on_save)
        self.ui.btn_Clear.clicked.connect(self.on_clear)
        self.ui.btn_Delete.clicked.connect(self.on_delete)
        self.ui.btn_Enable.clicked.connect(self.on_enable)
        self.ui.btn_Disable.clicked.connect(self.on_disable)
        self.ui.tv_InspectRoute.clicked.connect(self.on_select)
        self.ui.btn_Add.clicked.connect(self.add_point_to_route)
        self.ui.btn_Remove.clicked.connect(self.remove_point_from_route)
        self.ui.btn_Up.clicked.connect(self.adjust_sort_up)
        self.ui.btn_Down.clicked.connect(self.adjust_sort_down)
        self.ui.btn_SaveRelation.clicked.connect(self.save_relation)
        self.ui.txt_PlanType.addItems(["自动规划","手动规划"])
        self.ui.txt_PlanType.setCurrentIndex(0)  # 默认选中第一个选项
        self.ui.txt_PathLength.setDecimals(2)  # 显示2位小数
        self.ui.txt_InsDuration.setDecimals(2)  # 显示2位小数

    def load_inspectroute(self) -> None:
        self.ui.tv_InspectRoute.setRowCount(0)
        recordlist = self.db.fetch_all("select *, ia.AreaName from InspectArea ia, InspectRoute ir where ir.AreaID = ia.AreaID")
        for row, record in enumerate(recordlist):
            self.ui.tv_InspectRoute.insertRow(row)
            self.ui.tv_InspectRoute.setItem(row, 0, QTableWidgetItem(str(record.get("RouteId", ""))))  # 巡检点位ID
            self.ui.tv_InspectRoute.setItem(row, 1, QTableWidgetItem(str(record.get("AreaName", ""))))  #点位名称
            self.ui.tv_InspectRoute.setItem(row, 2, QTableWidgetItem(str(record.get("RouteName", ""))))   #区域名称
            self.ui.tv_InspectRoute.setItem(row, 3,  QTableWidgetItem(str(record.get("PointCount",""))))  #经度
            self.ui.tv_InspectRoute.setItem(row, 4, QTableWidgetItem(str(record.get("PathLength",""))))  #纬度
            self.ui.tv_InspectRoute.setItem(row, 5, QTableWidgetItem("启用" if record.get("Status") == 1 else "禁用" )) #状态

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

    def validate_required(self) -> bool:
        # 定义必填字段（控件变量 -> 字段名称）
        required = {
            self.ui.txt_RouteName: "路线名称",
            self.ui.txt_RouteCode: "路线编码"
        }
        for var, field_name in required.items():
            if not var.text().strip():
                self.ui.lab_Note.setText(f"{field_name}为必填项，请填写完整！")
                self.ui.lab_Note.setStyleSheet("color: red;")
                return False
        return True

    def _apply_form_style(self) -> None:
        self.setStyleSheet(
            "QDialog {"
            "background: #f7f9fc;"
            "}"
            "QGroupBox {"
            "font: 600 12px 'Microsoft YaHei';"
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
            "font: 12px 'Microsoft YaHei';"
            "color: #2f3a4a;"
            "}"
            "QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {"
            "font: 12px 'Microsoft YaHei';"
            "padding: 6px 8px;"
            "border: 1px solid #cfd7e3;"
            "border-radius: 6px;"
            "background: #ffffff;"
            "}"
            "QPushButton {"
            "font: 12px 'Microsoft YaHei';"
            "padding: 6px 14px;"
            "border-radius: 6px;"
            "border: 1px solid #cfd7e3;"
            "background: #ffffff;"
            "}"
            "QPushButton:hover {"
            "background: #eef4ff;"
            "border-color: #9bbcff;"
            "}"
            "QTableWidget {"
            "font: 12px 'Microsoft YaHei';"
            "gridline-color: #d0d7e2;"
            "background: #ffffff;"
            "}"
            "QHeaderView::section {"
            "font: 12px 'Microsoft YaHei';"
            "background: #f0f4fa;"
            "padding: 6px;"
            "border: 1px solid #dbe3ef;"
            "}"
        )
        for name in ("btn_Save", "btn_Clear", "btn_Delete", "btn_Enable", "btn_Disable"):
            btn = getattr(self.ui, name, None)
            if btn:
                btn.setMinimumWidth(90)

    def _tune_form_geometry(self) -> None:
        for name in (
            "txt_AreaId",
            "txt_RouteName",
            "txt_RouteCode",
            "txt_PlanType",
            "txt_PointCount",
            "txt_PathLength",
            "txt_InsDuration",
        ):
            widget = getattr(self.ui, name, None)
            if widget:
                widget.setFixedHeight(24)

        if hasattr(self.ui, "txt_Remark"):
            self.ui.txt_Remark.setFixedHeight(60)

        for name in ("label_11", "label_12"):
            label = getattr(self.ui, name, None)
            if label:
                label.setFixedHeight(20)

    def _dock_nav_bar(self) -> bool:
        host = getattr(self.ui, "groupBox_2", None)
        table = getattr(self.ui, "tv_InspectRoute", None)
        if host is None or table is None:
            return False

        if not hasattr(self, "_table_base_rect"):
            self._table_base_rect = table.geometry()

        row_widgets = []
        for name in ("btn_Delete", "btn_Enable", "btn_Disable"):
            btn = getattr(self.ui, name, None)
            if btn is not None:
                row_widgets.append(btn)

        nav = self._nav_bar
        nav.setParent(host)
        nav.adjustSize()

        nav_y = 6
        nav_x = 8
        if row_widgets:
            left = min(w.geometry().x() for w in row_widgets)
            right = max(w.geometry().x() + w.geometry().width() for w in row_widgets)
            top = min(w.geometry().y() for w in row_widgets)
            height = max(w.geometry().height() for w in row_widgets)
            nav_y = top + height + 4

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
        host = getattr(self.ui, "groupBox_2", None)
        if host is None:
            return

        def _swap_button(name: str, text: str) -> PushButton | None:
            old = getattr(self.ui, name, None)
            if old is None:
                return None
            rect = old.geometry()
            old.hide()
            btn = PushButton(text, host)
            btn.setGeometry(rect)
            btn.setFixedHeight(rect.height())
            btn.setMinimumWidth(rect.width())
            setattr(self.ui, name, btn)
            return btn

        _swap_button("btn_Delete", "删除")
        _swap_button("btn_Enable", "启用")
        _swap_button("btn_Disable", "禁用")

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
        else:
            areaId = self.ui.txt_AreaId.currentData()
            routeName = self.ui.txt_RouteName.text().strip()
            routeCode = self.ui.txt_RouteCode.text().strip()
            planType = self.ui.txt_PlanType.currentIndex()
            pointCount = self.ui.txt_PointCount.value()
            pathLength = self.ui.txt_PathLength.value()
            insDuration = self.ui.txt_InsDuration.value()
            remark = self.ui.txt_Remark.text().strip()

            try:
                # 新增
                if not self.routeid:
                    # 校验路线编码唯一性
                    check_sql = "SELECT * FROM InspectRoute WHERE RouteCode=%s"
                    if self.db.execute_query(check_sql, (routeCode,)):
                        QMessageBox.warning(self, "提示", "路线编码已存在！")
                        return
                    # 插入数据
                    query = """
                                INSERT INTO InspectRoute (AreaId, RouteName, RouteCode, PlanType, Status, PointCount, PathLength, InsDuration,Remark)
                                VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s)
                                """
                    params = (areaId, routeName, routeCode, planType, pointCount, pathLength,insDuration, remark)
                    i = self.db.execute_query(query, params)
                    if (i > 0):
                        self.ui.lab_Note.setText("巡检路线添加成功！")
                        self.clear_input()
                        self.load_inspectroute()
                    else:
                        self.ui.lab_Note.setText("巡检路线添加失败！")
                else:
                    query = """
                    UPDATE InspectRoute
                    SET AreaId = %s, RouteName = %s, RouteCode = %s, PlanType=%s, PointCount=%s, PathLength=%s, InsDuration=%s,  Remark = %s
                    WHERE RouteId = %s
                    """
                    params = (areaId, routeName, routeCode, planType, pointCount, pathLength,insDuration, remark,  self.routeid)
                    i = self.db.execute_query(query, params)
                    if (i>0):
                        self.ui.lab_Note.setText("巡检路线修改成功！")
                        self.clear_input()
                        self.load_inspectroute()
                    else:
                        self.ui.lab_Note.setText("巡检路线修改失败！" )
            except Exception as exc:
                self.ui.lab_Note.setText("巡检路线保存失败！"+str(exc))
                return

    # 选中某一项巡检点位数据
    def on_select(self, index) -> None:
        row = index.row() if hasattr(index, 'row') else int(index)
        ins_item = self.ui.tv_InspectRoute.item(row, 0)
        if ins_item is None:
            return
        self.routeid = int(ins_item.text())
        recordlist = self.db.fetch_all("SELECT * FROM InspectRoute WHERE RouteId = %s", (self.routeid,))
        if not recordlist:
            return
        record = recordlist[0]
        # 所属机构：匹配时直接通过userData查找
        for i in range(self.ui.txt_AreaId.count()):
            if self.ui.txt_AreaId.itemData(i) == record.get("AreaID", ""):
                self.ui.txt_AreaId.setCurrentIndex(i)
                break

        self.ui.txt_RouteName.setText(record.get("RouteName", ""))
        self.ui.txt_RouteCode.setText(record.get("RouteCode", ""))
        self.ui.txt_PlanType.setCurrentIndex(record.get("PlanType", 0))
        self.ui.txt_PointCount.setValue(record.get("PointCount", 0))
        path_length = record.get("PathLength")
        self.ui.txt_PathLength.setValue(float(path_length) if path_length else 0.0)
        ins_duration = record.get("InsDuration")
        self.ui.txt_InsDuration.setValue(float(ins_duration) if ins_duration else 0.0)
        self.ui.txt_Remark.setText(record.get("Remark", ""))
        self.ui.gbox_status.setTitle("修改巡检路线")
        self.ui.lab_Note.clear()
        if hasattr(self.ui, "lab_selectedArea"):
            area_item = self.ui.tv_InspectRoute.item(row, 1)
            if area_item is not None:
                self.ui.lab_selectedArea.setText(area_item.text())
        if hasattr(self.ui, "lab_selectedRoute"):
            self.ui.lab_selectedRoute.setText(record.get("RouteName", ""))
        self.load_inspectPointByAreaId(record.get("AreaId", record.get("AreaID", None)))
        self.load_inspectPointByRouteId(self.routeid)

    # 删除巡检点位
    def on_delete(self) -> None:
        selection = self.ui.tv_InspectRoute.selectedItems()
        if not selection:
            QMessageBox.warning(self, "操作提示", "请先选中要删除的巡检路线！")
            return

        reply = QMessageBox.question(self, "确认删除", "确定要删除选中的巡检路线吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        else:
            ins_item = self.ui.tv_InspectRoute.item(self.ui.tv_InspectRoute.currentRow(), 0)
            if ins_item is None:
                return
            self.routeid = int(ins_item.text())
            self.db.execute_query("DELETE FROM InspectRoutePoint WHERE RouteId = %s", (self.routeid,))
            i = self.db.execute_query("DELETE FROM InspectRoute WHERE RouteId = %s", (self.routeid,))
            if (i>0):
                self.ui.lab_Note.setText("巡检路线删除成功！")
                self.clear_input()
                self.load_inspectroute()
            else:
                self.ui.lab_Note.setText("巡检路线删除失败！")

    # 启用巡检点位
    def on_enable(self) -> None:
        selection = self.ui.tv_InspectRoute.selectedItems()
        if not selection:
            QMessageBox.warning(self, "操作提示", "请先选中要启用的巡检路线！")
            return
        else:
            ins_item = self.ui.tv_InspectRoute.item(self.ui.tv_InspectRoute.currentRow(), 0)
            if ins_item is None:
                return
            self.routeid = int(ins_item.text())
            i = self.db.execute_query("UPDATE InspectRoute SET Status = 1 WHERE RouteId = %s", (self.routeid,))
            if (i > 0):
                self.ui.lab_Note.setText("巡检路线已启用！")
                self.clear_input()
                self.load_inspectroute()
            else:
                self.ui.lab_Note.setText("巡检路线启用失败！")

    # 禁用巡检点位
    def on_disable(self) -> None:
        selection = self.ui.tv_InspectRoute.selectedItems()
        if not selection:
            QMessageBox.warning(self, "操作提示", "请先选中要禁用的巡检点位！")
            return
        else:
            ins_item = self.ui.tv_InspectRoute.item(self.ui.tv_InspectRoute.currentRow(), 0)
            if ins_item is None:
                return
            self.routeid = int(ins_item.text())
            i = self.db.execute_query("UPDATE InspectRoute SET Status = 0 WHERE RouteId = %s", (self.routeid,))
            if (i > 0):
                self.ui.lab_Note.setText("巡检路线已禁用！")
                self.clear_input()
                self.load_inspectroute()
            else:
                self.ui.lab_Note.setText("巡检路线禁用失败！")

    #清空输入框和提示
    def on_clear(self):
        self.clear_input()
        self.ui.lab_Note.text()

    """清空输入框"""
    def clear_input(self) -> None:
        self.ui.txt_RouteName.clear()
        self.ui.txt_RouteCode.clear()
        self.ui.txt_PointCount.setValue(0)
        self.ui.txt_PathLength.setValue(0.0)
        self.ui.txt_InsDuration.setValue(0.0)
        self.ui.txt_Remark.clear()
        self.ui.gbox_status.setTitle("新增巡检路线")
        self.routeid = None


    def load_inspectPointByAreaId(self, areaid) -> None:
        table = getattr(self.ui, "tv_InspectPoint1", None)
        if table is None:
            return
        table.setRowCount(0)
        if areaid is None:
            return

        recordlist = self.db.fetch_all(
            "SELECT PointId, PointName, Longitude, Latitude FROM InspectPoint WHERE AreaId=%s AND Status=1",
            (areaid,),
        )
        table.setColumnCount(3)
        for row, record in enumerate(recordlist):
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(str(record.get("PointId", ""))))
            table.setItem(row, 1, QTableWidgetItem(str(record.get("PointName", ""))))
            lng_lat = f"{record.get('Longitude', '')},{record.get('Latitude', '')}"
            table.setItem(row, 2, QTableWidgetItem(lng_lat))

    def load_inspectPointByRouteId(self, route_id) -> None:
        table = getattr(self.ui, "tv_InspectPoint2", None)
        if table is None:
            return
        table.setRowCount(0)
        if route_id is None:
            return

        recordlist = self.db.fetch_all(
            """
            SELECT ip.PointId, ip.PointName, ip.Longitude, ip.Latitude,
                   rp.StayTime, rp.InspectAngle, rp.SortNo
            FROM InspectRoutePoint rp
            JOIN InspectPoint ip ON rp.PointId = ip.PointId
            WHERE rp.RouteId = %s
            ORDER BY rp.SortNo
            """,
            (route_id,),
        )
        table.setColumnCount(6)
        for row, record in enumerate(recordlist):
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(str(record.get("PointId", ""))))
            table.setItem(row, 1, QTableWidgetItem(str(record.get("PointName", ""))))
            lng_lat = f"{record.get('Longitude', '')},{record.get('Latitude', '')}"
            table.setItem(row, 2, QTableWidgetItem(lng_lat))
            table.setItem(row, 3, QTableWidgetItem(str(record.get("StayTime", 10))))
            table.setItem(row, 4, QTableWidgetItem(str(record.get("InspectAngle", 0))))
            table.setItem(row, 5, QTableWidgetItem(str(record.get("SortNo", row + 1))))

    def add_point_to_route(self) -> None:
        if not self.routeid:
            QMessageBox.warning(self, "提示", "请先选择路线")
            return
        selected_row = self.ui.tv_InspectPoint1.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "提示", "请选择要添加的点位")
            return

        point_id = self.ui.tv_InspectPoint1.item(selected_row, 0).text()
        exists = self.db.fetch_all(
            "SELECT 1 FROM InspectRoutePoint WHERE RouteId=%s AND PointId=%s",
            (self.routeid, point_id),
        )
        if exists:
            QMessageBox.warning(self, "提示", "该点位已在路线中")
            return

        max_sort = self.db.fetch_all(
            "SELECT IFNULL(MAX(SortNo), 0) AS max_sort FROM InspectRoutePoint WHERE RouteId=%s",
            (self.routeid,),
        )
        sort_no = int(max_sort[0].get("max_sort", 0)) + 1
        self.db.execute_query(
            "INSERT INTO InspectRoutePoint (RouteId, PointId, SortNo, StayTime, InspectAngle) VALUES (%s, %s, %s, 10, 0)",
            (self.routeid, point_id, sort_no),
        )
        self.load_inspectPointByRouteId(self.routeid)

    def adjust_sort_up(self) -> None:
        self.adjust_sort(-1)

    def adjust_sort_down(self) -> None:
        self.adjust_sort(1)

    def adjust_sort(self, step: int) -> None:
        if not self.routeid:
            return
        selected_row = self.ui.tv_InspectPoint2.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "提示", "请选择要调整顺序的点位")
            return

        target_row = selected_row + step
        if target_row < 0 or target_row >= self.ui.tv_InspectPoint2.rowCount():
            return

        curr_point_id = self.ui.tv_InspectPoint2.item(selected_row, 0).text()
        curr_sort = int(self.ui.tv_InspectPoint2.item(selected_row, 5).text())
        target_point_id = self.ui.tv_InspectPoint2.item(target_row, 0).text()
        target_sort = int(self.ui.tv_InspectPoint2.item(target_row, 5).text())

        self.db.execute_query(
            "UPDATE InspectRoutePoint SET SortNo=%s WHERE RouteId=%s AND PointId=%s",
            (target_sort, self.routeid, curr_point_id),
        )
        self.db.execute_query(
            "UPDATE InspectRoutePoint SET SortNo=%s WHERE RouteId=%s AND PointId=%s",
            (curr_sort, self.routeid, target_point_id),
        )
        self.load_inspectPointByRouteId(self.routeid)

    def remove_point_from_route(self) -> None:
        if not self.routeid:
            return
        selected_row = self.ui.tv_InspectPoint2.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "提示", "请选择要移除的点位")
            return

        point_id = self.ui.tv_InspectPoint2.item(selected_row, 0).text()
        ok = QMessageBox.question(
            self, "确认", "确认移除该点位吗？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return

        self.db.execute_query(
            "DELETE FROM InspectRoutePoint WHERE RouteId=%s AND PointId=%s",
            (self.routeid, point_id),
        )
        rows = self.db.fetch_all(
            "SELECT PointId FROM InspectRoutePoint WHERE RouteId=%s ORDER BY SortNo",
            (self.routeid,),
        )
        for idx, row in enumerate(rows, start=1):
            self.db.execute_query(
                "UPDATE InspectRoutePoint SET SortNo=%s WHERE RouteId=%s AND PointId=%s",
                (idx, self.routeid, row["PointId"]),
            )
        self.load_inspectPointByRouteId(self.routeid)

    def save_relation(self) -> None:
        if not self.routeid:
            QMessageBox.warning(self, "提示", "请先选择路线")
            return

        for row in range(self.ui.tv_InspectPoint2.rowCount()):
            point_id = self.ui.tv_InspectPoint2.item(row, 0).text()
            stay_text = self.ui.tv_InspectPoint2.item(row, 3).text() or "0"
            angle_text = self.ui.tv_InspectPoint2.item(row, 4).text() or "0"
            try:
                stay_time = int(float(stay_text))
                inspect_angle = int(float(angle_text))
            except ValueError:
                QMessageBox.warning(self, "提示", f"第 {row + 1} 行停留时间或角度格式错误")
                return

            self.db.execute_query(
                "UPDATE InspectRoutePoint SET StayTime=%s, InspectAngle=%s WHERE RouteId=%s AND PointId=%s",
                (stay_time, inspect_angle, self.routeid, point_id),
            )

        point_count, path_length, ins_duration = self.calculate_route_metrics(self.routeid)
        self.ui.txt_PointCount.setValue(point_count)
        self.ui.txt_PathLength.setValue(path_length)
        self.ui.txt_InsDuration.setValue(ins_duration)
        self.load_inspectroute()
        QMessageBox.information(self, "完成", "路线点位关系已保存")

    def calculate_distance(self, lng1, lat1, lng2, lat2) -> float:
        radius = 6371000
        lng1_rad = math.radians(float(lng1))
        lat1_rad = math.radians(float(lat1))
        lng2_rad = math.radians(float(lng2))
        lat2_rad = math.radians(float(lat2))

        dlng = lng2_rad - lng1_rad
        dlat = lat2_rad - lat1_rad
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius * c

    def calculate_route_metrics(self, route_id: int):
        rows = self.db.fetch_all(
            """
            SELECT rp.PointId, rp.SortNo, rp.StayTime, ip.Longitude, ip.Latitude
            FROM InspectRoutePoint rp
            LEFT JOIN InspectPoint ip ON rp.PointId = ip.PointId
            WHERE rp.RouteId = %s
            ORDER BY rp.SortNo ASC
            """,
            (route_id,),
        )
        point_count = len(rows)

        path_length = 0.0
        for i in range(max(0, point_count - 1)):
            p1 = rows[i]
            p2 = rows[i + 1]
            if p1.get("Longitude") is None or p1.get("Latitude") is None:
                continue
            if p2.get("Longitude") is None or p2.get("Latitude") is None:
                continue
            path_length += self.calculate_distance(p1["Longitude"], p1["Latitude"], p2["Longitude"], p2["Latitude"])

        stay_total = sum(int(r.get("StayTime") or 0) for r in rows)
        move_time = path_length / 0.5 if path_length > 0 else 0
        ins_duration = stay_total + move_time

        self.db.execute_query(
            "UPDATE InspectRoute SET PointCount=%s, PathLength=%s, InsDuration=%s WHERE RouteId=%s",
            (point_count, round(path_length, 2), round(ins_duration, 2), route_id),
        )
        return point_count, round(path_length, 2), round(ins_duration, 2)


if __name__ == "__main__":
    # 运行应用
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    window = BLL_InspectRoute()
    window.show()
    sys.exit(app.exec())

