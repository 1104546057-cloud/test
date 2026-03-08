import mysql.connector
from loguru import logger
from mysql.connector import Error

from MICCProject1.scripts.Config import load_config


class DBHelper:
    def __init__(self):
        self.conn = None
        # 缓存数据库/备份配置，供外部（如备份/恢复模块）调用
        cfg = load_config()
        self.db_config = {
            "host": cfg.get("DB_HOST", "127.0.0.1"),
            "port": int(cfg.get("DB_PORT", "3306") or 3306),
            "user": cfg.get("DB_USER", "root"),
            "password": cfg.get("DB_PASS", "123456"),
            "db_name": cfg.get("DB_NAME", "UGV_DB"),
            # 若未配置路径，尝试使用 PATH 中的可执行名
            "mysqldump_path": cfg.get("mysqldump_path") or "mysqldump",
            "mysql_path": cfg.get("mysql_path") or "mysql",
        }
        try:
            self.conn = mysql.connector.connect(
                host=self.db_config["host"],
                port=self.db_config["port"],
                user=self.db_config["user"],
                password=self.db_config["password"],
                database=self.db_config["db_name"],
                connection_timeout=2,
            )
            if self.conn.is_connected():
                logger.info("数据库连接成功")
        except Error as e:
            logger.info(f"数据库连接失败: {e}")

    def execute_query(self, query, params=None):
        cursor = self.conn.cursor(dictionary=True)
        try:
            cursor.execute(query, params or ())

            # 如果是 SELECT 查询，立即读取所有结果
            if query.strip().lower().startswith('select'):
                result = cursor.fetchall()
                cursor.close()
                return result  # 返回结果数据，而不是 cursor
            else:
                # 对于 INSERT、UPDATE、DELETE 等操作
                self.conn.commit()
                affected_rows = cursor.rowcount
                cursor.close()
                return affected_rows

        except Exception as e:
            print(f"执行SQL失败: {e}")
            logger.error(f"执行SQL失败: {e}")
            self.conn.rollback()
            return None

    def fetch_all(self, query, params=None):
        # 现在 execute_query 直接返回结果
        result = self.execute_query(query, params)
        return result if result is not None else []

    def close(self):
        if self.conn and self.conn.is_connected():
            self.conn.close()
            print("数据库连接已关闭")

