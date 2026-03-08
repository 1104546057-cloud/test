import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QApplication, QMainWindow
from qfluentwidgets import PushButton

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from MICCProject1.scripts.BLL_InspectArea import BLL_InspectArea
from MICCProject1.scripts.BLL_InspectPoint_V4 import BLL_InspectPoint
from MICCProject1.scripts.BLL_InspectRoute_V1 import BLL_InspectRoute
from MICCProject1.scripts.DBHelper import DBHelper
from MICCProject1.ui.Frm_InspectMag import Ui_Frm_InspectMag


class BLL_InspectMag(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_Frm_InspectMag()
        self.ui.setupUi(self)
        self.db = DBHelper()

        self._inspect_area = None
        self._inspect_point = None
        self._inspect_route = None

        self._apply_window_icon()
        self._replace_buttons()
        self._bind_actions()
        self.load_inspectarea()

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

    def _bind_actions(self) -> None:
        self.ui.btn_InspectArea.clicked.connect(self.on_btn_InspectArea_click)
        self.ui.btn_InspectPoint.clicked.connect(self.on_btn_InspectPoint_click)
        self.ui.btn_InspectRoute.clicked.connect(self.on_btn_InspectRoute_click)
        self.ui.txt_InspectArea.currentIndexChanged.connect(self._on_area_changed)

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
            return

        for row in records:
            self.ui.txt_InspectArea.addItem(row["AreaName"], userData=row["AreaId"])

        self._on_area_changed(0)

    def _on_area_changed(self, _idx: int):
        area_id = self.ui.txt_InspectArea.currentData()
        self.ui.txt_InspectRoute.clear()
        if area_id is None:
            self.ui.txt_InspectRoute.addItem("暂无巡检路线", userData=None)
            return

        routes = self.db.fetch_all(
            "SELECT RouteId, RouteName FROM InspectRoute WHERE AreaId=%s ORDER BY RouteId",
            (area_id,),
        )
        if not routes:
            self.ui.txt_InspectRoute.addItem("暂无巡检路线", userData=None)
            return

        for row in routes:
            self.ui.txt_InspectRoute.addItem(row["RouteName"], userData=row["RouteId"])


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = BLL_InspectMag()
    win.show()
    sys.exit(app.exec_())
