import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from PyQt6.QtCore import QObject, pyqtSlot, QUrl, pyqtSignal
from PyQt6.QtWidgets import QApplication, QDialog, QAbstractItemView, QTableWidgetItem, QMessageBox, QHeaderView, \
    QMainWindow, QSizePolicy, QVBoxLayout, QSplitter, QWidget, QHBoxLayout, QWidget
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from ui.Frm_InspectMag import Ui_Frm_InspectMag  # 导入自动生成的界面类
from BLL_InspectArea import BLL_InspectArea
from BLL_InspectPoint_V4 import BLL_InspectPoint
from BLL_InspectRoute_V2 import BLL_InspectRoute
from DBHelper import DBHelper
import math
import json


class BLL_InspectMag(QMainWindow):
    def __init__(self, registration_mode: bool = False):
        super().__init__()
        self.ui = Ui_Frm_InspectMag()
        self.ui.setupUi(self)
        self.init_ui()
        self.db = DBHelper()
        self.load_inspectarea()

    def init_ui(self) -> None:
        self.ui.btn_InspectArea.clicked.connect(self.on_btn_InspectArea_click)
        self.ui.btn_InspectPoint.clicked.connect(self.on_btn_InspectPoint_click)
        self.ui.btn_InspectPoint.clicked.connect(self.on_btn_InspectRoute_click)

    # 巡检区域管理
    def on_btn_InspectArea_click(self):
        self.bll_inspectArea = BLL_InspectArea ()
        self.bll_inspectArea.exec()

    # 巡检点位管理
    def on_btn_InspectPoint_click(self):
        self.bll_inspectPoint = BLL_InspectPoint()
        self.bll_inspectPoint.exec()

    # 巡检区域管理
    def on_btn_InspectRoute_click(self):
        self.bll_inspectRoute = BLL_InspectRoute()
        self.bll_inspectRoute.exec()


    def load_inspectarea(self):
        self.ui.txt_InspectArea.clear()
        recordlist = self.db.fetch_all("SELECT AreaId, AreaName FROM InspectArea ORDER BY AreaId")
        if not recordlist:
            self.ui.txt_InspectArea.addItem("暂无巡检区域")
            return
        for record in recordlist:
            areaid = record['AreaId']  # 通过键'AreaID'取对应值
            areaname = record['AreaName']  # 通过键'AreaName'取对应值
            self.ui.txt_InspectArea.addItem(areaname,userData=areaid)
        self.load_inspectrouteByAreaId(recordlist[0]['AreaId'])

    def load_inspectrouteByAreaId(self, areaid) -> None:
        self.ui.txt_InspectRoute.clear()
        recordlist = self.db.fetch_all("SELECT RouteId, RouteName FROM InspectRoute where AreaId ="+ str(areaid) + " ORDER BY RouteId")
        if not recordlist:
            self.ui.txt_InspectRoute.addItem("暂无巡检路线")
            return
        for record in recordlist:
            routeId = record['RouteId']  # 通过键'RouteId'取对应值
            routeName = record['RouteName']  # 通过键'RouteName'取对应值
            self.ui.txt_InspectRoute.addItem(routeName,userData=routeId)

if __name__ == "__main__":
    # 运行应用
    app = QApplication(sys.argv)
    window = BLL_InspectMag()
    window.show()
    sys.exit(app.exec())