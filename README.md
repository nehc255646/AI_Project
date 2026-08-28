# AI 对话智能体 — 存档版

> 10 个独立存档位 · 单模型 / 双模型 Role-Play · 流式 SSE · 用户自建 OpenAI 兼容供应商目录

一个开箱即用的本地 AI 对话应用：在「模型配置」里自行添加 OpenAI 兼容供应商、密钥与模型，存档只从目录中选择。支持单聊与双模型依次对话，完整存档备份与恢复。前端 Vite + 原生 JS，后端 FastAPI + MySQL。

---

## ✨ 功能特性

- **10 存档位**：每个存档独立的 `model / system_prompt / params / dual_config`，互不干扰
- **单 / 双模型**：单模型直聊；双模型（`model1` 🎭 + `model2` 🌟）按 `response_mode: both / model1 / model2` 与 `first_model` 依次回复，`pass_mode: user / assistant` 控制模型1的回复以何种身份透传给模型2
- **自建供应商目录**：右上角「模型配置」添加 OpenAI 兼容端点（提供商 ID、显示名称、基础 URL、密钥或环境变量、model-id）；创建存档时先选供应商再选模型
- **连通性测试**：每个已保存模型旁可发送 `hello` 探测是否能收到回复
- **模型热更换**：存档内 `🔄 更换模型`，`PATCH /api/slots/{id}/config` 原子更新，双模型两侧完全独立
- **流式对话**：`POST /api/chat` + `POST /slots/{id}/chat/continue` SSE 流，支持取消（`■`）与断点回滚，已落库回滚 `delete_messages_from`
- **继续回复**：单模型合并续写最后一条 assistant；双模型相当于用户留空让两位角色各再回复一轮
- **消息精细操作**：编辑（保存后自动重发）、删除（按 `id` 精确）、重新生成（单/双模型 `↻`，删除该轮及其后消息并重发）、清空对话
- **标题 / 参数**：侧栏标题原地编辑；密钥挂在供应商上（可填密钥或从指定环境变量读取，均可空）；调用只发送 OpenAI 标准参数 `temperature / top_p / presence_penalty / frequency_penalty / max_tokens`
- **导入导出**：导出 Markdown、导出可完整恢复的 JSON 备份（`GET /backup`）与导入（`POST /backup`）
- **并发保护**：内存 `asyncio.Lock` + MySQL `GET_LOCK(ai_chat_slot_*)`，`slot_busy` 友好提示；5xx/网络指数退避重试，流开始后不重试
- **开箱脚本**：`快速启动.bat`（端口检测、自动打开浏览器）、`重置启动.bat`（.venv、依赖、前端构建）

## 🧱 技术栈

- **后端**：Python 3.14 · FastAPI · Uvicorn · `openai` AsyncOpenAI · `httpx` · Pydantic · `pymysql` + `DBUtils.PooledDB` · `python-dotenv`
- **前端**：Vite 6 · 原生 ESM · `marked` · `highlight.js`（按需）
- **存储**：MySQL 8（`providers` + `catalog_models` + `slots` + `messages`）
- **协议**：OpenAI 兼容 `chat.completions`（用户自填 `base_url`）

## 📂 目录结构

```
AI_project/
├─ backend/
│  ├─ main.py            # FastAPI 入口，lifespan 初始化 AIClient/SlotManager，托管 frontend/dist
│  ├─ config.py          # MySQL / 槽位 / 默认生成参数
│  ├─ clients.py         # AIClient.stream_chat / test_hello
│  ├─ session_manager.py # SlotManager + 供应商/模型目录 CRUD
│  ├─ routes/ {slots,chat,models,catalog,backgrounds}.py
│  ├─ models.py          # Pydantic 请求/响应（含 UpdateSlotRequest）
│  └─ state.py           # 全局单例
├─ frontend/
│  ├─ index.html         # 10宫格存档视图 + 聊天视图 + 侧栏 + 6步向导 + 帮助弹窗
│  ├─ js/ {main,api,state,ui,modals,chat,catalog,markdown,confirm,toast,utils}.js
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

# 可选：在「模型配置」里勾选「从环境变量读取」后，把变量名配成你这里设置的名字
# MYPROVIDER_API_KEY=sk-xxxx
```
2. **首次 / 依赖变化后**：双击 `重置启动.bat`（创建 `.venv`、装依赖、构建前端、启动 `127.0.0.1:8000`）
3. **日常启动**：双击 `快速启动.bat`（检测 8000 占用、直接起后端、自动打开浏览器）

