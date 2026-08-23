# AI 对话智能体 — 存档版

> 10 个独立存档位 · 单模型 / 双模型 Role-Play · 流式 SSE · 模型热更换 · OpenAI 兼容多提供商

一个开箱即用的本地 AI 对话应用：每个存档独立绑定提供商、模型、提示词与参数，支持单聊与双模型依次对话，完整存档备份与恢复。前端 Vite + 原生 JS，后端 FastAPI + MySQL，全部走 OpenAI 兼容接口。

---

## ✨ 功能特性

- **10 存档位**：每个存档独立的 `model / system_prompt / api_key / params / dual_config`，互不干扰
- **单 / 双模型**：单模型直聊；双模型（`model1` 🎭 + `model2` 🌟）按 `response_mode: both / model1 / model2` 与 `first_model` 依次回复，`pass_mode: user / assistant` 控制模型1的回复以何种身份透传给模型2
- **提供商-模型二级选择**：先选提供商（DeepSeek / 阿里云百炼 / Ollama Cloud / Ollama 本地 / OpenAI / Gemini / opencode go / opencode Zen 免费），再选该提供商下的模型
- **模型热更换**：存档内 `🔄 更换模型`，`PATCH /api/slots/{id}/config` 原子更新，双模型两侧完全独立
- **流式对话**：`POST /api/chat` + `POST /slots/{id}/chat/continue` SSE 流，支持取消（`■`）与断点回滚，已落库回滚 `delete_messages_from`
- **继续回复**：单模型合并续写最后一条 assistant；双模型相当于用户留空让两位角色各再回复一轮
- **消息精细操作**：编辑（保存后自动重发）、删除（按 `id` 精确）、重新生成（单/双模型 `↻`，删除该轮及其后消息并重发）、清空对话
- **标题 / 密钥 / 参数**：侧栏标题原地编辑；密钥存档级绑定（环境变量优先，Ollama 本地免密钥）；`temperature / top_p / min_p / top_k / repeat_penalty / presence_penalty / frequency_penalty / num_ctx / num_predict` + DeepSeek `thinking_enabled` 可选
- **导入导出**：导出 Markdown、导出可完整恢复的 JSON 备份（`GET /backup`）与导入（`POST /backup`）
- **并发保护**：内存 `asyncio.Lock` + MySQL `GET_LOCK(ai_chat_slot_*)`，`slot_busy` 友好提示；5xx/网络指数退避重试，流开始后不重试
- **开箱脚本**：`快速启动.bat`（端口检测、自动打开浏览器）、`重置启动.bat`（.venv、依赖、前端构建）

## 🧱 技术栈

- **后端**：Python 3.14 · FastAPI · Uvicorn · `openai` AsyncOpenAI · `httpx` · Pydantic · `pymysql` + `DBUtils.PooledDB` · `python-dotenv`
- **前端**：Vite 6 · 原生 ESM · `marked` · `highlight.js`（按需）
- **存储**：MySQL 8（`slots` + `messages`，`params / dual_config` JSON）
- **协议**：全部 OpenAI 兼容 `base_url`，`extra_body: thinking / enable_thinking / reasoning_effort / min_p / top_k / num_ctx / repeat_penalty` 按提供商白名单透传

## 📂 目录结构

```
AI_project/
├─ backend/
│  ├─ main.py            # FastAPI 入口，lifespan 初始化 AIClient/SlotManager，托管 frontend/dist
│  ├─ config.py          # PROVIDER_CONFIG / PROVIDER_ORDER / MODEL_CONFIG / DEFAULT_PARAMS
│  ├─ clients.py         # AIClient.stream_chat（重试、密钥解析、思考开关）
│  ├─ session_manager.py # SlotManager（PooledDB、建库建表、CRUD + update_slot）
│  ├─ routes/ {slots,chat,models}.py
│  ├─ models.py          # Pydantic 请求/响应（含 UpdateSlotRequest）
│  └─ state.py           # 全局单例
├─ frontend/
│  ├─ index.html         # 10宫格存档视图 + 聊天视图 + 侧栏 + 6步向导 + 帮助弹窗
│  ├─ js/ {main,api,state,ui,modals,chat,markdown,confirm,toast,utils}.js
│  ├─ css/ (variables/base/sidebar/slots/chat/modals/...)
│  └─ vite.config.js     # dev 5173 proxy /api → 8000，build dist
├─ 快速启动.bat
├─ 重置启动.bat
└─ .env                  # 本地 env 模板（被 .gitignore 忽略）
```

