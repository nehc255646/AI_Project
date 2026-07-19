/**
 * Chat logic — send, receive SSE stream, regenerate, abort.
 *
 * Changes:
 *   - 移除了文件上传功能
 *   - 改用 JSON POST（取代 FormData）
 *   - 流式渲染使用增量 textContent（修复 O(n²)）
 *   - SSE done 事件返回 user_message_id / assistant_message_id
 *   - regenerate 使用消息 ID 定位（取代脆弱的 DOM 位置计数）
 *   - 编辑消息也使用 data-message-id
 *   - 移除了 getHistoryIndex()
 */

import { state } from "./state.js";
import { apiGet, apiPost, apiDelete, apiPatch } from "./api.js";
import {
  $,
  scrollToBottom,
} from "./utils.js";
import { showToast } from "./toast.js";
import { showConfirm } from "./confirm.js";
import { renderMarkdown, enhanceCodeBlocks } from "./markdown.js";
import {
  showSlotView,
  showChatView,
  showEmptyState,
  renderMessages,
  addMessage,
  finishStreaming,
  updateSidebarInfo,
  setStreaming,
  addErrorMessage,
  loadSlots,
} from "./ui.js";

// ── Open a slot ──

export async function openSlot(index) {
  state.currentSlotIndex = index;

  try {
    const data = await apiGet(`/api/slots/${index}/chat`);
    state.currentSlotData = data;
    showChatView();
    renderMessages(data.history || []);
    showToast("已进入存档 #" + (index + 1), "success");
  } catch (e) {
    showToast("加载存档失败: " + e.message, "error");
  }
}

// ── Delete a slot ──

export async function deleteSlotAction(index) {
  const confirmed = await showConfirm(
    `确定要删除存档 #${index + 1} 吗？所有对话将永久丢失。`,
    true
  );
  if (!confirmed) return;

  try {
    await apiDelete(`/api/slots/${index}`);
    if (state.currentSlotIndex === index) {
      backToSlots();
    } else {
      loadSlots();
    }
    showToast("存档已删除", "success");
  } catch (e) {
    showToast("删除失败: " + e.message, "error");
  }
}

// ── Back to slot view ──

export function backToSlots() {
  if (state.streaming) {
    if (state.abortController) state.abortController.abort();
    setStreaming(false);
  }
  state.currentSlotIndex = null;
  state.currentSlotData = null;
  document.getElementById("chat-messages").innerHTML = "";
  closeSidebar();
  showSlotView();
}

// ── Clear chat ──

export async function clearSlotChat() {
  if (state.streaming) {
    showToast("请等待当前回复完成", "warning");
    return;
  }

  const idx = state.currentSlotIndex;
  if (idx === null) return;

  const container = document.getElementById("chat-messages");
  const empty = !container.querySelector(".message");
  if (empty) return;

  const confirmed = await showConfirm("确定要清空当前存档的所有对话吗？");
  if (!confirmed) return;

  try {
    await apiPost(`/api/slots/${idx}/chat/clear`, {});
    const data = await apiGet(`/api/slots/${idx}/chat`);
    state.currentSlotData = data;
    container.innerHTML = "";
    showEmptyState();
    showToast("对话已清空", "success");
  } catch (e) {
    showToast("清空失败: " + e.message, "error");
  }
}

// ── Send message (SSE, JSON) ──

