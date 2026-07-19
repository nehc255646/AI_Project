/**
 * UI rendering functions.
 *
 * Handles view switching, slot grid rendering, message rendering,
 * sidebar updates, and streaming status indicator.
 *
 * Changes:
 *   - renderMessages now passes message IDs and creates regenerate buttons
 *     for loaded history (fix: 重载后重试按钮不再消失)
 *   - addMessage uses messageId instead of msgIndex for data attributes
 */

import { state } from "./state.js";
import { apiGet } from "./api.js";
import { $, scrollToBottom } from "./utils.js";
import { showToast } from "./toast.js";
import { renderMarkdown, enhanceCodeBlocks } from "./markdown.js";
import { openCreateModal } from "./modals.js";
import { deleteSlotAction, openSlot, editAndResend } from "./chat.js";

// ── DOM refs (lazily resolved) ──

function el(id) {
  return document.getElementById(id);
}

// ── View switching ──

export function showSlotView() {
  state.view = "slots";
  el("slot-view").classList.remove("hidden");
  el("chat-view").classList.add("hidden");
  el("sidebar").style.display = "none";
  loadSlots();
}

export function showChatView() {
  state.view = "chat";
  el("slot-view").classList.add("hidden");
  el("chat-view").classList.remove("hidden");
  el("sidebar").style.display = "flex";
  updateSidebarInfo();
}

// ── Slot grid ──

export async function loadSlots() {
  try {
    state.slots = await apiGet("/api/slots");
  } catch (e) {
    state.slots = new Array(10).fill(null);
    showToast("加载存档失败: " + e.message, "error");
  }
  renderSlotGrid();
}

export function renderSlotGrid() {
  const grid = el("slot-grid");
  if (!grid) return;
  grid.innerHTML = "";

  for (let i = 0; i < 10; i++) {
    const info = state.slots[i];
    const card = document.createElement("div");
    card.className = "slot-card";

    if (info === null || info === undefined) {
      // Empty slot
      card.classList.add("empty");
      card.innerHTML = `
        <div class="slot-plus">+</div>
        <div class="slot-empty-label">空存档</div>
        <div class="slot-index-label">存档 #${i + 1}</div>
      `;
      card.addEventListener("click", () => openCreateModal(i));
    } else {
      // Used slot
      card.classList.add("used");
      const displayTitle = info.title || `存档 #${i + 1}`;

      const fmtTime = (iso) => {
        if (!iso) return "";
        try {
          return new Date(iso).toLocaleString("zh-CN", {
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          });
        } catch (_) {
          return "";
        }
      };
      const created = fmtTime(info.created_at);
      const updated = fmtTime(info.updated_at);

      card.innerHTML = `
        <button class="slot-delete-btn" data-index="${i}" title="删除存档">✕</button>
        <div class="slot-card-content">
          <div class="slot-title">${displayTitle.slice(0, 20)}</div>
          <div class="slot-model-badge">${info.model || "未知"}</div>
          <div class="slot-time"><span class="slot-time-label">创建</span><span class="slot-time-value">${created || "未知"}</span></div>
          <div class="slot-time"><span class="slot-time-label">使用</span><span class="slot-time-value">${updated || "未知"}</span></div>
        </div>
      `;

      card.addEventListener("click", (e) => {
        if (e.target.closest(".slot-delete-btn")) return;
        openSlot(i);
      });

      const delBtn = card.querySelector(".slot-delete-btn");
      delBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteSlotAction(i);
      });
    }

    grid.appendChild(card);
  }
}

// ── Chat messages ──