## 🚀 快速开始（Windows）

> 要求：Python 3.14、`MySQL 8` 已启动、Node.js 18+（仅重置/开发需要）

1. **配置环境变量**（系统环境变量或项目根 `.env`）：
```ini
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的密码   # 必填
MYSQL_DATABASE=ai_chat

# 按需，任选其一：系统级（全部存档共用）或存档级（创建时填写）
DEEPSEEK_API_KEY=sk-xxxx
DASHSCOPE_API_KEY=sk-xxxx
OLLAMA_API_KEY=xxxx            # Ollama Cloud
OPENAI_API_KEY=sk-xxxx
GEMINI_API_KEY=AIza-xxxx
OPENCODE_API_KEY=sk-xxxx        # 同时用于 opencode go 与 opencode Zen 免费
# 兼容旧变量 OPENCODE_ZEN_API_KEY 仍可识别
```
2. **首次 / 依赖变化后**：双击 `重置启动.bat`（创建 `.venv`、装依赖、构建前端、启动 `127.0.0.1:8000`）
3. **日常启动**：双击 `快速启动.bat`（检测 8000 占用、直接起后端、自动打开浏览器）

生产默认 `UVICORN_RELOAD=0`，需热重载：`set UVICORN_RELOAD=1 && 快速启动.bat`。

## ⚙️ 提供商与模型

| 提供商 | `PROVIDER_CONFIG` key | `base_url` | `api_key_env` | 模型示例 |
|---|---|---|---|---|
| DeepSeek 官方 | `deepseek` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` | `deepseek-v4-flash`, `deepseek-v4-pro`（支持 `thinking_enabled`） |
| 阿里云百炼 | `dashscope` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` | `qwen-3.8-max / 3.7-max / 3.7-plus`, `GLM-5.2`, `kimi-k3`, `deepseek-v4-*` |
| Ollama Cloud | `ollama_cloud` | `https://ollama.com/v1` | `OLLAMA_API_KEY` | `minimax-m3:cloud`, `nemotron-3-ultra:cloud`, `glm-4.7:cloud` 等 |
| Ollama 本地 | `ollama_local` | `http://127.0.0.1:11434/v1` | —（`dummy_api_key: ollama`） | `qwen3.8:27b`, `gemma4:31b` 等（需 `ollama pull` 且服务常驻） |
| OpenAI 官方 | `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` | `gpt-5.6-luna / sol / terra` |
| Gemini 官方 | `gemini` | `https://generativelanguage.googleapis.com/v1beta/openai/` | `GEMINI_API_KEY` | `gemini-3.7-flash`, `gemini-3.6-flash` |
| opencode go 订阅 | `opencode` | `https://opencode.ai/zen/go/v1` | `OPENCODE_API_KEY` | `glm-5.3 / 5.2`, `kimi-k3 / k2.6`, `mimo-v2.5*`, `hy3` |
| **opencode Zen 免费** | `opencode_zen` | `https://opencode.ai/zen/v1` | `OPENCODE_API_KEY`（与 go 共用） | `x-preview-f-free` (Ox Alpha Free), `mimo-v2.5-free`, `hy3-free`, `nemotron-3-ultra-free`, `nemotron-3.5-lightning-free`, `muse-spark-1.2-contributor-free` — 全部 `chat/completions` 兼容 |

> 全部 OpenAI 兼容；非 DeepSeek 模型全局 `disable_thinking: reasoning_effort=none`；`min_p/top_k` 仅对 `deepseek/dashscope`（+ Ollama 的 `num_ctx/repeat_penalty`）透传。

