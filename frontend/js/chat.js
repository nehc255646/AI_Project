/**
 * Chat logic — send, receive SSE stream, regenerate, abort.
 *
 * Support for dual-mode (multi-role) streaming.
 */

import { state } from "./state.js";
import { apiGet, apiPost, apiDelete, apiPatch } from "./api.js";
import { $, scrollToBottom, escapeHtml } from "./utils.js";
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

/** 从 .bubble 中获取文本内容容器 */
function getContent(bubble) {
  if (!bubble) return null;
  // 如果有 label bar，内容在 .bubble-content 中
  return bubble.querySelector(".bubble-content") || bubble;
}

/** 获取 .bubble 所在的 .message */
function getMsgDiv(bubble) {
  return bubble ? bubble.closest(".message") : null;
}

// ── Open a slot ──

export async function openSlot(index) {
  state.currentSlotIndex = index;

  try {
    const data = await apiGet(`/api/slots/${index}/chat`);
    state.currentSlotData = data;
    state.dualEnabled = data.dual_enabled || false;
    state.responseMode = data.response_mode || "both";
    state.firstModel = data.first_model || "model1";
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
  state.dualEnabled = false;
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
  const userMsgBubble = addMessage("user", text, false);
  const userMsgDiv = userMsgBubble ? userMsgBubble.closest(".message") : null;

  setStreaming(true);
  state.abortController = new AbortController();
  state.streamCancelled = false;
  state.currentReader = null;

  let currentBubble = null;
  let bubbles = []; // [{el, role, fullContent, msgId, label}]
  let idleCheck = null;
  let gotDone = false;      // 是否收到 done 事件
  let errorHandled = false; // 是否已显示错误提示
  let aborted = false;      // 本轮是否被取消/超时中断

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
            // ── 双模型：模型开始回复 ──
            case "model_start": {
              const name = event.name || "";
              const icon = event.icon || "🤖";
              currentBubble = addMessage("assistant", "", true, null,
                icon ? `${icon} ${name}`.trim() : name);
              bubbles.push({
                el: currentBubble,
                role: event.role,
                fullContent: "",
                msgId: null,
                label: `${icon} ${name}`.trim(),
              });
              scrollToBottom();
              break;
            }

            // ── 流式数据块 ──
            case "chunk": {
              let entry = null;
              if (currentBubble) {
                entry = bubbles[bubbles.length - 1];
              }
              if (!entry) {
                // 单模型：首次 chunk 时创建气泡
                const bubble = addMessage("assistant", "", true);
                entry = { el: bubble, role: null, fullContent: "", msgId: null, label: null };
                bubbles.push(entry);
                currentBubble = bubble;
              }
              entry.fullContent += content;
              const contentDiv = getContent(entry.el);
              if (contentDiv) {
                contentDiv.textContent += content;
              }
              scrollToBottom();
              break;
            }

            // ── 双模型：单个模型完成 ──
            case "model_done": {
              const entry = bubbles.find(b => b.role === event.role || b.el === currentBubble);
              if (entry) {
                entry.msgId = event.message_id;
                if (event.message_id) {
                  const msgDiv = getMsgDiv(entry.el);
                  if (msgDiv) msgDiv.dataset.messageId = event.message_id;
                }
                const contentDiv = getContent(entry.el);
                if (contentDiv) {
                  contentDiv.innerHTML = renderMarkdown(entry.fullContent);
                  enhanceCodeBlocks(contentDiv);
                }
                finishStreaming(entry.el);
              }
              currentBubble = null;
              break;
            }

            // ── 完成事件 ──
            case "done": {
              gotDone = true;
              if (event.dual) {
                userMessageId = event.user_message_id;
                if (userMsgDiv && userMessageId) userMsgDiv.dataset.messageId = userMessageId;

                if (event.message_ids) {
                  bubbles.forEach((b, i) => {
                    if (event.message_ids[i]) {
                      const d = getMsgDiv(b.el);
                      if (d) d.dataset.messageId = event.message_ids[i];
                    }
                  });
                }
              } else {
                // 单模型
                userMessageId = event.user_message_id;
                const assistantMessageId = event.assistant_message_id;
                if (userMsgDiv && userMessageId) userMsgDiv.dataset.messageId = userMessageId;

                const entry = bubbles[bubbles.length - 1];
                if (entry && entry.el) {
                  const msgDiv = getMsgDiv(entry.el);
                  if (msgDiv && assistantMessageId) msgDiv.dataset.messageId = assistantMessageId;
                  // 完成渲染
                  const contentDiv = getContent(entry.el);
                  if (contentDiv) {
                    contentDiv.innerHTML = renderMarkdown(entry.fullContent);
                    enhanceCodeBlocks(contentDiv);
                  }
                  finishStreaming(entry.el);

                  // 单模型：给最后一个 assistant 消息加重试按钮
                  if (userMsgDiv && userMessageId) {
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
                }
              }
              loadSlots();
              break;
            }

            // ── 错误处理 ──
            case "error": {
              errorHandled = true;
              // 已有完成的模型气泡（已收到 model_done）且非补 Key 场景：
              // 后端会保留用户消息与已完成回复，前端仅移除失败模型的未完成气泡
              const completedBubbles = bubbles.filter(b => b.msgId);
              const hasCompleted = completedBubbles.length > 0 && code !== "ollama_need_key";

              if (hasCompleted) {
                bubbles.forEach(b => {
                  if (!b.msgId) {
                    const d = getMsgDiv(b.el);
                    if (d) d.remove();
                  }
                });
                bubbles = bubbles.filter(b => b.msgId);
                if (currentBubble) {
                  const d = getMsgDiv(currentBubble);
                  if (d) d.remove();
                  currentBubble = null;
                }
                // 保留的用户消息气泡回写消息 ID，保证后续编辑/删除可用
                if (userMsgDiv && event.user_message_id) {
                  userMsgDiv.dataset.messageId = event.user_message_id;
                }
              } else {
                bubbles.forEach(b => {
                  if (b.el) {
                    const d = getMsgDiv(b.el);
                    if (d) d.remove();
                  }
                });
                bubbles = [];
                if (currentBubble) {
                  const d = getMsgDiv(currentBubble);
                  if (d) d.remove();
                  currentBubble = null;
                }
                // 本轮失败，后端会回滚数据库；移除用户消息气泡保持视觉一致
                if (userMsgDiv) userMsgDiv.remove();
              }

              if (code === "ollama_need_key") {
                const container = document.getElementById("chat-messages");
                const empty = container?.querySelector(".empty-state");
                if (empty) empty.remove();
                const card = document.createElement("div");
                card.className = "message error";
                card.innerHTML = `<div class="bubble">
                  <div style="margin-bottom:12px">⚠️ ${escapeHtml(content || "无法连接")}</div>
                  <input type="password" id="ollama-key-input" class="create-input"
                    placeholder="输入 Ollama Cloud API Key" autocomplete="off"
                    style="margin-bottom:10px;width:100%" />
                  <button id="ollama-key-save-btn" class="modal-btn modal-btn-confirm"
                    style="width:100%;padding:10px">保存并重试</button>
                </div>`;
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
                const msgs = {
                  auth_failed: "🔑 API 认证失败，请检查 API Key 是否正确",
                  rate_limited: "⏳ 请求过于频繁，请稍后重试",
                  quota_exceeded: "💰 API 额度不足，请检查账户余额",
                  ollama_unreachable: "🔌 无法连接到 Ollama 服务，请确认已启动",
                  config_error: "⚙️ 模型配置错误",
                };
                addErrorMessage(msgs[code] || `⚠️ ${content || "未知错误"}`, hasCompleted ? null : text);
              }
              break;
            }
          }
        } catch (_) { /* ignore parse errors */ }
      }
    }

  } catch (e) {
    if (idleCheck !== null) clearInterval(idleCheck);
    if (state.streamCancelled || e.name === "AbortError") {
      // 取消/超时：统一在 finally 中回滚本轮气泡并提示
      aborted = true;
    } else {
      errorHandled = true;
      bubbles.forEach(b => {
        if (b.el) {
          const d = getMsgDiv(b.el);
          if (d) d.remove();
        }
      });
      bubbles = [];
      if (currentBubble) {
        const d = getMsgDiv(currentBubble);
        if (d) d.remove();
        currentBubble = null;
      }
      if (userMsgDiv) userMsgDiv.remove();
      addErrorMessage(`请求失败: ${e.message}`, text);
    }
  } finally {
    // 手动取消（streamCancelled）与超时中断（aborted）都需回滚本轮气泡；
    // 手动取消时额外提示一次，超时已有独立提示
    if (state.streamCancelled) {
      rollbackMessages(text);
      showToast("已取消", "info");
    } else if (aborted) {
      rollbackMessages(text);
    }
  }

  // 刷新存档数据
  if (state.currentSlotIndex !== null) {
    try {
      state.currentSlotData = await apiGet(`/api/slots/${state.currentSlotIndex}/chat`);
      state.dualEnabled = state.currentSlotData.dual_enabled || false;
      state.responseMode = state.currentSlotData.response_mode || "both";
      state.firstModel = state.currentSlotData.first_model || "model1";
      // 取消/超时中断时后端已回滚数据库，用最新数据重建 DOM 保持一致性
      if (!gotDone && !errorHandled) {
        renderMessages(state.currentSlotData.history || []);
      }
      updateSidebarInfo();
    } catch (_) { /* 静默失败 */ }
  }

  setStreaming(false);
  state.streamCancelled = false;
  state.currentReader = null;
  document.getElementById("message-input")?.focus();
}

