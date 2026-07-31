/**
 * 通用工具函数 — DOM 快捷操作、HTML 转义与聊天滚动。
 */

// ── DOM 快捷操作 ──

export const $ = (sel) => document.querySelector(sel);
export const $$ = (sel) => document.querySelectorAll(sel);

// ── HTML 转义（防止注入） ──

export function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ── 聊天滚动 ──

export function scrollToBottom(smooth = true) {
  const el = document.getElementById("chat-messages");
  if (!el) return;
  // 流式输出时用瞬时滚动，避免 smooth 动画堆积造成卡顿
  if (smooth && !streamingFlag) {
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  } else {
    el.scrollTop = el.scrollHeight;
  }
}

let streamingFlag = false;
export function setStreamingFlag(val) {
  streamingFlag = val;
}
