from __future__ import annotations

from dataclasses import dataclass
import threading
from enum import Enum
from typing import Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from MICCProject1.scripts.DBHelper import DBHelper


class PatrolState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    EMERGENCY = "EMERGENCY"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass
class PatrolWaypoint:
    point_id: int
    point_name: str
    map_x: float
    map_y: float
    yaw_deg: float
    stay_time: int
    inspect_angle: int
    sort_no: int

@dataclass
class PatrolPlan:
    route_id: int
    route_name: str
    area_id: int
    area_name: str
    waypoints: list[PatrolWaypoint]


class PatrolService:
    def __init__(self, db: DBHelper):
        self.db = db

    def route_point_table_exists(self) -> bool:
        rows = self.db.fetch_all("SHOW TABLES LIKE 'InspectRoutePoint'")
        return bool(rows)

    def load_plan(self, route_id: int) -> tuple[Optional[PatrolPlan], str]:
        if not self.route_point_table_exists():
            return None, "缺少数据表 InspectRoutePoint，请先执行数据库初始化脚本。"

        meta = self.db.fetch_all(
            """
            SELECT ir.RouteId, ir.RouteName, ir.AreaId, ia.AreaName
            FROM InspectRoute ir
            JOIN InspectArea ia ON ia.AreaId = ir.AreaId
            WHERE ir.RouteId=%s
            """
            ,
            (route_id,),
        )
        if not meta:
            return None, "未找到选中的路线。"

        rows = self.db.fetch_all(
            """
            SELECT rp.PointId, rp.SortNo, rp.StayTime, rp.InspectAngle,
                   ip.PointName, ip.MapX, ip.MapY, ip.YawDeg
            FROM InspectRoutePoint rp
            JOIN InspectPoint ip ON ip.PointId = rp.PointId
            WHERE rp.RouteId = %s
            ORDER BY rp.SortNo
            """
            ,
            (route_id,),
        )
        if not rows:
            return None, "当前路线还没有关联点位。"

        waypoints: list[PatrolWaypoint] = []
        for row in rows:
            if row.get("MapX") is None or row.get("MapY") is None:
                return None, f"点位 {row.get('PointName', '')} 缺少ROS地图坐标。"
            waypoints.append(
                PatrolWaypoint(
                    point_id=int(row["PointId"]),
                    point_name=str(row.get("PointName", "")),
                    map_x=float(row["MapX"]),
                    map_y=float(row["MapY"]),
                    yaw_deg=float(row.get("YawDeg") or 0.0),
                    stay_time=max(1, int(row.get("StayTime") or 1)),
                    inspect_angle=int(row.get("InspectAngle") or 0),
                    sort_no=int(row.get("SortNo") or 0),
                )
            )

        expected = list(range(1, len(waypoints) + 1))
        current = [wp.sort_no for wp in waypoints]
        if current != expected:
            return None, "路线点位顺序异常（SortNo 不是连续 1..N），请先保存关联。"

        m = meta[0]
        return (
            PatrolPlan(
                route_id=int(m["RouteId"]),
                route_name=str(m.get("RouteName", "")),
                area_id=int(m["AreaId"]),
                area_name=str(m.get("AreaName", "")),
                waypoints=waypoints,
            ),
            "",
        )

