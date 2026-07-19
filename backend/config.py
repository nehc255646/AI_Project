import os
from pathlib import Path
from dotenv import load_dotenv

# Paths
BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

# 从项目根目录加载 .env（而非 backend/ 下）
load_dotenv(BASE_DIR.parent / ".env")

# API Keys
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# Ollama
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_CLOUD_URL = "https://ollama.com/api/chat"

# Limits
CONTEXT_WINDOW_SIZE = 100   # 每次传给 AI 模型的消息数（上下文窗口）
SLOT_COUNT = 10

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

# Model definitions
MODEL_CONFIG = {
    "DeepSeek-v4-flash": {
        "id": "deepseek-v4-flash",
        "provider": "deepseek",
        "max_tokens": 8192,
        "thinking_disabled": True,
    },
    "DeepSeek-v4-Pro": {
        "id": "deepseek-v4-pro",
        "provider": "deepseek",
        "max_tokens": 8192,
        "thinking_disabled": True,
    },
    "Qwen3.6-Flash": {
        "id": "qwen3.6-flash",
        "provider": "dashscope",
        "max_tokens": 4096,
        "thinking_disabled": True,
    },
    "Qwen3.7-Max": {
        "id": "qwen3.7-max",
        "provider": "dashscope",
        "max_tokens": 8192,
        "thinking_disabled": True,
    },
    "Minimax-M3": {
        "id": "minimax-m3:cloud",
        "provider": "ollama",
        "max_tokens": 8192,
        "thinking_disabled": True,
    },
    "Nemotron-3-Ultra": {
        "id": "nemotron-3-ultra:cloud",
        "provider": "ollama",
        "max_tokens": 8192,
        "thinking_disabled": True,
    },
}
