"""
FastAPI server — AI Chat Agent.

Entry point: sets up middleware, registers routers, serves static files.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import FRONTEND_DIR
from clients import AIClient
from session_manager import SlotManager
from state import init as init_state
from routes.slots import router as slots_router
from routes.chat import router as chat_router
from routes.models import router as models_router

# ── Logging ──

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ai_client = AIClient()
        slot_mgr = SlotManager()
        init_state(ai_client, slot_mgr)
        logger.info("服务初始化完成")
    except RuntimeError as e:
        logger.critical(f"服务启动失败: {e}")
        raise
    except Exception as e:
        logger.critical(f"服务初始化时发生意外错误: {e}", exc_info=True)
        raise
    yield


app = FastAPI(title="AI 对话智能体 - 存档版", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ──

app.include_router(slots_router)
app.include_router(chat_router)
app.include_router(models_router)


# ── Global exception handler for structured errors (#14) ──


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": "error", "message": str(exc.detail), "detail": ""},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": "internal_error",
            "message": "服务器内部错误",
            "detail": str(exc),
        },
    )


# ── Serve frontend static files ──
# Priority: dist/ (Vite production build) → frontend/ (dev / raw)
dist_dir = FRONTEND_DIR / "dist"
if dist_dir.is_dir() and list(dist_dir.iterdir()):
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")
    logger.info(f"已挂载前端静态文件: {dist_dir}")
elif FRONTEND_DIR.is_dir():
    app.mount(
        "/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend"
    )
    logger.info(f"已挂载前端开发文件: {FRONTEND_DIR}")
else:
    logger.warning(f"前端目录不存在: {FRONTEND_DIR}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
