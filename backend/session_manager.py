"""
Slot Manager — MySQL 存储实现。

将对话存档从 JSON 文件迁移到 MySQL，对外接口保持不变。
"""
import datetime
import json
import logging
from typing import List, Dict, Optional

import pymysql
from dbutils.pooled_db import PooledDB

from config import SLOT_COUNT
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD
from config import MYSQL_DATABASE, MYSQL_CHARSET

logger = logging.getLogger(__name__)


def _get_connection(pool):
    """安全地从连接池获取连接，失败时统一处理。"""
    try:
        return pool.connection()
    except pymysql.Error as e:
        logger.error(f"无法从连接池获取数据库连接: {e}")
        raise RuntimeError(f"数据库连接池获取连接失败: {e}")
    except Exception as e:
        logger.error(f"获取数据库连接时发生未知错误: {e}")
        raise RuntimeError(f"数据库连接异常: {e}")


def _safe_rollback(conn):
    """安全回滚，避免在异常处理中二次抛出异常。"""
    if conn:
        try:
            conn.rollback()
        except Exception:
            pass


class SlotManager:
    def __init__(self):
        self._ensure_database()
        try:
            self.pool = PooledDB(
                creator=pymysql,
                maxconnections=10,
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE,
                charset=MYSQL_CHARSET,
                cursorclass=pymysql.cursors.DictCursor,
            )
            self._init_tables()
        except pymysql.Error as e:
            logger.critical(f"数据库连接池初始化失败: {e}")
            raise RuntimeError(f"无法连接到 MySQL 数据库: {e}")

    # ── 数据库初始化 ──

    def _ensure_database(self):
        """确保数据库存在，不存在则自动创建。"""
        try:
            conn = pymysql.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                charset=MYSQL_CHARSET,
            )
        except pymysql.Error as e:
            raise RuntimeError(
                f"无法连接到 MySQL 服务器 ({MYSQL_HOST}:{MYSQL_PORT})，请确认 MySQL 服务已启动: {e}"
            )
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` "
                    f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            conn.commit()
        except pymysql.Error as e:
            raise RuntimeError(
                f"无法创建数据库 `{MYSQL_DATABASE}`，请确认用户 '{MYSQL_USER}' 有 CREATE 权限: {e}"
            )
        finally:
            conn.close()

    def _init_tables(self):
        """自动建表（若不存在）。"""
        conn = _get_connection(self.pool)
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS slots (
                        id INT PRIMARY KEY,
                        model VARCHAR(64) NOT NULL DEFAULT '',
                        system_prompt TEXT,
                        api_key VARCHAR(256) DEFAULT '',
                        title VARCHAR(128) DEFAULT '',
                        params TEXT,
                        created_at VARCHAR(32) DEFAULT '',
                        updated_at VARCHAR(32) DEFAULT ''
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        slot_id INT NOT NULL,
                        role VARCHAR(16) NOT NULL,
                        content TEXT,
                        created_at VARCHAR(32) DEFAULT '',
                        FOREIGN KEY (slot_id) REFERENCES slots(id) ON DELETE CASCADE,
                        INDEX idx_slot_id (slot_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                for col, col_def in [
                    ("params", "TEXT AFTER title"),
                ]:
                    cursor.execute(f"SHOW COLUMNS FROM `slots` LIKE '{col}'")
                    if not cursor.fetchone():
                        cursor.execute(f"ALTER TABLE `slots` ADD COLUMN `{col}` {col_def}")
                        logger.info(f"已添加 {col} 列到 slots 表")
            conn.commit()
            logger.info("MySQL 数据库表初始化完成")
        except pymysql.Error as e:
            logger.error(f"数据库表初始化失败: {e}")
            _safe_rollback(conn)
            raise
        finally:
            conn.close()

    # ── 核心 CRUD ──

    def _with_conn(self, callback, *args, **kwargs):
        """通用模板：获取连接 → 执行 → 提交 → 关闭。"""
        conn = _get_connection(self.pool)
        try:
            result = callback(conn, *args, **kwargs)
            conn.commit()
            return result
        except pymysql.Error as e:
            _safe_rollback(conn)
            raise  # 由上层统一处理
        finally:
            conn.close()

    def create_slot(self, index: int, model: str, system_prompt: str,
                     api_key: str = "", params: Optional[dict] = None,
                     title: str = "") -> bool:
        if index < 0 or index >= SLOT_COUNT:
            return False
        conn = _get_connection(self.pool)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM slots WHERE id = %s", (index,))
                if cursor.fetchone():
                    return False
                now = datetime.datetime.now().isoformat()
                title = title.strip()
                params_json = json.dumps(params) if params else "{}"
                cursor.execute(
                    "INSERT INTO slots (id, model, system_prompt, api_key, title, params, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (index, model, system_prompt, api_key, title, params_json, now, now),
                )
            conn.commit()
            return True
        except pymysql.Error as e:
            logger.error(f"create_slot({index}) 失败: {e}")
            _safe_rollback(conn)
            return False
        finally:
            conn.close()

    def get_slot(self, index: int) -> Optional[Dict]:
        conn = _get_connection(self.pool)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM slots WHERE id = %s", (index,))
                slot = cursor.fetchone()
                if not slot:
                    return None
                if isinstance(slot.get("params"), str):
                    try:
                        slot["params"] = json.loads(slot["params"])
                    except (json.JSONDecodeError, TypeError):
                        slot["params"] = {}
                elif slot.get("params") is None:
                    slot["params"] = {}
                cursor.execute(
                    "SELECT id, role, content FROM messages WHERE slot_id = %s ORDER BY id ASC",
                    (index,),
                )
                slot["history"] = list(cursor.fetchall())
                return slot
        except pymysql.Error as e:
            logger.error(f"get_slot({index}) 失败: {e}")
            return None
        finally:
            conn.close()

    def delete_slot(self, index: int) -> bool:
        conn = _get_connection(self.pool)
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM slots WHERE id = %s", (index,))
            conn.commit()
            return cursor.rowcount > 0
        except pymysql.Error as e:
            logger.error(f"delete_slot({index}) 失败: {e}")
            _safe_rollback(conn)
            return False
        finally:
            conn.close()

    def update_slot_meta(self, index: int, meta: dict) -> bool:
        conn = _get_connection(self.pool)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM slots WHERE id = %s", (index,))
                if not cursor.fetchone():
                    return False
                set_parts = []
                values = []
                for key, val in meta.items():
                    set_parts.append(f"{key} = %s")
                    values.append(val)
                set_parts.append("updated_at = %s")
                values.append(datetime.datetime.now().isoformat())
                values.append(index)
                sql = f"UPDATE slots SET {', '.join(set_parts)} WHERE id = %s"
                cursor.execute(sql, values)
            conn.commit()
            return True
        except pymysql.Error as e:
            logger.error(f"update_slot_meta({index}) 失败: {e}")
            _safe_rollback(conn)
            return False
        finally:
            conn.close()

    def save_slot_history(self, index: int, history: List) -> bool:
        conn = _get_connection(self.pool)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM slots WHERE id = %s", (index,))
                if not cursor.fetchone():
                    return False
                cursor.execute("DELETE FROM messages WHERE slot_id = %s", (index,))
                if history:
                    cursor.executemany(
                        "INSERT INTO messages (slot_id, role, content) VALUES (%s, %s, %s)",
                        [(index, m.get("role", ""), m.get("content", "")) for m in history],
                    )
                cursor.execute(
                    "UPDATE slots SET updated_at = %s WHERE id = %s",
                    (datetime.datetime.now().isoformat(), index),
                )
            conn.commit()
            return True
        except pymysql.Error as e:
            logger.error(f"save_slot_history({index}) 失败: {e}")
            _safe_rollback(conn)
            return False
        finally:
            conn.close()

    # ── append-only 写入 ──

    def append_messages(self, slot_id: int, messages: List[Dict]) -> List[int]:
        conn = _get_connection(self.pool)
        try:
            with conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO messages (slot_id, role, content) VALUES (%s, %s, %s)",
                    [(slot_id, m.get("role", ""), m.get("content", "")) for m in messages],
                )
                first_id = cursor.lastrowid
                ids = list(range(first_id, first_id + len(messages)))
                cursor.execute(
                    "UPDATE slots SET updated_at = %s WHERE id = %s",
                    (datetime.datetime.now().isoformat(), slot_id),
                )
            conn.commit()
            return ids
        except pymysql.Error as e:
            logger.error(f"append_messages({slot_id}) 失败: {e}")
            _safe_rollback(conn)
            return []
        finally:
            conn.close()

    def delete_messages_from(self, slot_id: int, from_message_id: int) -> bool:
        conn = _get_connection(self.pool)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM messages WHERE slot_id = %s AND id >= %s",
                    (slot_id, from_message_id),
                )
                cursor.execute(
                    "UPDATE slots SET updated_at = %s WHERE id = %s",
                    (datetime.datetime.now().isoformat(), slot_id),
                )
            conn.commit()
            return True
        except pymysql.Error as e:
            logger.error(f"delete_messages_from({slot_id}, {from_message_id}) 失败: {e}")
            _safe_rollback(conn)
            return False
        finally:
            conn.close()

    def clear_all_messages(self, slot_id: int) -> bool:
        conn = _get_connection(self.pool)
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM messages WHERE slot_id = %s", (slot_id,))
                cursor.execute(
                    "UPDATE slots SET updated_at = %s WHERE id = %s",
                    (datetime.datetime.now().isoformat(), slot_id),
                )
            conn.commit()
            return True
        except pymysql.Error as e:
            logger.error(f"clear_all_messages({slot_id}) 失败: {e}")
            _safe_rollback(conn)
            return False
        finally:
            conn.close()

    def update_message_content(self, message_id: int, content: str) -> bool:
        conn = _get_connection(self.pool)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE messages SET content = %s WHERE id = %s",
                    (content, message_id),
                )
            conn.commit()
            return cursor.rowcount > 0
        except pymysql.Error as e:
            logger.error(f"update_message_content({message_id}) 失败: {e}")
            _safe_rollback(conn)
            return False
        finally:
            conn.close()

    def list_slots(self) -> List[Optional[Dict]]:
        conn = _get_connection(self.pool)
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT s.*,
                           (SELECT COUNT(*) FROM messages m WHERE m.slot_id = s.id) AS msg_count
                    FROM slots s
                    ORDER BY s.id ASC
                """)
                rows = cursor.fetchall()
                row_map = {r["id"]: r for r in rows}
                result = []
                for i in range(SLOT_COUNT):
                    slot = row_map.get(i)
                    if slot is None:
                        result.append(None)
                    else:
                        # 解析 params JSON
                        params_raw = slot.get("params")
                        if isinstance(params_raw, str):
                            try:
                                params_val = json.loads(params_raw)
                            except (json.JSONDecodeError, TypeError):
                                params_val = {}
                        elif params_raw is None:
                            params_val = {}
                        else:
                            params_val = params_raw
                        result.append({
                            "index": i,
                            "model": slot.get("model", "未知"),
                            "system_prompt": slot.get("system_prompt", ""),
                            "created_at": slot.get("created_at", ""),
                            "updated_at": slot.get("updated_at", ""),
                            "message_count": slot.get("msg_count", 0) // 2,
                            "title": slot.get("title", ""),
                            "params": params_val,
                        })
                return result
        except pymysql.Error as e:
            logger.error(f"list_slots 失败: {e}")
            return [None] * SLOT_COUNT
        finally:
            conn.close()
