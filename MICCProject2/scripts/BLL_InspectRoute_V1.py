import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from PyQt6.QtWidgets import QApplication, QDialog, QAbstractItemView, QTableWidgetItem, QMessageBox, QHeaderView
from  ui.Frm_InspectRoute import Ui_Frm_InspectRoute  # 导入自动生成的界面类
from DBHelper import DBHelper
import math

class BLL_InspectRoute(QDialog):
    def __init__(self, registration_mode: bool = False):
        super().__init__()
        self.ui = Ui_Frm_InspectRoute()
        self.ui.setupUi(self)
        self.db = DBHelper()
        self.route_id = None
        self.init_ui()
        self.load_inspectroute() #加载巡检点位
        self.load_inspectarea() # 加载巡检区域
        #self.setFixedSize(1639, 636)

    def init_ui(self) -> None:
        self.ui.btn_Save.clicked.connect(self.on_save)
        self.ui.btn_Clear.clicked.connect(self.on_clear)
        self.ui.btn_Delete.clicked.connect(self.on_delete)
        self.ui.btn_Enable.clicked.connect(self.on_enable)
        self.ui.btn_Disable.clicked.connect(self.on_disable)
        self.ui.tv_InspectRoute.clicked.connect(self.on_select)
        self.ui.btn_Add.clicked.connect(self.add_point_to_route)
        self.ui.btn_Up.clicked.connect(self.adjust_sort_up)
        self.ui.btn_Down.clicked.connect(self.adjust_sort_down)
        self.ui.btn_Remove.clicked.connect(self.remove_point_from_route)
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
                if not self.route_id:
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
                    params = (areaId, routeName, routeCode, planType, pointCount, pathLength,insDuration, remark,  self.route_id)
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
        ins_item = self.ui.tv_InspectRoute.item(index.row(), 0)
        self.ui.lab_selectedArea.setText(self.ui.tv_InspectRoute.item(index.row(), 1).text())
        if ins_item is None:
            return
        self.route_id = int(ins_item.text())
        recordlist = self.db.fetch_all("SELECT * FROM InspectRoute WHERE RouteId = %s", (self.route_id,))
        if not recordlist:
            return
        record = recordlist[0]
        # 所属区域
        for index in range(self.ui.txt_AreaId.count()):
            if self.ui.txt_AreaId.itemData(index) == record.get("AreaId", ""):
                self.ui.txt_AreaId.setCurrentIndex(index)
                break

        # 根据AreaID加载当前区域的点位信息
        self.load_inspectPointByAreaId(record.get("AreaId"))
        self.load_inspectPointByRouteId(record.get("RouteId"))
        self.ui.lab_selectedRoute.setText(record.get("RouteName"))


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



    # 删除巡检点位
    def on_delete(self) -> None:
        selection = self.ui.tv_InspectRoute.selectedItems()
        if not selection:
            QMessageBox.warning(self, "操作提示", "请先选中要删除的巡检路线！")
            return

        reply = QMessageBox.question(self, "确认删除", "确定要删除选中的巡检路线吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        else:
            ins_item = self.ui.tv_InspectRoute.item(self.ui.tv_InspectRoute.currentRow(), 0)
            if ins_item is None:
                return
            self.route_id = int(ins_item.text())
            i = self.db.execute_query("DELETE FROM InspectRoute WHERE RouteId = %s", (self.route_id,))
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
            self.route_id = int(ins_item.text())
            i = self.db.execute_query("UPDATE InspectRoute SET Status = 1 WHERE RouteId = %s", (self.route_id,))
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
            self.route_id = int(ins_item.text())
            i = self.db.execute_query("UPDATE InspectRoute SET Status = 0 WHERE RouteId = %s", (self.route_id,))
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
        self.route_id = None

    #根据区域ID加载当前区域内的所有可用巡检点到列表1中
    def load_inspectPointByAreaId(self, areaid) -> None:
        if areaid is not None:
            self.ui.tv_InspectPoint1.setRowCount(0)
            recordlist = self.db.fetch_all("select * from  InspectPoint where AreaId =" + str(areaid) + " and Status =1")
            for row, record in enumerate(recordlist):
                self.ui.tv_InspectPoint1.insertRow(row)
                self.ui.tv_InspectPoint1.setItem(row, 0, QTableWidgetItem(str(record.get("PointId", ""))))  # 巡检点位ID
                self.ui.tv_InspectPoint1.setItem(row, 1, QTableWidgetItem(str(record.get("PointName", ""))))  #点位名称
                self.ui.tv_InspectPoint1.setItem(row, 2,  QTableWidgetItem(str(record.get("Longitude"))+","+str(record.get("Latitude"))))  #经度

    # 根据路线ID加载当前路线内的所有可用巡检点到列表2中
    def load_inspectPointByRouteId(self, route_id) -> None:
        if route_id is not None:
            self.ui.tv_InspectPoint2.setRowCount(0)
            recordlist = self.db.fetch_all("select ip.*, rp.SortNo, rp.StayTime,rp.InspectAngle from  InspectRoutePoint rp, InspectPoint ip where rp.PointId = ip.PointId and rp.RouteId =" + str(route_id) + " order by SortNo")
            for row, record in enumerate(recordlist):
                self.ui.tv_InspectPoint2.insertRow(row)
                self.ui.tv_InspectPoint2.setItem(row, 0, QTableWidgetItem(str(record.get("PointId", ""))))  # 巡检点位ID
                self.ui.tv_InspectPoint2.setItem(row, 1, QTableWidgetItem(str(record.get("PointName", ""))))  #点位名称
                self.ui.tv_InspectPoint2.setItem(row, 2,  QTableWidgetItem(str(record.get("Longitude"))+","+str(record.get("Latitude"))))  #经度
                self.ui.tv_InspectPoint2.setItem(row, 3, QTableWidgetItem(str(record["StayTime"]))) # 停留时间（秒）
                self.ui.tv_InspectPoint2.setItem(row, 4, QTableWidgetItem(str(record["InspectAngle"])))  #拍摄角度（度）
                self.ui.tv_InspectPoint2.setItem(row, 5, QTableWidgetItem(str(record["SortNo"])))

    def add_point_to_route(self):
        """添加选中的点位到路线"""
        selected_row = self.ui.tv_InspectPoint1.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "提示", "请选择要添加的巡检点！")
            return
        point_id = self.ui.tv_InspectPoint1.item(selected_row, 0).text()
        point_name = self.ui.tv_InspectPoint1.item(selected_row, 1).text()

        # 校验是否已关联
        check_sql = "SELECT * FROM InspectRoutePoint WHERE RouteId=%s AND PointId=%s"
        if self.db.execute_query(check_sql, (self.route_id, point_id)):
            QMessageBox.warning(self, "提示", "该点位已关联到路线！")
            return

        # 获取当前最大排序号，新序号=最大+1
        max_sort_sql = "SELECT MAX(SortNo) AS max_sort FROM InspectRoutePoint WHERE RouteId=%s"
        max_sort = self.db.execute_query(max_sort_sql, (self.route_id,))[0]["max_sort"] or 0
        new_sort = max_sort + 1

        # 插入关联记录（默认停留时间10秒，拍摄角度0）
        insert_sql = """
        INSERT INTO InspectRoutePoint (RouteId, PointId, SortNo, StayTime, InspectAngle)
        VALUES (%s, %s, %s, 10, 0)
        """
        if self.db.execute_query(insert_sql, (self.route_id, point_id, new_sort)):
            self.load_inspectPointByRouteId(self.route_id)  # 刷新列表
            QMessageBox.information(self, "成功", "点位添加成功！")

    def adjust_sort_up(self):
        """上移选中的点位（调整排序号）"""
        self.adjust_sort(-1)

    def adjust_sort_down(self):
        """下移选中的点位（调整排序号）"""
        self.adjust_sort(1)

    def adjust_sort(self, step):
        """调整排序号"""
        selected_row = self.ui.tv_InspectPoint2.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "提示", "请选择要调整的点位！")
            return
        # 边界校验
        if (step == -1 and selected_row == 0) or (step == 1 and selected_row == self.ui.tv_InspectPoint2.rowCount() - 1):
            QMessageBox.warning(self, "提示", "已到边界，无法调整！")
            return

        # 获取当前点位和目标点位的信息
        curr_point_id = self.ui.tv_InspectPoint2.item(selected_row, 0).text()
        curr_sort = int(self.ui.tv_InspectPoint2.item(selected_row, 5).text())
        target_row = selected_row + step
        target_point_id = self.ui.tv_InspectPoint2.item(target_row, 0).text()
        target_sort = int(self.ui.tv_InspectPoint2.item(target_row, 5).text())

        # 交换排序号
        update_sql1 = "UPDATE InspectRoutePoint SET SortNo=%s WHERE RouteId=%s AND PointId=%s"
        update_sql2 = "UPDATE InspectRoutePoint SET SortNo=%s WHERE RouteId=%s AND PointId=%s"
        self.db.execute_query(update_sql1, (target_sort, self.route_id, curr_point_id))
        self.db.execute_query(update_sql2, (curr_sort, self.route_id, target_point_id))
        self.load_inspectPointByRouteId(self.route_id)  # 刷新列表

    def remove_point_from_route(self):
        """移除选中的点位"""
        selected_row = self.ui.tv_InspectPoint2.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "提示", "请选择要移除的点位！")
            return
        point_id = self.ui.tv_InspectPoint2.item(selected_row, 0).text()

        if QMessageBox.question(self, "确认", "确定要移除该点位吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            delete_sql = "DELETE FROM InspectRoutePoint WHERE RouteId=%s AND PointId=%s"
            if self.db.execute_query(delete_sql, (self.route_id, point_id)):
                self.load_inspectPointByRouteId(self.route_id)  # 刷新列表
                QMessageBox.information(self, "成功", "点位移除成功！")

    """保存关联关系（更新停留时间、拍摄角度）"""
    def save_relation(self):
        # 遍历表格更新每个点位的属性
        for row in range(self.ui.tv_InspectPoint2.rowCount()):
            point_id = self.ui.tv_InspectPoint2.item(row, 0).text()
            stay_time = self.ui.tv_InspectPoint2.item(row, 3).text() or 0
            inspect_angle = self.ui.tv_InspectPoint2.item(row, 4).text() or 0
            # 校验数值
            try:
                stay_time = int(stay_time)
                inspect_angle = int(inspect_angle)
            except ValueError:
                QMessageBox.warning(self, "提示", f"第{row+1}行的停留时间/拍摄角度必须为整数数字！")
                return
            # 更新
            update_sql = """
            UPDATE InspectRoutePoint
            SET StayTime=%s, InspectAngle=%s
            WHERE RouteId=%s AND PointId=%s
            """
            self.db.execute_query(update_sql, (stay_time, inspect_angle, self.route_id, point_id))

        # 自动计算路线的PointCount、PathLength、InsDuration
        self.calculate_route_metrics(self.route_id)
        QMessageBox.information(self, "成功", "关联关系保存成功，已自动计算路线指标！")
        self.load_inspectroute()


    # ====================== 2. 辅助函数（计算距离/时长） ======================
    def calculate_distance(self, lng1, lat1, lng2, lat2):
        """
        计算两点经纬度间的球面距离（单位：米）
        :param lng1: 点1经度
        :param lat1: 点1纬度
        :param lng2: 点2经度
        :param lat2: 点2纬度
        :return: 距离（米）
        """
        # 地球半径（米）
        R = 6371000
        # 转弧度
        lng1_rad = math.radians(float(lng1))
        lat1_rad = math.radians(float(lat1))
        lng2_rad = math.radians(float(lng2))
        lat2_rad = math.radians(float(lat2))
        # 差值
        dlng = lng2_rad - lng1_rad
        dlat = lat2_rad - lat1_rad
        # 球面距离公式
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    def calculate_route_metrics(self, route_id):
        """
        自动计算路线的PointCount、PathLength、InsDuration
        :param route_id: 路线ID
        :param db: 数据库工具实例
        :return: 计算结果（point_count, path_length, ins_duration）
        """
        # 1. 查询路线下的点位（按SortNo排序）
        sql = """
        SELECT rp.PointId, rp.SortNo, rp.StayTime, ip.Longitude, ip.Latitude 
        FROM InspectRoutePoint rp
        LEFT JOIN InspectPoint ip ON rp.PointId = ip.PointId
        WHERE rp.RouteId = %s
        ORDER BY rp.SortNo ASC
        """
        points = self.db.execute_query(sql, (route_id,))
        point_count = len(points)

        # 2. 计算路径长度（相邻点位距离总和）
        path_length = 0.0
        if point_count >= 2:
            for i in range(point_count - 1):
                p1 = points[i]
                p2 = points[i+1]
                if p1["Longitude"] and p1["Latitude"] and p2["Longitude"] and p2["Latitude"]:
                    distance = self.calculate_distance(p1["Longitude"], p1["Latitude"], p2["Longitude"], p2["Latitude"])
                    path_length += distance

        # 3. 计算预计巡检时长（停留时间总和 + 移动时间，移动速度按0.5m/s计算）
        stay_time_total = sum([p["StayTime"] or 0 for p in points])
        move_time = path_length / 0.5 if path_length > 0 else 0
        ins_duration = stay_time_total + move_time  # 单位：秒

        # 4. 更新到InspectRoute表
        update_sql = """
        UPDATE InspectRoute 
        SET PointCount=%s, PathLength=%s, InsDuration=%s 
        WHERE RouteId=%s
        """
        self.db.execute_query(update_sql, (point_count, round(path_length, 2), round(ins_duration, 2), route_id))
        return point_count, round(path_length, 2), round(ins_duration, 2)


if __name__ == "__main__":
    # 运行应用
    app = QApplication(sys.argv)
    window = BLL_InspectRoute()
    window.show()
    sys.exit(app.exec())