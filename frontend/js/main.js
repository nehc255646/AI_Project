/**
 * Application entry point.
 *
 * Imports CSS, wires up event listeners, and initialises state.
 */

// ── Import CSS (Vite bundles these) ──
import "../css/style.css";

// ── State ──
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

// ── Modals ──
import { initModalListeners, updateApiKeyField, closeCreateModal, openHelpModal, closeHelpModal, openExportModal } from "./modals.js";

// ── Chat ──
import { sendMessage, cancelStream, backToSlots, clearSlotChat, regenerate } from "./chat.js";

// ── Utils ──
import { $ } from "./utils.js";

// ── Toast ──
import { showToast } from "./toast.js";

// ── Init ──

async function init() {
  await loadModels();
  await loadEnvStatus();
  await loadSlots();
}

async function loadModels() {
  try {
    const models = await apiGet("/api/models");
    state.models = models;
    const select = document.getElementById("create-model-select");
    select.innerHTML = "";
    models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.key;
      opt.textContent = m.key;
      select.appendChild(opt);
    });
    updateApiKeyField();
  } catch (_) {
    // Fallback
    const fallback = [
      { key: "Minimax-M3", provider: "ollama" },
      { key: "Nemotron-3-Ultra", provider: "ollama" },
      { key: "DeepSeek-v4-flash", provider: "deepseek" },
      { key: "DeepSeek-v4-Pro", provider: "deepseek" },
      { key: "Qwen3.6-Flash", provider: "dashscope" },
      { key: "Qwen3.7-Max", provider: "dashscope" },
    ];
    state.models = fallback;
    const select = document.getElementById("create-model-select");
    select.innerHTML = fallback
      .map((m) => `<option value="${m.key}">${m.key}</option>`)
      .join("");
    updateApiKeyField(); // 使用本地 fallback 数据更新 API Key 字段
  }
}

async function loadEnvStatus() {
  try {
    state.envStatus = await apiGet("/api/env-check");
  } catch (_) {
    state.envStatus = {};
  }
}

// ── Wire DOM event listeners ──

function setupEventListeners() {
  // Sidebar toggle
  $("#sidebar-toggle").addEventListener("click", openSidebar);
  $("#sidebar-overlay").addEventListener("click", closeSidebar);

  // Navigation
  $("#back-to-slots-btn").addEventListener("click", backToSlots);
  $("#back-to-slots-header-btn").addEventListener("click", backToSlots);
  $("#clear-slot-chat-btn").addEventListener("click", clearSlotChat);

  // Export
  $("#export-chat-btn").addEventListener("click", openExportModal);

  // Help
  $("#help-btn-slot").addEventListener("click", openHelpModal);
  $("#help-btn-chat").addEventListener("click", openHelpModal);
  $("#help-close-btn").addEventListener("click", closeHelpModal);
  $("#help-got-it").addEventListener("click", closeHelpModal);

  // Send
  $("#send-btn").addEventListener("click", sendMessage);

  // Cancel stream
  $("#cancel-stream-btn").addEventListener("click", cancelStream);

  // Input: auto-resize
  $("#message-input").addEventListener("input", () => {
    const el = $("#message-input");
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  });

  // Input: Enter to send, Escape to blur
  $("#message-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
    if (e.key === "Escape") {
      $("#message-input").blur();
    }
  });

  // Global: Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;

    // Close help modal
    const helpModal = document.getElementById("help-modal");
    if (!helpModal.classList.contains("hidden")) {
      closeHelpModal();
      return;
    }

    // Close create modal
    const createModal = document.getElementById("create-modal");
    if (!createModal.classList.contains("hidden")) {
      closeCreateModal();
      return;
    }

    // Close confirmation modal
    const confirmOverlay = document.getElementById("modal-overlay");
    if (!confirmOverlay.classList.contains("hidden")) {
      confirmOverlay.classList.add("hidden");
      return;
    }

    // Close sidebar
    const sidebar = document.getElementById("sidebar");
    if (sidebar.classList.contains("open")) {
      closeSidebar();
    }
  });

  // Global: Ctrl+Enter / Cmd+Enter to send from any textarea
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
      const active = document.activeElement;
      if (active && active.tagName === "TEXTAREA" && active.id !== "message-input") return;
      e.preventDefault();
      sendMessage();
    }
  });

  // Initialise modal listeners
  initModalListeners();

  // Event delegation: regenerate button clicks — uses data-user-msg-id
  document.getElementById("chat-messages").addEventListener("click", (e) => {
    const btn = e.target.closest(".regenerate-btn");
    if (!btn) return;
    const userMsgId = parseInt(btn.dataset.userMsgId, 10);
    if (!isNaN(userMsgId)) regenerate(userMsgId);
  });

  // ── Title editing ──

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

  // Click title or edit button → enter edit mode
  document.getElementById("slot-title-display").addEventListener("click", enterTitleEdit);

  // Save button
  document.getElementById("title-save-btn").addEventListener("click", saveTitle);

  // Cancel button
  document.getElementById("title-cancel-btn").addEventListener("click", () => exitTitleEdit(false));

  // Enter → save, Escape → cancel
  document.getElementById("slot-title-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      saveTitle();
    } else if (e.key === "Escape") {
      exitTitleEdit(false);
    }
  });
}

// ── Bootstrap

document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  init();
});