class BasePatrolExecutor(QObject):
    state_changed = pyqtSignal(str)
    progress_changed = pyqtSignal(int, int, str)  # current_idx_1_based, total, point_name
    log_emitted = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._plan: Optional[PatrolPlan] = None
        self._state = PatrolState.IDLE

    @property
    def state(self) -> PatrolState:
        return self._state

    def load_plan(self, plan: PatrolPlan) -> None:
        self._plan = plan
        self._set_state(PatrolState.IDLE)

    def start(self) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def pause(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def resume(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def emergency_stop(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def _set_state(self, state: PatrolState) -> None:
        self._state = state
        self.state_changed.emit(state.value)


class MockPatrolExecutor(BasePatrolExecutor):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._idx = 0
        self._remain = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    def load_plan(self, plan: PatrolPlan) -> None:
        super().load_plan(plan)
        self._idx = 0
        self._remain = 0
        self.log_emitted.emit(
            f"已加载路线: {plan.route_name} (点位数: {len(plan.waypoints)})"
        )

    def start(self) -> bool:
        if not self._plan or not self._plan.waypoints:
            self.log_emitted.emit("启动失败: 任务为空。")
            return False
        if self._state == PatrolState.RUNNING:
            return True
        if self._state in (PatrolState.STOPPED, PatrolState.EMERGENCY, PatrolState.DONE):
            self._idx = 0
            self._remain = 0
        self._set_state(PatrolState.RUNNING)
        self._start_current_waypoint()
        self._timer.start()
        return True

    def pause(self) -> None:
        if self._state != PatrolState.RUNNING:
            return
        self._timer.stop()
        self._set_state(PatrolState.PAUSED)
        self.log_emitted.emit("任务已暂停。")

    def resume(self) -> None:
        if self._state != PatrolState.PAUSED:
            return
        self._set_state(PatrolState.RUNNING)
        self._timer.start()
        self.log_emitted.emit("任务已恢复。")

    def stop(self) -> None:
        if self._state in (PatrolState.IDLE, PatrolState.STOPPED):
            return
        self._timer.stop()
        self._set_state(PatrolState.STOPPED)
        self.log_emitted.emit("任务已停止。")
        self.finished.emit(False, "stopped")

    def emergency_stop(self) -> None:
        self._timer.stop()
        self._set_state(PatrolState.EMERGENCY)
        self.log_emitted.emit("紧急制动触发。")
        self.finished.emit(False, "emergency")

    def _start_current_waypoint(self) -> None:
        if not self._plan:
            return
        if self._idx >= len(self._plan.waypoints):
            self._timer.stop()
            self._set_state(PatrolState.DONE)
            self.log_emitted.emit("任务完成。")
            self.finished.emit(True, "done")
            return
        wp = self._plan.waypoints[self._idx]
        self._remain = wp.stay_time
        self.progress_changed.emit(self._idx + 1, len(self._plan.waypoints), wp.point_name)
        self.log_emitted.emit(
            f"到达点位[{wp.sort_no}] {wp.point_name}，停留 {wp.stay_time}s，角度 {wp.inspect_angle}°"
        )

    def _on_tick(self) -> None:
        if self._state != PatrolState.RUNNING or not self._plan:
            return
        self._remain -= 1
        if self._remain > 0:
            return
        self._idx += 1
        self._start_current_waypoint()


class RosPatrolExecutor(BasePatrolExecutor):
    """ROS executor for real patrol on Ubuntu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ros_ready = False
        self._ros_err = ""
        self._idx = 0
        self._waiting = False
        self._goal_pub = None
        self._cancel_pub = None
        self._cmd_pub = None
        self._result_sub = None
        self._wait_timer = None
        self._prepare_ros_runtime()


    def _cancel_wait_timer(self) -> None:
        timer = getattr(self, "_wait_timer", None)
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass
            self._wait_timer = None

    def _schedule_next_after_wait_ms(self, ms: int) -> None:
        self._cancel_wait_timer()
        delay_s = max(0.0, float(ms) / 1000.0)
        self._wait_timer = threading.Timer(delay_s, self._go_next_after_wait)
        self._wait_timer.daemon = True
        self._wait_timer.start()

    def _prepare_ros_runtime(self) -> None:
        try:
            import rospy  # type: ignore
            from geometry_msgs.msg import PoseStamped, Twist  # type: ignore
            from actionlib_msgs.msg import GoalID  # type: ignore
            from move_base_msgs.msg import MoveBaseActionResult  # type: ignore
            from tf.transformations import quaternion_from_euler  # type: ignore

            self._rospy = rospy
            self._PoseStamped = PoseStamped
            self._Twist = Twist
            self._GoalID = GoalID
            self._MoveBaseActionResult = MoveBaseActionResult
            self._quaternion_from_euler = quaternion_from_euler

            if not rospy.core.is_initialized():
                rospy.init_node("uav_patrol_executor", anonymous=True, disable_signals=True)

            self._goal_pub = rospy.Publisher("/move_base_simple/goal", PoseStamped, queue_size=1)
            self._cancel_pub = rospy.Publisher("/move_base/cancel", GoalID, queue_size=1)
            self._cmd_pub = rospy.Publisher("/cmd_vel", Twist, queue_size=1)
            self._result_sub = rospy.Subscriber("/move_base/result", MoveBaseActionResult, self._on_result)
            self._ros_ready = True
        except Exception as exc:
            self._ros_ready = False
            self._ros_err = str(exc)

    def start(self) -> bool:
        if not self._plan:
            self.log_emitted.emit("ROS启动失败: 未加载任务。")
            return False
        if not self._ros_ready:
            self._set_state(PatrolState.FAILED)
            self.log_emitted.emit(f"ROS执行器未就绪: {self._ros_err}")
            self.finished.emit(False, "ros_not_ready")
            return False

        if self._state in (PatrolState.STOPPED, PatrolState.EMERGENCY, PatrolState.DONE, PatrolState.FAILED):
            self._idx = 0
            self._waiting = False

        if self._state == PatrolState.RUNNING:
            return True

        self._set_state(PatrolState.RUNNING)
        self.log_emitted.emit(f"ROS巡逻启动: {self._plan.route_name}")
        self._publish_current_goal()
        return True

    def pause(self) -> None:
        if self._state != PatrolState.RUNNING:
            return
        self._cancel_current_goal()
        self._cancel_wait_timer()
        self._set_state(PatrolState.PAUSED)
        self.log_emitted.emit("ROS任务已暂停。")

    def resume(self) -> None:
        if self._state != PatrolState.PAUSED:
            return
        self._set_state(PatrolState.RUNNING)
        self.log_emitted.emit("ROS任务已恢复。")
        self._publish_current_goal()

    def stop(self) -> None:
        if self._state in (PatrolState.IDLE, PatrolState.STOPPED):
            return
        self._cancel_wait_timer()
        self._cancel_current_goal()
        self._set_state(PatrolState.STOPPED)
        self.log_emitted.emit("ROS任务已停止。")
        self.finished.emit(False, "stopped")

    def emergency_stop(self) -> None:
        self._cancel_wait_timer()
        self._cancel_current_goal()
        self._publish_zero_cmd()
        self._set_state(PatrolState.EMERGENCY)
        self.log_emitted.emit("ROS紧急制动触发。")
        self.finished.emit(False, "emergency")

    def _publish_current_goal(self) -> None:
        if not self._plan:
            return
        if self._idx >= len(self._plan.waypoints):
            self._set_state(PatrolState.DONE)
            self.log_emitted.emit("任务完成。")
            self.finished.emit(True, "done")
            return

        wp = self._plan.waypoints[self._idx]
        msg = self._PoseStamped()
        msg.header.frame_id = "map"
        msg.header.stamp = self._rospy.Time.now()
        msg.pose.position.x = wp.map_x
        msg.pose.position.y = wp.map_y
        msg.pose.position.z = 0.0

        qx, qy, qz, qw = self._quaternion_from_euler(0.0, 0.0, wp.yaw_deg * 3.141592653589793 / 180.0)
        msg.pose.orientation.x = qx
        msg.pose.orientation.y = qy
        msg.pose.orientation.z = qz
        msg.pose.orientation.w = qw

        self.progress_changed.emit(self._idx + 1, len(self._plan.waypoints), wp.point_name)
        self.log_emitted.emit(
            f"发送点位[{wp.sort_no}] {wp.point_name}: x={wp.map_x:.2f}, y={wp.map_y:.2f}, yaw={wp.yaw_deg:.1f}°"
        )

        # 等待 publisher 建立连接，避免第一条 goal 丢失
        t0 = self._rospy.Time.now().to_sec()
        while self._goal_pub.get_num_connections() == 0:
            if self._rospy.Time.now().to_sec() - t0 > 2.0:
                break
            self._rospy.sleep(0.1)

        # 只发送一次，避免 simple action server 把前一个目标取消
        self._goal_pub.publish(msg)

        self._waiting = True

    def _on_result(self, msg) -> None:
        if self._state != PatrolState.RUNNING or not self._plan or not self._waiting:
            return

        status = int(msg.status.status)
        wp = self._plan.waypoints[self._idx]

        if status == 3:
            self._waiting = False
            self.log_emitted.emit(f"到达点位[{wp.sort_no}] {wp.point_name}，停留 {wp.stay_time}s")
            self._schedule_next_after_wait_ms(max(1, wp.stay_time) * 1000)
        elif status in (4, 5, 9):
            self._waiting = False
            self._set_state(PatrolState.FAILED)
            self.log_emitted.emit(f"点位[{wp.sort_no}] {wp.point_name} 执行失败，status={status}")
            self.finished.emit(False, f"goal_failed_{status}")

    def _go_next_after_wait(self) -> None:
        if self._state != PatrolState.RUNNING or not self._plan:
            return
        self._idx += 1
        self._publish_current_goal()

    def _cancel_current_goal(self) -> None:
        if self._cancel_pub is not None:
            self._cancel_pub.publish(self._GoalID())

    def _publish_zero_cmd(self) -> None:
        if self._cmd_pub is None:
            return
        twist = self._Twist()
        for _ in range(3):
            self._cmd_pub.publish(twist)

def create_executor(mode: str, parent=None) -> BasePatrolExecutor:
    normalized = (mode or "mock").strip().lower()
    if normalized == "ros":
        return RosPatrolExecutor(parent)
    return MockPatrolExecutor(parent)

