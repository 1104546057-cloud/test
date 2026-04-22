from __future__ import annotations

from PyQt5.QtCore import QTimer


def init_navigation(window, parent=None) -> None:
    if parent is not None:
        setattr(window, "_nav_parent_window", parent)
    if not hasattr(window, "_nav_restore_enabled"):
        setattr(window, "_nav_restore_enabled", True)


def _show_window(window, mode: str = "normal", reference=None) -> None:
    resolved_mode = mode
    if mode == "match_parent":
        try:
            if reference is not None and reference.isFullScreen():
                resolved_mode = "fullscreen"
            elif reference is not None and reference.isMaximized():
                resolved_mode = "maximized"
            else:
                resolved_mode = "normal"
        except Exception:
            resolved_mode = "normal"

    try:
        if reference is not None:
            window.resize(reference.size())
            if resolved_mode == "normal":
                window.move(reference.pos())
    except Exception:
        pass

    if resolved_mode == "fullscreen":
        window.showFullScreen()
    elif resolved_mode == "maximized":
        window.showMaximized()
    else:
        window.show()


def _activate_window(window) -> None:
    try:
        window.raise_()
        window.activateWindow()
    except Exception:
        pass


def open_child_window(parent, child, mode: str = "match_parent") -> None:
    if child is None:
        return

    init_navigation(child, parent)

    try:
        if parent is not None:
            parent.hide()
    except Exception:
        pass

    _show_window(child, mode=mode, reference=parent)
    QTimer.singleShot(0, lambda: _activate_window(child))


def restore_previous_window(window, mode: str = "match_parent") -> None:
    parent = getattr(window, "_nav_parent_window", None)
    if parent is None or not getattr(window, "_nav_restore_enabled", True):
        return

    try:
        _show_window(parent, mode=mode, reference=window)
        QTimer.singleShot(0, lambda: _activate_window(parent))
    except Exception:
        pass
