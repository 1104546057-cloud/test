from __future__ import annotations

import os


def load_db_config() -> dict:
    """
    数据库连接配置：
    - 优先读取环境变量
    - 没有则使用默认值（本机开发）
    """
    return {
        "host": os.getenv("UAV_DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("UAV_DB_PORT", "3306")),
        "user": os.getenv("UAV_DB_USER", "root"),
        "password": os.getenv("UAV_DB_PASSWORD", "123456"),
        "database": os.getenv("UAV_DB_NAME", "device_management"),
    }