export function showEmptyState() {
  const container = el("chat-messages");
  if (!container) return;
  if (!container.querySelector(".message")) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">✦</div>
        <div class="empty-title">开始新的对话</div>
        <div class="empty-desc">在下方输入消息，与 AI 开始交流</div>
      </div>
    `;
  }
}

export function renderMessages(history) {
  const container = el("chat-messages");
  if (!container) return;
  container.innerHTML = "";

  if (!history || history.length === 0) {
    showEmptyState();
    return;
  }

  let lastUserMsgId = null;

  history.forEach((msg) => {
    const isUser = msg.role === "user";
    const messageId = msg.id || null;

    // addMessage 会在元素上设置 data-message-id
    const bubble = addMessage(isUser ? "user" : "assistant", msg.content, false, messageId);

    if (isUser) {
      lastUserMsgId = messageId;
    }

    // 为 assistant 消息添加重试按钮（带上对应的 user message id）
    if (!isUser && lastUserMsgId !== null) {
      const msgDiv = bubble ? bubble.closest(".message") : null;
      if (msgDiv) {
        let regenBtn = msgDiv.querySelector(".regenerate-btn");
        if (!regenBtn) {
          regenBtn = document.createElement("button");
          regenBtn.className = "regenerate-btn";
          regenBtn.textContent = "↻";
          regenBtn.title = "重新生成";
          msgDiv.appendChild(regenBtn);
        }
        regenBtn.dataset.userMsgId = lastUserMsgId;
      }
    }
  });
}

export function addMessage(role, content, isStreaming = false, messageId = null) {
  const container = el("chat-messages");
  if (!container) return null;

  // Remove empty state if present
  const empty = container.querySelector(".empty-state");
  if (empty) empty.remove();

  const div = document.createElement("div");
  div.className = `message ${role}`;
  if (messageId !== null) {
    div.dataset.messageId = messageId;
  }

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "👤" : "🤖";
  avatar.setAttribute("aria-hidden", "true");

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (isStreaming) bubble.classList.add("streaming");

  // Streaming 消息在流式过程中用 textContent（增量写入），
  // 完成后由 chat.js 替换为 renderMarkdown
  if (role === "user") {
    bubble.textContent = content;
  } else if (!isStreaming) {
    // 非流式（历史加载）直接渲染 Markdown
    bubble.innerHTML = renderMarkdown(content);
    enhanceCodeBlocks(bubble);
  }
  // isStreaming && assistant: bubble 为空，等待流式 chunk 写入

  div.appendChild(avatar);
  div.appendChild(bubble);

  if (role === "user") {
    const editBtn = document.createElement("button");
    editBtn.className = "user-edit-btn";
    editBtn.textContent = "✏️";
    editBtn.title = "编辑消息";
    editBtn.addEventListener("click", () => editAndResend(div));
    div.appendChild(editBtn);
  }

  container.appendChild(div);
  scrollToBottom();
  return bubble;
}

export function updateMessage(bubble, content) {
  if (!bubble) return;
  if (bubble.classList.contains("streaming")) {
    bubble.textContent = content;
  } else {
    bubble.innerHTML = renderMarkdown(content);
    enhanceCodeBlocks(bubble);
  }
}

export function finishStreaming(bubble) {
  if (!bubble) return;
  bubble.classList.remove("streaming");
}

// ── Sidebar ──

export function updateSidebarInfo() {
  const idx = state.currentSlotIndex;
  if (idx === null) return;

  el("slot-number-display").textContent = `存档 #${idx + 1}`;
  if (state.currentSlotData) {
    const title = state.currentSlotData.title || "未命名";
    el("slot-title-text").textContent = title;
    el("slot-model-display").textContent = state.currentSlotData.model || "-";
    el("slot-prompt-display").textContent = state.currentSlotData.system_prompt || "-";
  }

  el("chat-slot-badge").textContent = `存档 #${idx + 1}`;
  el("current-model-badge").textContent = state.currentSlotData
    ? state.currentSlotData.model || ""
    : "";
}

export function openSidebar() {
  el("sidebar").classList.add("open");
  el("sidebar-overlay").classList.add("active");
}

export function closeSidebar() {
  el("sidebar").classList.remove("open");
  el("sidebar-overlay").classList.remove("active");
}

// ── Streaming status indicator ──

export function setStreaming(val) {
  state.streaming = val;
  const sendBtn = el("send-btn");
  const cancelBtn = el("cancel-stream-btn");
  const statusBadge = el("streaming-status-badge");
  const inputStatus = el("input-status");
  const messageInput = el("message-input");

  if (sendBtn) sendBtn.disabled = val;
  if (sendBtn) sendBtn.classList.toggle("sending", val);
  if (cancelBtn) cancelBtn.classList.toggle("hidden", !val);
  if (statusBadge) statusBadge.classList.toggle("hidden", !val);
  if (inputStatus) {
    inputStatus.textContent = val
      ? "AI 正在回复…"
      : "AI 可能会犯错，请验证重要信息";
  }
  if (messageInput) messageInput.disabled = val;
}

// ── Add error message to chat ──

export function addErrorMessage(content) {
  const container = el("chat-messages");
  if (!container) return;

  const empty = container.querySelector(".empty-state");
  if (empty) empty.remove();

  const div = document.createElement("div");
  div.className = "message error";
  div.innerHTML = `<div class="bubble">⚠️ ${content}</div>`;
  container.appendChild(div);
  scrollToBottom();
}
