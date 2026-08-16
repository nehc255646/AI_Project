
# 后端运行说明

## 环境要求

- Python 3.14
- MySQL 8.0 或兼容版本
- Node.js 18 及以上（需要重新构建前端时使用）

## 配置环境变量

在项目根目录的 `.env` 或系统环境变量中设置：

```text
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的 MySQL 密码
MYSQL_DATABASE=ai_chat
```

模型 API Key 可按提供商设置，也可以在创建存档时单独填写：

```text
DEEPSEEK_API_KEY=
DASHSCOPE_API_KEY=
OLLAMA_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
OPENCODE_API_KEY=
```

## 启动方式

在项目根目录运行 `快速启动.bat`。该脚本直接启动后端并打开浏览器，不会重新构建前端。

首次运行、依赖变化或前端源码变化后，运行 `重置启动.bat`。该脚本会安装后端依赖、构建前端并启动服务。

服务默认只监听 `127.0.0.1:8000`，数据保存在 MySQL 中。项目没有内置用户认证，不建议将服务监听地址改为公网地址。

## 开发构建

```text
cd frontend
npm install
npm run dev
```

生产构建使用：

```text
npm run build
```