function rollbackMessages(text) {
  const allMsgs = document.querySelectorAll("#chat-messages > .message");
  const msgsToRemove = [];
  for (let i = allMsgs.length - 1; i >= Math.max(0, allMsgs.length - 5); i--) {
    const m = allMsgs[i];
    if (m && (m.classList.contains("user") || m.classList.contains("assistant"))) {
      msgsToRemove.push(m);
    }
    if (m && m.classList.contains("user")) break;
  }
  msgsToRemove.forEach(m => m?.remove());
  if (!document.querySelector("#chat-messages .message")) {
    document.getElementById("chat-messages").innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">✦</div>
        <div class="empty-title">开始新的对话</div>
        <div class="empty-desc">在下方输入消息，与 AI 开始交流</div>
      </div>`;
  }
  const msgInput = document.getElementById("message-input");
  if (msgInput) {
    msgInput.value = text;
    msgInput.style.height = "auto";
    msgInput.focus();
  }
}

// ── Regenerate (单模型，双模型禁用) ──

export async function regenerate(userMsgId) {
  if (state.streaming) return;
  if (state.dualEnabled) {
    showToast("双模型模式不支持重试，请编辑用户消息", "warning");
    return;
  }

  const regenBtn = document.querySelector(`.regenerate-btn[data-user-msg-id="${userMsgId}"]`);
  if (!regenBtn) return;
  const assistantDiv = regenBtn.closest(".message");

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

  try {
    await apiDelete(`/api/slots/${state.currentSlotIndex}/chat/messages`, { from_id: userMsgId });
  } catch (e) {
    showToast("操作失败: " + e.message, "error");
    return;
  }

  let current = userDiv;
  while (current) {
    const next = current.nextElementSibling;
    current.remove();
    current = next;
  }

  const input = document.getElementById("message-input");
  input.value = userText;
  input.style.height = "auto";
  sendMessage();
}

// ── Cancel stream ──

export function cancelStream() {
  if (!state.streaming) return;
  state.streamCancelled = true;
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

  const editBtn = msgElement.querySelector(".user-edit-btn");
  if (editBtn) editBtn.style.visibility = "hidden";

  const contentDiv = bubble.querySelector(".bubble-content") || bubble;
  contentDiv.innerHTML = "";
  contentDiv.appendChild(textarea);
  contentDiv.appendChild(actions);
  bubble.classList.add("editing");

  textarea.focus();
  textarea.setSelectionRange(textarea.value.length, textarea.value.length);

  textarea.addEventListener("input", () => {
    textarea.style.height = "auto";
    textarea.style.height = textarea.scrollHeight + "px";
  });
  textarea.style.height = textarea.scrollHeight + "px";

  saveBtn.onclick = async () => {
    const newText = textarea.value.trim();
    if (!newText) {
      showToast("内容不能为空", "warning");
      return;
    }
    if (newText === originalText) {
      cancelEdit(contentDiv, originalText, editBtn, bubble);
      return;
    }

    const messageId = parseInt(msgElement.dataset.messageId, 10);
    if (!messageId) {
      showToast("无法定位消息 ID", "error");
      cancelEdit(contentDiv, originalText, editBtn, bubble);
      return;
    }

    try {
      await apiDelete(`/api/slots/${state.currentSlotIndex}/chat/messages`, { from_id: messageId });

      let current = msgElement;
      while (current) {
        const next = current.nextElementSibling;
        current.remove();
        current = next;
      }

      const input = document.getElementById("message-input");
      input.value = newText;
      input.style.height = "auto";
      input.style.height = input.scrollHeight + "px";
      sendMessage();
    } catch (e) {
      showToast("编辑失败: " + e.message, "error");
      cancelEdit(contentDiv, originalText, editBtn, bubble);
    }
  };

  cancelBtn.onclick = () => {
    cancelEdit(contentDiv, originalText, editBtn, bubble);
  };
}

function cancelEdit(contentDiv, originalText, editBtn, bubble) {
  bubble.classList.remove("editing");
  contentDiv.textContent = originalText;
  if (editBtn) editBtn.style.visibility = "";
}

// ── 切换双模型回复模式 ──

export async function setDualResponseMode(mode, firstModel) {
  if (state.streaming) {
    showToast("请等待当前回复完成", "warning");
    return;
  }
  const idx = state.currentSlotIndex;
  if (idx === null) return;

  try {
    const resp = await apiPatch(`/api/slots/${idx}/dual-toggle`, {
      response_mode: mode,
      first_model: firstModel || state.firstModel || "model1",
    });
    state.responseMode = resp.dual_config?.response_mode || mode;
    state.firstModel = resp.dual_config?.first_model || firstModel || "model1";
    updateSidebarInfo();
    showToast(
      mode === "both" ? "已设为同时回复" :
      mode === "model1" ? "已设为仅模型1回复" : "已设为仅模型2回复",
      "success"
    );
  } catch (e) {
    showToast("切换失败: " + e.message, "error");
  }
}

// ── Helper: close sidebar ──

function closeSidebar() {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebar-overlay");
  if (sidebar) sidebar.classList.remove("open");
  if (overlay) overlay.classList.remove("active");
}
