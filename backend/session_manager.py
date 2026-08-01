"""
Slot Manager — 基于 MySQL 的对话存档存储实现。

提供存档的增删改查、消息追加与删除等数据库操作。
"""
import datetime
import json
import logging
from contextlib import contextmanager
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

    def close(self):
        """关闭数据库连接池（服务关闭时调用）。"""
        try:
            if getattr(self, "pool", None) is not None:
                self.pool.close()
        except Exception as e:
            logger.warning(f"关闭数据库连接池失败: {e}")

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
                        dual_config TEXT,
                        created_at VARCHAR(32) DEFAULT '',
                        updated_at VARCHAR(32) DEFAULT ''
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        slot_id INT NOT NULL,
                        role VARCHAR(16) NOT NULL,
                        source VARCHAR(16) NOT NULL DEFAULT '',
                        content TEXT,
                        created_at VARCHAR(32) DEFAULT '',
                        FOREIGN KEY (slot_id) REFERENCES slots(id) ON DELETE CASCADE,
                        INDEX idx_slot_id (slot_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                for col, col_def in [
                    ("params", "TEXT AFTER title"),
                    ("dual_config", "TEXT AFTER params"),
                ]:
                    cursor.execute(f"SHOW COLUMNS FROM `slots` LIKE '{col}'")
                    if not cursor.fetchone():
                        cursor.execute(f"ALTER TABLE `slots` ADD COLUMN `{col}` {col_def}")
                        logger.info(f"已添加 {col} 列到 slots 表")
                cursor.execute(f"SHOW COLUMNS FROM `messages` LIKE 'source'")
                if not cursor.fetchone():
                    cursor.execute(
                        "ALTER TABLE `messages` ADD COLUMN `source` VARCHAR(16) NOT NULL DEFAULT '' AFTER role"
                    )
                    logger.info("已添加 source 列到 messages 表")
            conn.commit()
            logger.info("MySQL 数据库表初始化完成")
        except pymysql.Error as e:
            logger.error(f"数据库表初始化失败: {e}")
            _safe_rollback(conn)
            raise
        finally:
            conn.close()

    # ── 通用事务模板 ──

    @contextmanager
    def _transaction(self):
        """获取连接 → 执行 → 提交 → 关闭，异常时回滚并重抛。"""
        conn = _get_connection(self.pool)
        try:
            yield conn
            conn.commit()
        except pymysql.Error:
            _safe_rollback(conn)
            raise
        finally:
            conn.close()

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now().isoformat()

    @staticmethod
    def _json_or_default(raw, default):
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return default
        return raw if raw is not None else default

    # ── 核心 CRUD ──

    def create_slot(self, index: int, model: str, system_prompt: str,
                     api_key: str = "", params: Optional[dict] = None,
                     title: str = "", dual_config: Optional[dict] = None) -> bool:
        if index < 0 or index >= SLOT_COUNT:
            return False
        try:
            with self._transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id FROM slots WHERE id = %s", (index,))
                    if cursor.fetchone():
                        return False
                    now = self._now()
                    title = title.strip()
                    params_json = json.dumps(params) if params else "{}"
                    dual_json = json.dumps(dual_config) if dual_config else "{}"
                    cursor.execute(
                        "INSERT INTO slots (id, model, system_prompt, api_key, title, params, dual_config, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (index, model, system_prompt, api_key, title, params_json, dual_json, now, now),
                    )
            return True
        except pymysql.Error as e:
            logger.error(f"create_slot({index}) 失败: {e}")
            return False

    def get_slot(self, index: int) -> Optional[Dict]:
        try:
            with self._transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM slots WHERE id = %s", (index,))
                    slot = cursor.fetchone()
                    if not slot:
                        return None
                    slot["params"] = self._json_or_default(slot.get("params"), {})
                    slot["dual_config"] = self._json_or_default(slot.get("dual_config"), {})
                    cursor.execute(
                        "SELECT id, role, content, source FROM messages WHERE slot_id = %s ORDER BY id ASC",
                        (index,),
                    )
                    slot["history"] = list(cursor.fetchall())
                    return slot
        except pymysql.Error as e:
            logger.error(f"get_slot({index}) 失败: {e}")
            return None

    def delete_slot(self, index: int) -> bool:
        try:
            with self._transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM slots WHERE id = %s", (index,))
                    deleted = cursor.rowcount > 0
            return deleted
        except pymysql.Error as e:
            logger.error(f"delete_slot({index}) 失败: {e}")
            return False

    # 允许通过 update_slot_meta 更新的列（白名单，防止动态 SQL 注入）
    _META_ALLOWED_COLUMNS = {"title", "api_key"}

    def update_slot_meta(self, index: int, meta: dict) -> bool:
        try:
            with self._transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id FROM slots WHERE id = %s", (index,))
                    if not cursor.fetchone():
                        return False
                    set_parts = []
                    values = []
                    for key, val in meta.items():
                        if key not in self._META_ALLOWED_COLUMNS:
                            logger.warning(f"update_slot_meta({index}) 跳过非法列: {key}")
                            continue
                        set_parts.append(f"{key} = %s")
                        values.append(val)
                    if not set_parts:
                        return False
                    set_parts.append("updated_at = %s")
                    values.append(self._now())
                    values.append(index)
                    sql = f"UPDATE slots SET {', '.join(set_parts)} WHERE id = %s"
                    cursor.execute(sql, values)
            return True
        except pymysql.Error as e:
            logger.error(f"update_slot_meta({index}) 失败: {e}")
            return False

    def save_slot_history(self, index: int, history: List) -> bool:
        try:
            with self._transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id FROM slots WHERE id = %s", (index,))
                    if not cursor.fetchone():
                        return False
                    cursor.execute("DELETE FROM messages WHERE slot_id = %s", (index,))
                    if history:
                        cursor.executemany(
                            "INSERT INTO messages (slot_id, role, content, source) VALUES (%s, %s, %s, %s)",
                            [(index, m.get("role", ""), m.get("content", ""), m.get("source", "")) for m in history],
                        )
                    cursor.execute(
                        "UPDATE slots SET updated_at = %s WHERE id = %s",
                        (self._now(), index),
                    )
            return True
        except pymysql.Error as e:
            logger.error(f"save_slot_history({index}) 失败: {e}")
            return False

    # ── append-only 写入 ──

    def append_messages(self, slot_id: int, messages: List[Dict]) -> List[int]:
        try:
            with self._transaction() as conn:
                with conn.cursor() as cursor:
                    # 逐条插入并记录每条真实 ID
                    ids = []
                    for m in messages:
                        cursor.execute(
                            "INSERT INTO messages (slot_id, role, content, source) VALUES (%s, %s, %s, %s)",
                            (slot_id, m.get("role", ""), m.get("content", ""), m.get("source", "")),
                        )
                        ids.append(cursor.lastrowid)
                    cursor.execute(
                        "UPDATE slots SET updated_at = %s WHERE id = %s",
                        (self._now(), slot_id),
                    )
            return ids
        except pymysql.Error as e:
            logger.error(f"append_messages({slot_id}) 失败: {e}")
            return []

    def delete_messages_from(self, slot_id: int, from_message_id: int) -> bool:
        try:
            with self._transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM messages WHERE slot_id = %s AND id >= %s",
                        (slot_id, from_message_id),
                    )
                    cursor.execute(
                        "UPDATE slots SET updated_at = %s WHERE id = %s",
                        (self._now(), slot_id),
                    )
            return True
        except pymysql.Error as e:
            logger.error(f"delete_messages_from({slot_id}, {from_message_id}) 失败: {e}")
            return False

    def delete_messages_by_ids(self, slot_id: int, message_ids: List[int]) -> bool:
        """按消息 ID 精确删除（用于删除中间一段消息，不改变其余消息 ID）。"""
        if not message_ids:
            return True
        try:
            with self._transaction() as conn:
                with conn.cursor() as cursor:
                    placeholders = ", ".join(["%s"] * len(message_ids))
                    cursor.execute(
                        f"DELETE FROM messages WHERE slot_id = %s AND id IN ({placeholders})",
                        (slot_id, *message_ids),
                    )
                    cursor.execute(
                        "UPDATE slots SET updated_at = %s WHERE id = %s",
                        (self._now(), slot_id),
                    )
            return True
        except pymysql.Error as e:
            logger.error(f"delete_messages_by_ids({slot_id}) 失败: {e}")
            return False

    def clear_all_messages(self, slot_id: int) -> bool:
        try:
            with self._transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM messages WHERE slot_id = %s", (slot_id,))
                    cursor.execute(
                        "UPDATE slots SET updated_at = %s WHERE id = %s",
                        (self._now(), slot_id),
                    )
            return True
        except pymysql.Error as e:
            logger.error(f"clear_all_messages({slot_id}) 失败: {e}")
            return False

    def touch_slot(self, index: int) -> bool:
        """仅刷新存档的 updated_at（继续回复等只改内容不新增消息的场景）。"""
        try:
            with self._transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE slots SET updated_at = %s WHERE id = %s",
                        (self._now(), index),
                    )
            return True
        except pymysql.Error as e:
            logger.error(f"touch_slot({index}) 失败: {e}")
            return False

    def update_message_content(self, message_id: int, content: str) -> bool:
        try:
            with self._transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE messages SET content = %s WHERE id = %s",
                        (content, message_id),
                    )
                    updated = cursor.rowcount > 0
            return updated
        except pymysql.Error as e:
            logger.error(f"update_message_content({message_id}) 失败: {e}")
            return False

    def list_slots(self) -> List[Optional[Dict]]:
        try:
            with self._transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT s.*,
                               (SELECT COALESCE(SUM(role = 'user'), 0)
                                FROM messages m WHERE m.slot_id = s.id) AS round_count
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
                            params_val = self._json_or_default(slot.get("params"), {})
                            dual_val = self._json_or_default(slot.get("dual_config"), {})
                            result.append({
                                "index": i,
                                "model": slot.get("model", "未知"),
                                "system_prompt": slot.get("system_prompt", ""),
                                "created_at": slot.get("created_at", ""),
                                "updated_at": slot.get("updated_at", ""),
                                "message_count": slot.get("round_count", 0),
                                "title": slot.get("title", ""),
                                "params": params_val,
                                "dual_config": dual_val,
                                "dual_enabled": dual_val.get("enabled", False),
                            })
                    return result
        except pymysql.Error as e:
            logger.error(f"list_slots 失败: {e}")
            return [None] * SLOT_COUNT

    def update_dual_config(self, index: int, dual_config: dict) -> bool:
        """更新 dual_config（如切换响应模式）。"""
        try:
            with self._transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id FROM slots WHERE id = %s", (index,))
                    if not cursor.fetchone():
                        return False
                    cursor.execute(
                        "UPDATE slots SET dual_config = %s, updated_at = %s WHERE id = %s",
                        (json.dumps(dual_config), self._now(), index),
                    )
            return True
        except pymysql.Error as e:
            logger.error(f"update_dual_config({index}) 失败: {e}")
            return False