生产默认 `UVICORN_RELOAD=0`，需热重载：`set UVICORN_RELOAD=1 && 快速启动.bat`。

## ⚙️ 提供商与模型

不再内置供应商清单。打开右上角「模型配置」自行添加：

1. 提供商 ID（小写字母/数字/连字符/下划线，创建后不可改）
2. 显示名称、基础 URL（OpenAI 兼容，如 `https://api.example.com/v1` 或本地 `http://127.0.0.1:11434/v1`）
3. API 密钥（可空）或勾选从环境变量读取并填写变量名
4. 一条或多条模型：`model-id`（发给接口的真实名称）+ 显示名称
5. 保存后可点模型旁的「测试」发送 `hello`

存档引用的模型 key 形如 `{slug}:{model_id}`。被存档引用的供应商/模型不能删除。导入备份前须先在目录中建好对应模型。

## 🔌 API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/models` | 目录中的模型列表 |
| `GET` | `/api/env-check` | 各供应商运行时密钥是否可解析 |
| `GET` | `/api/providers` | 供应商列表（密钥仅掩码） |
| `POST` | `/api/providers` | 创建供应商（可带 models[]） |
| `PATCH` | `/api/providers/{id}` | 更新供应商（不可改 slug） |
| `DELETE` | `/api/providers/{id}` | 删除（无存档引用时） |
| `POST` | `/api/providers/{id}/models` | 添加模型 |
| `PATCH` | `/api/providers/{id}/models/{mid}` | 更新模型 |
| `DELETE` | `/api/providers/{id}/models/{mid}` | 删除模型 |
| `POST` | `/api/providers/{id}/models/{mid}/test` | 非流式 hello 测试 |
| `GET` | `/api/default-params` | 默认生成参数 |
| `GET` | `/api/slots` | 10 位列表（含 `message_count / dual_enabled`） |
| `POST` | `/api/slots/{i}` | 创建存档（`CreateSlotRequest`，含双模型分支） |
| `DELETE` | `/api/slots/{i}` | 删除存档（`CASCADE` 消息） |
| `GET` | `/api/slots/{i}/chat` | 存档详情 + `history[{id,role,content,source}]` |
| `POST` | `/api/slots/{i}/chat/clear` | 清空对话 |
| `DELETE` | `/api/slots/{i}/chat/messages` | 删消息（优先 `from_id`，回退 `from_index/to_index` → `delete_messages_by_ids`） |
| `PATCH` | `/api/slots/{i}/chat/messages` | 编辑消息（`message_id` 优先） |
| `PATCH` | `/api/slots/{i}/title` | 改标题 |
| `PATCH` | `/api/slots/{i}/api-key` | 已废弃（410，密钥改在模型配置） |
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
- **目录** `frontend/js/catalog.js`：右上角模型配置弹层，增删改供应商/模型，测试 hello
- **向导** `frontend/js/modals.js:1`：6 步（0 模式 → 1 模型 → 2 参数 → 3 提示词/模型2 → 4 模型2参数 → 5 标题），目录为空时不可创建；编辑态 `openEditModal` 复用并隐藏 `step0`
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
- **没有可选模型**：先在右上角「模型配置」添加供应商和模型
- **本地 Ollama**：基础 URL 填 `http://127.0.0.1:11434/v1`，密钥可留空；需服务常驻且已 `ollama pull`
- **API 401**：在模型配置中检查该供应商的密钥或环境变量；可用模型旁的「测试」按钮排查
- **流式中断**：已开始后中断不重试（防重复），前端提示“回复生成中途中断，请重试”；可点 `⏩继续` 或重新发送
- **端口占用**：`快速启动.bat` 检测 8000 `LISTENING`，若占用则直接打开现有服务

## 📄 许可

未声明许可证，仅供本地个人使用。勿将服务暴露到公网（无鉴权）。

---

> 构建自 `backend/config.py:1` · `backend/clients.py:1` · `backend/session_manager.py:1` · `frontend/index.html:1`
