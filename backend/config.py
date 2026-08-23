"""
全局配置 — 提供商、模型、数据库与默认生成参数。

所有提供商均使用 OpenAI 兼容接口调用。
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 路径
BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

# 从项目根目录加载 .env
load_dotenv(BASE_DIR.parent / ".env")

# ── API 提供商配置 ──
# base_url: OpenAI 兼容接口地址
# api_key_env: 环境变量名（无则依赖创建存档时传入的密钥）
# ollama_local 无需密钥，兼容端点要求占位 key
PROVIDER_CONFIG = {
    "deepseek": {
        "name": "DeepSeek 官方",
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "disable_thinking": {"extra_body": {"thinking": {"type": "disabled"}}},
    },
    "dashscope": {
        "name": "阿里云百炼官方",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "disable_thinking": {"extra_body": {"enable_thinking": False}},
    },
    "ollama_cloud": {
        "name": "Ollama Cloud",
        "base_url": "https://ollama.com/v1",
        "api_key_env": "OLLAMA_API_KEY",
        "disable_thinking": {"reasoning_effort": "none"},
    },
    "ollama_local": {
        "name": "Ollama 本地",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key_env": "",
        "dummy_api_key": "ollama",
        "disable_thinking": {"reasoning_effort": "none"},
    },
    "openai": {
        "name": "OpenAI 官方",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "disable_thinking": {"reasoning_effort": "none"},
    },
    "gemini": {
        "name": "Gemini 官方",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "disable_thinking": {"reasoning_effort": "none"},
    },
    "opencode": {
        "name": "opencode go 订阅",
        "base_url": "https://opencode.ai/zen/go/v1",
        "api_key_env": "OPENCODE_API_KEY",
        "disable_thinking": {"reasoning_effort": "none"},
    },
    "opencode_zen": {
        "name": "opencode Zen 免费",
        "base_url": "https://opencode.ai/zen/v1",
        "api_key_env": "OPENCODE_API_KEY",
        "disable_thinking": {"reasoning_effort": "none"},
    },
}

# 提供商展示顺序（前端提供商下拉的排序依据）
PROVIDER_ORDER = [
    "deepseek",
    "dashscope",
    "ollama_cloud",
    "ollama_local",
    "openai",
    "gemini",
    "opencode",
    "opencode_zen",
]

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

# ── 模型定义 ──
# key 格式: "{provider}:{模型ID}"，模型 ID 为各提供商接口的真实模型名（可能含冒号）
# provider: 对应 PROVIDER_CONFIG 中的键
MODEL_CONFIG = {
    # DeepSeek 官方
    "deepseek:deepseek-v4-flash": {"provider": "deepseek", "id": "deepseek-v4-flash", "max_tokens": 8192},
    "deepseek:deepseek-v4-pro": {"provider": "deepseek", "id": "deepseek-v4-pro", "max_tokens": 8192},
    # 阿里云百炼官方
    "dashscope:qwen-3.8-max": {"provider": "dashscope", "id": "qwen-3.8-max", "max_tokens": 8192},
    "dashscope:qwen-3.7-max": {"provider": "dashscope", "id": "qwen-3.7-max", "max_tokens": 8192},
    "dashscope:qwen-3.7-plus": {"provider": "dashscope", "id": "qwen-3.7-plus", "max_tokens": 8192},
    "dashscope:deepseek-v4-flash": {"provider": "dashscope", "id": "deepseek-v4-flash", "max_tokens": 8192},
    "dashscope:deepseek-v4-pro": {"provider": "dashscope", "id": "deepseek-v4-pro", "max_tokens": 8192},
    "dashscope:GLM-5.2": {"provider": "dashscope", "id": "GLM-5.2", "max_tokens": 8192},
    "dashscope:kimi-k3": {"provider": "dashscope", "id": "kimi-k3", "max_tokens": 8192},
    # Ollama Cloud
    "ollama_cloud:gemma4:31b-cloud": {"provider": "ollama_cloud", "id": "gemma4:31b-cloud", "max_tokens": 8192},
    "ollama_cloud:nemotron-3-super:cloud": {"provider": "ollama_cloud", "id": "nemotron-3-super:cloud", "max_tokens": 8192},
    "ollama_cloud:minimax-m2.5:cloud": {"provider": "ollama_cloud", "id": "minimax-m2.5:cloud", "max_tokens": 8192},
    "ollama_cloud:glm-4.7:cloud": {"provider": "ollama_cloud", "id": "glm-4.7:cloud", "max_tokens": 8192},
    "ollama_cloud:qwen3-next:80b-cloud": {"provider": "ollama_cloud", "id": "qwen3-next:80b-cloud", "max_tokens": 8192},
    "ollama_cloud:devstral-2:123b-cloud": {"provider": "ollama_cloud", "id": "devstral-2:123b-cloud", "max_tokens": 8192},
    "ollama_cloud:gpt-oss:120b-cloud": {"provider": "ollama_cloud", "id": "gpt-oss:120b-cloud", "max_tokens": 8192},
    "ollama_cloud:qwen3-vl:235b-instruct-cloud": {"provider": "ollama_cloud", "id": "qwen3-vl:235b-instruct-cloud", "max_tokens": 8192},
    "ollama_cloud:nemotron-3-ultra:cloud": {"provider": "ollama_cloud", "id": "nemotron-3-ultra:cloud", "max_tokens": 8192},
    "ollama_cloud:minimax-m3:cloud": {"provider": "ollama_cloud", "id": "minimax-m3:cloud", "max_tokens": 8192},
    # Ollama 本地
    "ollama_local:qwen3.8:27b": {"provider": "ollama_local", "id": "qwen3.8:27b", "max_tokens": 8192},
    "ollama_local:nemotron-3.5-lightning:30b": {"provider": "ollama_local", "id": "nemotron-3.5-lightning:30b", "max_tokens": 8192},
    "ollama_local:muse-glimmer:30b": {"provider": "ollama_local", "id": "muse-glimmer:30b", "max_tokens": 8192},
    "ollama_local:gemma4:e4b": {"provider": "ollama_local", "id": "gemma4:e4b", "max_tokens": 8192},
    "ollama_local:gemma4:31b": {"provider": "ollama_local", "id": "gemma4:31b", "max_tokens": 8192},
    # OpenAI 官方
    "openai:gpt-5.6-luna": {"provider": "openai", "id": "gpt-5.6-luna", "max_tokens": 8192},
    "openai:gpt-5.6-sol": {"provider": "openai", "id": "gpt-5.6-sol", "max_tokens": 8192},
    "openai:gpt-5.6-terra": {"provider": "openai", "id": "gpt-5.6-terra", "max_tokens": 8192},
    # Gemini 官方
    "gemini:gemini-3.7-flash": {"provider": "gemini", "id": "gemini-3.7-flash", "max_tokens": 8192},
    "gemini:gemini-3.6-flash": {"provider": "gemini", "id": "gemini-3.6-flash", "max_tokens": 8192},
    # opencode go 订阅
    "opencode:glm-5.3": {"provider": "opencode", "id": "glm-5.3", "max_tokens": 8192},
    "opencode:glm-5.2": {"provider": "opencode", "id": "glm-5.2", "max_tokens": 8192},
    "opencode:kimi-k3": {"provider": "opencode", "id": "kimi-k3", "max_tokens": 8192},
    "opencode:kimi-k2.6": {"provider": "opencode", "id": "kimi-k2.6", "max_tokens": 8192},
    "opencode:deepseek-v4-pro": {"provider": "opencode", "id": "deepseek-v4-pro", "max_tokens": 8192},
    "opencode:deepseek-v4-flash": {"provider": "opencode", "id": "deepseek-v4-flash", "max_tokens": 8192},
    "opencode:mimo-v2.5-pro": {"provider": "opencode", "id": "mimo-v2.5-pro", "max_tokens": 8192},
    "opencode:mimo-v2.5": {"provider": "opencode", "id": "mimo-v2.5", "max_tokens": 8192},
    "opencode:hy3": {"provider": "opencode", "id": "hy3", "max_tokens": 8192},
    # opencode Zen 免费（OpenAI 兼容，base_url: https://opencode.ai/zen/v1/）
    "opencode_zen:x-preview-f-free": {"provider": "opencode_zen", "id": "x-preview-f-free", "max_tokens": 8192},
    "opencode_zen:mimo-v2.5-free": {"provider": "opencode_zen", "id": "mimo-v2.5-free", "max_tokens": 8192},
    "opencode_zen:hy3-free": {"provider": "opencode_zen", "id": "hy3-free", "max_tokens": 8192},
    "opencode_zen:nemotron-3-ultra-free": {"provider": "opencode_zen", "id": "nemotron-3-ultra-free", "max_tokens": 8192},
    "opencode_zen:nemotron-3.5-lightning-free": {"provider": "opencode_zen", "id": "nemotron-3.5-lightning-free", "max_tokens": 8192},
    "opencode_zen:muse-spark-1.2-contributor-free": {"provider": "opencode_zen", "id": "muse-spark-1.2-contributor-free", "max_tokens": 8192},
}
