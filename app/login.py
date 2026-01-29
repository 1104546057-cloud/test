# app/login.py
from __future__ import annotations

from PyQt5 import QtWidgets
from PyQt5.QtCore import pyqtSignal, QPropertyAnimation, QEasingCurve, QPoint, Qt, QTimer
from PyQt5.QtCore import QSequentialAnimationGroup
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QIcon
from qfluentwidgets import ThemeColor, TransparentToolButton
from qfluentwidgets import FluentIcon as FIF

try:
    from .ui_loader import resource_path
    from UI.generated.login import Ui_Form
except ImportError:
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from app.ui_loader import resource_path
    from UI.generated.login import Ui_Form


USE_FLUENT_BUTTONS = True
if USE_FLUENT_BUTTONS:
    from qfluentwidgets import PushButton


def replace_widget(old: QWidget, new: QWidget):
    parent = old.parentWidget()
    layout = parent.layout()
    if layout is None:
        raise RuntimeError("父控件没有 layout，无法 replaceWidget，请确认 Designer 里用了布局")

    layout.replaceWidget(old, new)
    new.setObjectName(old.objectName())
    old.setParent(None)


class LoginPage(QWidget):
    login_success = pyqtSignal()
    """
    合并版：LoginPage 里同时包含 UI 绑定 + 登录业务逻辑（密码输入/回退/校验）。
    """
    def __init__(self):
        super().__init__()
        ui = Ui_Form()
        ui.setupUi(self)
        self.ui = ui
        self.setWindowIcon(QIcon(resource_path("assets/app.ico")))

        # ===== 业务状态（原 login_logic.py 的内容）=====
        self.max_len = 6
        self.password = ""
        self._pending_login = False
        self._login_delay_ms = 450

        # ===== UI 初始化 =====
        self.apply_fluent_dot_style()

        if USE_FLUENT_BUTTONS:
            for i in range(10):
                old = self.findChild(QWidget, f"btn{i}")
                if old:
                    new_btn = PushButton(old.text(), self)
                    replace_widget(old, new_btn)

        back_old = self.findChild(QWidget, "btnBack")
        if back_old:
            new_back = TransparentToolButton(FIF.LEFT_ARROW, self)
            new_back.setFixedSize(back_old.size())
            replace_widget(back_old, new_back)

        # 绑定按钮
        for i in range(10):
            btn = self.findChild(QWidget, f"btn{i}")
            if btn:
                btn.clicked.connect(lambda _, n=i: self.on_digit(n))

        back_btn = self.findChild(QWidget, "btnBack")
        if back_btn:
            back_btn.clicked.connect(self.on_backspace)

        self.update_dots()

        if self.is_complete():
            if self.verify():
                self.login_success.emit()
            else:
                self.password = ""
                self.update_dots()

    # ===== 业务方法 =====
    def verify(self) -> bool:
        """
        TODO: 写你的密码验证规则
        """
        return self.password == "123456"

    def is_complete(self) -> bool:
        return len(self.password) >= self.max_len

    # ===== UI/交互 =====
    def on_digit(self, n: int):
        if self._pending_login:
            return
        if len(self.password) >= self.max_len:
            return
        self.password += str(n)
        self.update_dots()

        # ???6?????
        if self.is_complete():
            if self.verify():
                self._pending_login = True
                self._set_inputs_enabled(False)
                self._play_success_anim()
                QTimer.singleShot(self._login_delay_ms, self._emit_login)
            else:
                self.password = ""
                self.update_dots()
                self._shake_dots()

        # 可选：输入满 6 位自动验证
        # if self.is_complete():
        #     ok = self.verify()
        #     print("login ok?", ok)

    def on_backspace(self):
        if self._pending_login:
            return
        if not self.password:
            return
        self.password = self.password[:-1]
        self.update_dots()

    def _emit_login(self):
        self.login_success.emit()

    def _set_inputs_enabled(self, enabled: bool) -> None:
        for i in range(10):
            btn = self.findChild(QWidget, f"btn{i}")
            if btn:
                btn.setEnabled(enabled)
        back_btn = self.findChild(QWidget, "btnBack")
        if back_btn:
            back_btn.setEnabled(enabled)

    def _shake_dots(self) -> None:
        target = getattr(self.ui, "dotsWrap", None)
        if target is None:
            target = getattr(self.ui, "dotsRow", None)
        if target is None:
            return

        base = target.pos()
        offsets = [QPoint(-6, 0), QPoint(6, 0), QPoint(-4, 0), QPoint(4, 0), QPoint(0, 0)]

        group = QSequentialAnimationGroup(target)
        for off in offsets:
            anim = QPropertyAnimation(target, b"pos", target)
            anim.setDuration(45)
            anim.setEasingCurve(QEasingCurve.InOutSine)
            anim.setStartValue(base)
            anim.setEndValue(base + off)
            group.addAnimation(anim)
        group.start()
        self._shake_anim = group

    def _play_success_anim(self) -> None:
        target = getattr(self.ui, "dotsWrap", None)
        if target is None:
            target = getattr(self.ui, "dotsRow", None)
        if target is None:
            return

        base = target.pos()
        offsets = [QPoint(0, 2), QPoint(0, -1), QPoint(0, 0)]
        group = QSequentialAnimationGroup(target)
        for off in offsets:
            anim = QPropertyAnimation(target, b"pos", target)
            anim.setDuration(90)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.setStartValue(base)
            anim.setEndValue(base + off)
            group.addAnimation(anim)
        group.start()
        self._success_anim = group

    def apply_fluent_dot_style(self):
        accent = ThemeColor.PRIMARY.color()
        r, g, b, _ = accent.getRgb()

        dot_qss = f"""
        *#dot1, *#dot2, *#dot3, *#dot4, *#dot5, *#dot6 {{
            background: transparent;
            border: 2px solid rgba(0,0,0,90);
            border-radius: 11px;
        }}

        *#dot1[dotState="filled"],
        *#dot2[dotState="filled"],
        *#dot3[dotState="filled"],
        *#dot4[dotState="filled"],
        *#dot5[dotState="filled"],
        *#dot6[dotState="filled"] {{
            background: rgb({r},{g},{b});
            border: 2px solid rgb({r},{g},{b});
            border-radius: 11px;
        }}
        """
        self.setStyleSheet(self.styleSheet() + dot_qss)

    def update_dots(self):
        filled = len(self.password)

        accent = ThemeColor.PRIMARY.color()
        r, g, b, _ = accent.getRgb()

        for i in range(1, 7):
            dot = self.findChild(QWidget, f"dot{i}")
            if not dot:
                continue

            if i <= filled:
                dot.setStyleSheet(f"""
                    background: rgb({r},{g},{b});
                    border: 2px solid rgb({r},{g},{b});
                    border-radius: 11px;
                """)
            else:
                dot.setStyleSheet("""
                    background: transparent;
                    border: 2px solid rgba(0,0,0,90);
                    border-radius: 11px;
                """)
