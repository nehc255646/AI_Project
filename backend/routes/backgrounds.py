"""
背景图路由 — 自定义全局背景的上传、列表与删除。

图片存放于 backend/backgrounds/ 目录，可手动放入文件，
也可通过 POST /api/backgrounds 上传；统一由 /backgrounds 静态挂载访问。
"""
from __future__ import annotations

import re
import time
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

from config import (
    BACKGROUNDS_DIR,
    BACKGROUND_ALLOWED_EXTS,
    BACKGROUND_MAX_SIZE,
)

router = APIRouter(prefix="/api/backgrounds", tags=["backgrounds"])
logger = logging.getLogger(__name__)

# 文件名白名单：字母数字、空格、中文常用字符与 ._-()[] 等，防止路径穿越
_SAFE_NAME_RE = re.compile(r"^[\w\u4e00-\u9fff .()\[\]-]+$")


def _ensure_dir() -> None:
    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)


def _resolve_safe(name: str) -> Path:
    """校验文件名并解析为目录内的安全路径（防路径穿越）。"""
    if not name or "/" in name or "\\" in name or not _SAFE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail={
            "code": "invalid_name",
            "message": "非法的文件名",
            "detail": "",
        })
    path = (BACKGROUNDS_DIR / name).resolve()
    if BACKGROUNDS_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail={
            "code": "invalid_name",
            "message": "非法的文件路径",
            "detail": "",
        })
    return path


@router.get("")
def list_backgrounds():
    """返回 backgrounds 目录下全部图片 [{name, url}]。"""
    _ensure_dir()
    items = []
    try:
        for f in sorted(BACKGROUNDS_DIR.iterdir(), key=lambda p: p.name.lower()):
            if f.is_file() and f.suffix.lower() in BACKGROUND_ALLOWED_EXTS:
                items.append({"name": f.name, "url": f"/backgrounds/{f.name}"})
    except OSError as e:
        logger.error(f"扫描背景图目录失败: {e}")
        raise HTTPException(status_code=500, detail={
            "code": "scan_failed",
            "message": "读取背景图目录失败",
            "detail": "",
        })
    return items


@router.post("")
async def upload_background(file: UploadFile = File(...)):
    """上传一张图片到 backgrounds 目录。"""
    _ensure_dir()

    # 扩展名校验
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in BACKGROUND_ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail={
            "code": "invalid_type",
            "message": f"仅支持图片格式: {', '.join(sorted(BACKGROUND_ALLOWED_EXTS))}",
            "detail": "",
        })

    # 读取并校验大小
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail={
            "code": "empty_file", "message": "文件内容为空", "detail": "",
        })
    if len(data) > BACKGROUND_MAX_SIZE:
        raise HTTPException(status_code=400, detail={
            "code": "too_large",
            "message": f"图片不能超过 {BACKGROUND_MAX_SIZE // (1024 * 1024)}MB",
            "detail": "",
        })

    # 生成安全文件名：时间戳前缀 + 清洗后的原名
    stem = Path(file.filename or "image").stem.strip() or "image"
    stem = _SAFE_NAME_RE.sub("", stem).strip() or "image"
    if len(stem) > 60:
        stem = stem[:60]
    name = f"{int(time.time())}_{stem}{suffix}"
    dest = BACKGROUNDS_DIR / name
    while dest.exists():  # 极端情况：同秒同名
        name = f"{int(time.time())}_{stem}_1{suffix}"
        dest = BACKGROUNDS_DIR / name

    try:
        dest.write_bytes(data)
    except OSError as e:
        logger.error(f"保存背景图失败: {e}")
        raise HTTPException(status_code=500, detail={
            "code": "save_failed", "message": "保存图片失败", "detail": "",
        })

    logger.info(f"背景图已上传: {name} ({len(data)} bytes)")
    return {"name": name, "url": f"/backgrounds/{name}"}


@router.delete("/{name:path}")
def delete_background(name: str):
    """删除指定背景图。"""
    path = _resolve_safe(name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail={
            "code": "not_found", "message": "背景图不存在", "detail": "",
        })
    if path.suffix.lower() not in BACKGROUND_ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail={
            "code": "invalid_type", "message": "仅允许删除图片文件", "detail": "",
        })
    try:
        path.unlink()
    except OSError as e:
        logger.error(f"删除背景图失败: {e}")
        raise HTTPException(status_code=500, detail={
            "code": "delete_failed", "message": "删除图片失败", "detail": "",
        })
    return {"ok": True}
