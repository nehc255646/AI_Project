"""
全局配置 — 数据库、槽位与默认生成参数。

模型目录由用户自行配置（OpenAI 兼容接口），保存在数据库中。
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 路径
BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

# 从项目根目录加载 .env
load_dotenv(BASE_DIR.parent / ".env")

# 无鉴权 OpenAI 兼容端点（如本地 Ollama）时客户端仍需要占位 key
DUMMY_API_KEY = "sk-no-auth"
DEFAULT_MAX_TOKENS = 8192

# CORS 允许来源（逗号分隔，可通过 ALLOWED_ORIGINS 环境变量覆盖）
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "").strip()
ALLOWED_ORIGINS = (
    [o.strip() for o in _raw_origins.split(",") if o.strip()]
    if _raw_origins
    else ["http://localhost:5173", "http://127.0.0.1:5173"]
)

# 限制
CONTEXT_WINDOW_SIZE = 100   # 每次传给 AI 模型的消息数（上下文窗口）
SLOT_COUNT = 10

# ── 自定义背景图 ──
BACKGROUNDS_DIR = BASE_DIR / "backgrounds"
BACKGROUND_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
BACKGROUND_MAX_SIZE = 10 * 1024 * 1024  # 10MB

# MySQL 配置（密码必须通过环境变量设置，不提供默认值）
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
_mysql_port_raw = os.environ.get("MYSQL_PORT", "3306")
try:
    MYSQL_PORT = int(_mysql_port_raw)
except (ValueError, TypeError):
    raise RuntimeError(
        f"MYSQL_PORT 环境变量值无效: {_mysql_port_raw!r}，应为整数端口号"
    )
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD")
if not MYSQL_PASSWORD or not MYSQL_PASSWORD.strip():
    raise RuntimeError(
        "MYSQL_PASSWORD 环境变量未设置或为空！请在系统环境变量或 .env 文件中设置有效的 MySQL 密码。"
    )
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "ai_chat")
MYSQL_CHARSET = "utf8mb4"

# 默认生成参数（创建存档时预填）
DEFAULT_PARAMS = {
    "temperature": 1.1,
    "min_p": 0.1,
    "top_k": 100,
    "top_p": 0.95,
    "repeat_penalty": 1.25,
    "presence_penalty": 0.4,
    "frequency_penalty": 0.0,
    "num_ctx": 131072,
    "num_predict": 4096,
}

# 模型目录由用户在「模型配置」中维护，保存在 MySQL 的 providers / catalog_models 表。
