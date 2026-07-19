/**
 * Shared utility functions.
 *
 * DOM shortcuts and chat scroll.
 * Toast → toast.js, Confirm → confirm.js, Markdown → markdown.js
 */

// ── DOM shortcuts ──

export const $ = (sel) => document.querySelector(sel);
export const $$ = (sel) => document.querySelectorAll(sel);

// ── Chat scroll ──

export function scrollToBottom(smooth = true) {
  const el = document.getElementById("chat-messages");
  if (!el) return;
  if (smooth) {
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  } else {
    el.scrollTop = el.scrollHeight;
  }
}
