/**
 * 应用入口 — 引入样式、绑定事件监听并初始化状态。
 */

// ── 引入样式（由 Vite 打包） ──
import "../css/style.css";

// ── 状态 ──
import { state } from "./state.js";

// ── API ──
import { apiGet, apiPatch } from "./api.js";

// ── UI ──
import {
  showSlotView,
  loadSlots,
  openSidebar,
  closeSidebar,
} from "./ui.js";

// ── 弹窗 ──
import { initModalListeners, updateApiKeyField, closeCreateModal, openHelpModal, closeHelpModal, openExportModal, exportSlotBackup, importSlotBackup, openEditModal } from "./modals.js";

// ── 对话 ──
import { sendMessage, cancelStream, backToSlots, clearSlotChat, regenerate, setDualResponseMode, continueLastReply } from "./chat.js";

// ── 工具 ──
import { $ } from "./utils.js";

// ── 轻提示 ──
import { showToast } from "./toast.js";

// ── 初始化 ──

async function init() {
  await loadModels();
  await loadEnvStatus();
  await loadSlots();
}

async function loadModels() {
  try {
    state.models = await apiGet("/api/models");
  } catch (_) {
    // 兜底：后端不可用时的备用模型列表，需与 backend/config.py 的 MODEL_CONFIG 保持一致
    state.models = [
      { key: "deepseek:deepseek-v4-flash", id: "deepseek-v4-flash", provider: "deepseek" },
      { key: "deepseek:deepseek-v4-pro", id: "deepseek-v4-pro", provider: "deepseek" },
      { key: "dashscope:qwen-3.8-max", id: "qwen-3.8-max", provider: "dashscope" },
      { key: "dashscope:qwen-3.7-max", id: "qwen-3.7-max", provider: "dashscope" },
      { key: "ollama_cloud:minimax-m3:cloud", id: "minimax-m3:cloud", provider: "ollama_cloud" },
      { key: "ollama_local:qwen3.8:27b", id: "qwen3.8:27b", provider: "ollama_local" },
      { key: "openai:gpt-5.6-luna", id: "gpt-5.6-luna", provider: "openai" },
      { key: "gemini:gemini-3.7-flash", id: "gemini-3.7-flash", provider: "gemini" },
      { key: "opencode:glm-5.3", id: "glm-5.3", provider: "opencode" },
    ];
  }
  updateApiKeyField(); // 使用当前选中的模型更新 API Key 字段
}

async function loadEnvStatus() {
  try {
    state.envStatus = await apiGet("/api/env-check");
  } catch (_) {
    state.envStatus = {};
  }
}

// ── 绑定 DOM 事件监听 ──