export async function sendMessage() {
  const input = document.getElementById("message-input");
  const text = input.value.trim();

  if (!text || state.streaming) return;
  if (state.currentSlotIndex === null) return;

  input.value = "";
  input.style.height = "auto";

  // 添加用户消息气泡
  addMessage("user", text, false);

  setStreaming(true);
  state.abortController = new AbortController();
  state.streamCancelled = false;
  state.currentReader = null;

  // 添加 AI 占位气泡
  const bubble = addMessage("assistant", "", true);
  const msgDiv = bubble ? bubble.closest(".message") : null;
  let idleCheck = null;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slot_index: state.currentSlotIndex,
        message: text,
      }),
      signal: state.abortController.signal,
    });

    if (!response.ok) {
      let errMsg = `请求失败: ${response.status}`;
      try {
        const err = await response.json();
        errMsg = err.message || errMsg;
      } catch (_) { /* ignore */ }
      throw new Error(errMsg);
    }

    const reader = response.body.getReader();
    state.currentReader = reader;
    const decoder = new TextDecoder();
    let buffer = "";
    let fullContent = "";
    let lastChunkTime = Date.now();
    const IDLE_TIMEOUT = 60_000;
    idleCheck = setInterval(() => {
      if (Date.now() - lastChunkTime > IDLE_TIMEOUT) {
        state.abortController?.abort();
        showToast("响应超时：长时间未收到数据", "error");
        clearInterval(idleCheck);
      }
    }, 10_000);

    let userMessageId = null;
    let assistantMessageId = null;

    while (true) {
      const { done, value } = await reader.read();
      if (state.streamCancelled || done) {
        clearInterval(idleCheck); idleCheck = null;
        break;
      }
      lastChunkTime = Date.now();

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;

        try {
          const event = JSON.parse(line.slice(6));
          const { type, content, code } = event;

          switch (type) {
            case "chunk":
              fullContent += content;
              // 增量写入 textContent（避免 O(n²)）
              bubble.textContent += content;
              scrollToBottom();
              break;

            case "done":
              userMessageId = event.user_message_id;
              assistantMessageId = event.assistant_message_id;

              // 标记消息 ID
              // 用户消息是倒数第二个 .message （刚刚添加的）
              const allMsgs = document.querySelectorAll("#chat-messages > .message");
              const userDiv = allMsgs[allMsgs.length - 2];
              if (userDiv && userMessageId) {
                userDiv.dataset.messageId = userMessageId;
              }
              if (msgDiv && assistantMessageId) {
                msgDiv.dataset.messageId = assistantMessageId;
              }

              // Markdown 渲染完成
              bubble.innerHTML = renderMarkdown(fullContent);
              enhanceCodeBlocks(bubble);
              finishStreaming(bubble);

              // 添加重试按钮
              if (msgDiv && userMessageId) {
                let regenBtn = msgDiv.querySelector(".regenerate-btn");
                if (!regenBtn) {
                  regenBtn = document.createElement("button");
                  regenBtn.className = "regenerate-btn";
                  regenBtn.textContent = "↻";
                  regenBtn.title = "重新生成";
                  msgDiv.appendChild(regenBtn);
                }
                regenBtn.dataset.userMsgId = userMessageId;
              }

              loadSlots();
              break;

            case "error":
              finishStreaming(bubble);
              if (code === "ollama_need_key") {
                const container = document.getElementById("chat-messages");
                const empty = container?.querySelector(".empty-state");
                if (empty) empty.remove();
                const card = document.createElement("div");
                card.className = "message error";
                card.innerHTML = `
                  <div class="bubble">
                    <div style="margin-bottom:12px">⚠️ ${content || "无法连接"}</div>
                    <input type="password" id="ollama-key-input" class="create-input"
                      placeholder="输入 Ollama Cloud API Key" autocomplete="off"
                      style="margin-bottom:10px;width:100%" />
                    <button id="ollama-key-save-btn" class="modal-btn modal-btn-confirm"
                      style="width:100%;padding:10px">保存并重试</button>
                  </div>
                `;
                container?.appendChild(card);
                setTimeout(() => document.getElementById("ollama-key-input")?.focus(), 100);
                document.getElementById("ollama-key-save-btn")?.addEventListener("click", async () => {
                  const key = document.getElementById("ollama-key-input")?.value.trim();
                  if (!key) { showToast("请输入 API Key", "warning"); return; }
                  try {
                    await apiPatch(`/api/slots/${state.currentSlotIndex}/api-key`, { api_key: key });
                    card.remove();
                    const input = document.getElementById("message-input");
                    if (input) { input.value = text; input.focus(); }
                    sendMessage();
                  } catch (e) {
                    showToast("保存失败: " + e.message, "error");
                  }
                });
              } else {
                const errorMessages = {
                  auth_failed: "🔑 API 认证失败，请检查 API Key 是否正确",
                  rate_limited: "⏳ 请求过于频繁，请稍后重试",
                  quota_exceeded: "💰 API 额度不足，请检查账户余额",
                  ollama_unreachable: "🔌 无法连接到 Ollama 服务，请确认已启动",
                  config_error: "⚙️ 模型配置错误",
                };
                const displayMsg = errorMessages[code]
                  ? errorMessages[code]
                  : `⚠️ ${content || "未知错误"}`;
                addErrorMessage(displayMsg);
              }
              break;
          }
        } catch (_) {
          // Ignore parse errors for incomplete lines
        }
      }
    }

  } catch (e) {
    if (idleCheck !== null) clearInterval(idleCheck);
    // 主动取消（由 abort 抛异常进入）→ 回滚
    if (state.streamCancelled || e.name === "AbortError") {
      if (bubble) {
        const allMsgs = document.querySelectorAll("#chat-messages > .message");
        const userDiv = allMsgs[allMsgs.length - 2];
        const aiDiv = allMsgs[allMsgs.length - 1];
        if (userDiv) userDiv.remove();
        if (aiDiv) aiDiv.remove();
        if (!document.querySelector("#chat-messages .message")) {
          document.getElementById("chat-messages").innerHTML = `
            <div class="empty-state">
              <div class="empty-icon">✦</div>
              <div class="empty-title">开始新的对话</div>
              <div class="empty-desc">在下方输入消息，与 AI 开始交流</div>
            </div>
          `;
        }
        const msgInput = document.getElementById("message-input");
        if (msgInput) {
          msgInput.value = text;
          msgInput.style.height = "auto";
          msgInput.focus();
        }
      }
      showToast("已取消", "info");
    } else {
      if (bubble) {
        bubble.textContent = "";
        finishStreaming(bubble);
      }
      addErrorMessage(`请求失败: ${e.message}`);
    }
  }


  finally {
// 用户主动取消（正常退出 while）→ 回滚
    if (state.streamCancelled && bubble) {
      const allMsgs = document.querySelectorAll("#chat-messages > .message");
      const userDiv = allMsgs[allMsgs.length - 2];
      const aiDiv = allMsgs[allMsgs.length - 1];
      if (userDiv) userDiv.remove();
      if (aiDiv) aiDiv.remove();
      if (!document.querySelector("#chat-messages .message")) {
        document.getElementById("chat-messages").innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">✦</div>
            <div class="empty-title">开始新的对话</div>
            <div class="empty-desc">在下方输入消息，与 AI 开始交流</div>
          </div>
        `;
      }
      const msgInput = document.getElementById("message-input");
      if (msgInput) {
        msgInput.value = text;
        msgInput.style.height = "auto";
        msgInput.focus();
      }
      showToast("已取消", "info");
    }
  }

  // 刷新存档数据和侧栏
  if (state.currentSlotIndex !== null) {
    try {
      state.currentSlotData = await apiGet(`/api/slots/${state.currentSlotIndex}/chat`);
      updateSidebarInfo();
    } catch (_) { /* 静默失败 */ }
  }

  setStreaming(false);
  state.streamCancelled = false;
  state.currentReader = null;
  document.getElementById("message-input")?.focus();
}

// ── Regenerate (使用 userMsgId 定位) ──

export async function regenerate(userMsgId) {
  if (state.streaming) return;

  // 通过 data-user-msg-id 找到对应的 assistant 消息
  const regenBtn = document.querySelector(`.regenerate-btn[data-user-msg-id="${userMsgId}"]`);
  if (!regenBtn) return;
  const assistantDiv = regenBtn.closest(".message");

  // 向前找到对应的用户消息
  let userDiv = assistantDiv ? assistantDiv.previousElementSibling : null;
  while (userDiv && !userDiv.classList.contains("user")) {
    userDiv = userDiv.previousElementSibling;
  }
  if (!userDiv) return;

  const userBubble = userDiv.querySelector(".bubble");
  if (!userBubble) {
    showToast("无法找到用户消息内容", "error");
    return;
  }
  const userText = userBubble.textContent || "";

  // 删除后端数据
  try {
    await apiDelete(`/api/slots/${state.currentSlotIndex}/chat/messages`, {
      from_id: userMsgId,
    });
  } catch (e) {
    showToast("操作失败: " + e.message, "error");
    return;
  }

  // 移除 DOM 中这条用户消息及之后的所有消息
  let current = userDiv;
  while (current) {
    const next = current.nextElementSibling;
    current.remove();
    current = next;
  }

  // 填回输入框并发送
  const input = document.getElementById("message-input");
  input.value = userText;
  input.style.height = "auto";
  sendMessage();
}

// ── Cancel stream ──

export function cancelStream() {
  if (!state.streaming) return;
  state.streamCancelled = true;
  // 直接取消 reader（最可靠的方式终止 SSE 循环）
  if (state.currentReader) {
    try { state.currentReader.cancel(); } catch (_) { /* ignore */ }
    state.currentReader = null;
  }
  if (state.abortController) {
    state.abortController.abort();
    state.abortController = null;
  }
}

// ── Edit user message ──

export function editAndResend(msgElement) {
  if (state.streaming) {
    showToast("请等待当前回复完成再编辑", "warning");
    return;
  }

  const bubble = msgElement.querySelector(".bubble");
  if (!bubble) return;

  const originalText = bubble.textContent;
  if (!originalText) return;

  // Switch to edit mode
  const textarea = document.createElement("textarea");
  textarea.className = "edit-textarea";
  textarea.value = originalText;

  const actions = document.createElement("div");
  actions.className = "edit-actions";

  const saveBtn = document.createElement("button");
  saveBtn.className = "edit-save-btn";
  saveBtn.textContent = "保存";

  const cancelBtn = document.createElement("button");
  cancelBtn.className = "edit-cancel-btn";
  cancelBtn.textContent = "取消";

  actions.appendChild(saveBtn);
  actions.appendChild(cancelBtn);

  // Hide edit button
  const editBtn = msgElement.querySelector(".user-edit-btn");
  if (editBtn) editBtn.style.visibility = "hidden";

  bubble.innerHTML = "";
  bubble.appendChild(textarea);
  bubble.appendChild(actions);
  bubble.classList.add("editing");

  textarea.focus();
  textarea.setSelectionRange(textarea.value.length, textarea.value.length);

  // Auto-resize
  textarea.addEventListener("input", () => {
    textarea.style.height = "auto";
    textarea.style.height = textarea.scrollHeight + "px";
  });
  textarea.style.height = textarea.scrollHeight + "px";

  // ── Save handler ──

  saveBtn.onclick = async () => {
    const newText = textarea.value.trim();
    if (!newText) {
      showToast("内容不能为空", "warning");
      return;
    }
    if (newText === originalText) {
      cancelEdit(bubble, originalText, editBtn, msgElement);
      return;
    }

    // 使用 data-message-id 定位（取代 getHistoryIndex）
    const messageId = parseInt(msgElement.dataset.messageId, 10);
    if (!messageId) {
      showToast("无法定位消息 ID", "error");
      cancelEdit(bubble, originalText, editBtn, msgElement);
      return;
    }

    try {
      // 从这条消息起全部删除，让 sendMessage 重新追加
      await apiDelete(`/api/slots/${state.currentSlotIndex}/chat/messages`, {
        from_id: messageId,
      });

      // 移除 DOM 中这条消息及之后的所有消息
      let current = msgElement;
      while (current) {
        const next = current.nextElementSibling;
        current.remove();
        current = next;
      }

      // 将编辑后的文本放入输入框并自动发送
      const input = document.getElementById("message-input");
      input.value = newText;
      input.style.height = "auto";
      input.style.height = input.scrollHeight + "px";
      sendMessage();
    } catch (e) {
      showToast("编辑失败: " + e.message, "error");
      cancelEdit(bubble, originalText, editBtn, msgElement);
    }
  };

  cancelBtn.onclick = () => {
    cancelEdit(bubble, originalText, editBtn, msgElement);
  };
}

function cancelEdit(bubble, originalText, editBtn, msgElement) {
  bubble.classList.remove("editing");
  bubble.textContent = originalText;
  if (editBtn) editBtn.style.visibility = "";
}

// ── Helper: close sidebar (local) ──

function closeSidebar() {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebar-overlay");
  if (sidebar) sidebar.classList.remove("open");
  if (overlay) overlay.classList.remove("active");
}
