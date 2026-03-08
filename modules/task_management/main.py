from __future__ import annotations

import sys

from PyQt5.QtWidgets import QApplication

from modules.task_management.pages.task_execution_management_page import TaskExecutionManagementPage


def create_task_management_page(parent=None) -> TaskExecutionManagementPage:
    return TaskExecutionManagementPage(parent)


def main() -> int:
    app = QApplication(sys.argv)
    page = create_task_management_page()
    page.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