function setupEventListeners() {
  // 侧边栏开关
  $("#sidebar-toggle").addEventListener("click", openSidebar);
  $("#sidebar-overlay").addEventListener("click", closeSidebar);

  // 导航
  $("#back-to-slots-btn").addEventListener("click", backToSlots);
  $("#back-to-slots-header-btn").addEventListener("click", backToSlots);
  $("#clear-slot-chat-btn").addEventListener("click", clearSlotChat);
  // 更换模型（侧边栏）
  document.getElementById("change-model-btn")?.addEventListener("click", openEditModal);

  // 导出
  $("#export-chat-btn").addEventListener("click", openExportModal);
  $("#backup-slot-btn").addEventListener("click", exportSlotBackup);
  $("#import-slot-btn").addEventListener("click", () => $("#import-slot-input").click());
  $("#import-backup-slot-btn").addEventListener("click", () => $("#import-slot-input").click());
  $("#import-slot-input").addEventListener("change", (e) => {
    importSlotBackup(e.target.files[0]);
    e.target.value = "";
  });

  // 帮助
  $("#help-btn-slot").addEventListener("click", openHelpModal);
  $("#help-btn-chat").addEventListener("click", openHelpModal);
  $("#help-close-btn").addEventListener("click", closeHelpModal);
  $("#help-got-it").addEventListener("click", closeHelpModal);

  // 发送
  $("#send-btn").addEventListener("click", sendMessage);

  // 继续回复（不输入消息，让 AI 接着上一条回复继续）
  $("#continue-btn").addEventListener("click", continueLastReply);

  // 取消流式回复
  $("#cancel-stream-btn").addEventListener("click", cancelStream);

  // 输入框自动增高
  $("#message-input").addEventListener("input", () => {
    const el = $("#message-input");
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  });

  // Enter 发送，Escape 失焦
  $("#message-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
    if (e.key === "Escape") {
      $("#message-input").blur();
    }
  });

  // 全局 Escape 键
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;

    // 关闭帮助弹窗
    const helpModal = document.getElementById("help-modal");
    if (!helpModal.classList.contains("hidden")) {
      closeHelpModal();
      return;
    }

    // 关闭创建弹窗
    const createModal = document.getElementById("create-modal");
    if (!createModal.classList.contains("hidden")) {
      closeCreateModal();
      return;
    }

    // 关闭确认弹窗
    const confirmOverlay = document.getElementById("modal-overlay");
    if (!confirmOverlay.classList.contains("hidden")) {
      confirmOverlay.classList.add("hidden");
      return;
    }

    // 关闭侧边栏
    const sidebar = document.getElementById("sidebar");
    if (sidebar.classList.contains("open")) {
      closeSidebar();
    }
  });

  // 全局 Ctrl/Cmd + Enter 发送（任意文本域）
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
      const active = document.activeElement;
      if (active && active.tagName === "TEXTAREA" && active.id !== "message-input") return;
      e.preventDefault();
      sendMessage();
    }
  });

  // 初始化弹窗监听
  initModalListeners();

  // 事件委托：重新生成按钮点击（依据 data-user-msg-id）
  document.getElementById("chat-messages").addEventListener("click", (e) => {
    const btn = e.target.closest(".regenerate-btn");
    if (!btn) return;
    const userMsgId = parseInt(btn.dataset.userMsgId, 10);
    if (!isNaN(userMsgId)) regenerate(userMsgId);
  });

  // ── 双模型：回复模式单选框 ──
  document.querySelectorAll('input[name="response-mode"]').forEach((radio) => {
    radio.addEventListener("change", (e) => {
      const mode = e.target.value;
      const firstRadio = document.querySelector('input[name="first-model"]:checked');
      const first = firstRadio ? firstRadio.value : "model1";
      setDualResponseMode(mode, first);
    });
  });

  document.querySelectorAll('input[name="first-model"]').forEach((radio) => {
    radio.addEventListener("change", (e) => {
      const modeRadio = document.querySelector('input[name="response-mode"]:checked');
      const mode = modeRadio ? modeRadio.value : "both";
      setDualResponseMode(mode, e.target.value);
    });
  });

  // ── 标题编辑 ──

  function enterTitleEdit() {
    const curTitle = state.currentSlotData?.title || "";
    document.getElementById("slot-title-input").value = curTitle;
    document.getElementById("slot-title-display").classList.add("hidden");
    document.getElementById("slot-title-edit-wrapper").classList.remove("hidden");
    document.getElementById("slot-title-input").focus();
    document.getElementById("slot-title-input").select();
  }

  function exitTitleEdit(saved) {
    document.getElementById("slot-title-display").classList.remove("hidden");
    document.getElementById("slot-title-edit-wrapper").classList.add("hidden");
    if (saved && state.currentSlotData) {
      const newTitle = document.getElementById("slot-title-text").textContent;
      state.currentSlotData.title = newTitle;
      loadSlots();
    }
  }

  async function saveTitle() {
    const input = document.getElementById("slot-title-input");
    const newTitle = input.value.trim();
    if (!newTitle) {
      showToast("标题不能为空", "warning");
      return;
    }
    const idx = state.currentSlotIndex;
    if (idx === null) return;
    try {
      await apiPatch(`/api/slots/${idx}/title`, { title: newTitle });
      document.getElementById("slot-title-text").textContent = newTitle;
      exitTitleEdit(true);
      showToast("标题已更新", "success");
    } catch (e) {
      showToast("更新标题失败: " + e.message, "error");
    }
  }

  // 点击标题或编辑按钮进入编辑
  document.getElementById("slot-title-display").addEventListener("click", enterTitleEdit);

  // 保存按钮
  document.getElementById("title-save-btn").addEventListener("click", saveTitle);

  // 取消按钮
  document.getElementById("title-cancel-btn").addEventListener("click", () => exitTitleEdit(false));

  // Enter 保存，Escape 取消
  document.getElementById("slot-title-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      saveTitle();
    } else if (e.key === "Escape") {
      exitTitleEdit(false);
    }
  });
}

// ── 启动 ──

document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  init();
});