## 🔌 API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/models` | 模型列表（按 `PROVIDER_ORDER` 排序） |
| `GET` | `/api/env-check` | 各 `api_key_env` 是否已配置 |
| `GET` | `/api/default-params` | 默认生成参数 |
| `GET` | `/api/slots` | 10 位列表（含 `message_count / dual_enabled`） |
| `POST` | `/api/slots/{i}` | 创建存档（`CreateSlotRequest`，含双模型分支） |
| `DELETE` | `/api/slots/{i}` | 删除存档（`CASCADE` 消息） |
| `GET` | `/api/slots/{i}/chat` | 存档详情 + `history[{id,role,content,source}]` |
| `POST` | `/api/slots/{i}/chat/clear` | 清空对话 |
| `DELETE` | `/api/slots/{i}/chat/messages` | 删消息（优先 `from_id`，回退 `from_index/to_index` → `delete_messages_by_ids`） |
| `PATCH` | `/api/slots/{i}/chat/messages` | 编辑消息（`message_id` 优先） |
| `PATCH` | `/api/slots/{i}/title` | 改标题 |
| `PATCH` | `/api/slots/{i}/api-key` | 补密钥（`target: model1 / model2`） |
| `PATCH` | `/api/slots/{i}/dual-toggle` | 切 `response_mode / first_model` |
| `PATCH` | `/api/slots/{i}/config` | **模型更换**（`UpdateSlotRequest`，双模型两侧独立） |
| `POST` | `/api/chat` | 流式对话 `SSE`（单/双分流，自动回滚） |
| `POST` | `/api/slots/{i}/chat/continue` | 继续回复（单合并、双各新增一轮） |
| `GET` | `/api/slots/{i}/chat/export` | 导出 Markdown 数据 |
| `GET` | `/api/slots/{i}/backup` | 导出完整 JSON 备份 |
| `POST` | `/api/slots/{i}/backup` | 导入备份到空位 |

错误统一 `HTTPException {code, message, detail}`，前端映射为中文 Toast / 内联卡片。

## 🖥️ 前端要点

- **状态** `frontend/js/state.js:5`：`view / slots / currentSlotIndex / currentSlotData / streaming / dualEnabled / responseMode / firstModel`
- **API** `frontend/js/api.js:12`：`apiFetch` 指数退避（4xx 不重试，5xx/网络重试）
- **向导** `frontend/js/modals.js:1`：6 步（0 模式 → 1 模型 → 2 参数 → 3 提示词/模型2 → 4 模型2参数 → 5 标题），编辑态 `openEditModal` 复用并隐藏 `step0`，`🔄更换模型` 单双独立提交 `PATCH /config`
- **对话** `frontend/js/chat.js:1`：`sendMessage / continueLastReply / cancelStream / regenerate / editAndResend`，60s 空闲超时，`model_start / chunk / model_done / done / error` 事件分派，`model2` 通过 `pass_mode` 拼接
- **UI** `frontend/js/ui.js:1`：宫格、消息气泡（含 `model-label-bar`）、侧栏信息、流式态、错误重试按钮

## 🛠️ 开发

```bash
# 前端开发（自动代理 /api → 8000）
cd frontend
npm install
npm run dev      # http://localhost:5173

# 后端开发
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
# 或设置 UVICORN_RELOAD=1 后运行 快速启动.bat

# 生产构建
cd frontend
npm run build    # 输出 frontend/dist，backend 启动时优先托管
```

## ❓ 常见问题

- **MySQL 连不上**：确认 `MYSQL_PASSWORD` 已设、`MySQL` 服务运行、`MYSQL_HOST/PORT` 正确；启动时自动 `CREATE DATABASE ai_chat CHARACTER SET utf8mb4`
- **Ollama 本地无法使用**：确认 `http://127.0.0.1:11434` 可访问且已 `ollama pull <model>`；本地 provider 无需密钥
- **API 401**：检查对应 `*_API_KEY` 是否正确，可先用存档级密钥测试；`opencode` 与 `opencode_zen` 共用 `OPENCODE_API_KEY`
- **流式中断**：已开始后中断不重试（防重复），前端提示“回复生成中途中断，请重试”；可点 `⏩继续` 或重新发送
- **端口占用**：`快速启动.bat` 检测 8000 `LISTENING`，若占用则直接打开现有服务

## 📄 许可

未声明许可证，仅供本地个人使用。勿将服务暴露到公网（无鉴权）。

---

> 构建自 `backend/config.py:1` · `backend/clients.py:1` · `backend/session_manager.py:1` · `frontend/index.html:1`
