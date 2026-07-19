/**
 * Modal management.
 *
 * Create-slot modal (3-step wizard), export modal, and API-key field logic.
 */

import { state } from "./state.js";
import { apiGet, apiPost } from "./api.js";
import { showToast } from "./toast.js";
import { loadSlots } from "./ui.js";
import { openSlot } from "./chat.js";

// ── Create Slot Modal (3-step wizard) ──

export let pendingCreateIndex = null;
let currentStep = 1;

/** 默认参数缓存（从后端获取） */
let defaultParams = null;

async function loadDefaultParams() {
  if (defaultParams) return defaultParams;
  try {
    defaultParams = await apiGet("/api/default-params");
  } catch (_) {
    // Fallback 默认值
    defaultParams = {
      temperature: 1.1,
      min_p: 0.1,
      top_k: 100,
      top_p: 0.95,
      repeat_penalty: 1.25,
      presence_penalty: 0.4,
      frequency_penalty: 0.0,
      num_ctx: 131072,
      num_predict: 4096,
    };
  }
  return defaultParams;
}

/** 所有参数的最新值 */
function getParamValues() {
  return {
    temperature: parseFloat(document.getElementById("param-temperature").value),
    top_p: parseFloat(document.getElementById("param-top-p").value),
    min_p: parseFloat(document.getElementById("param-min-p").value),
    top_k: parseInt(document.getElementById("param-top-k").value, 10),
    repeat_penalty: parseFloat(document.getElementById("param-repeat-penalty").value),
    presence_penalty: parseFloat(document.getElementById("param-presence-penalty").value),
    frequency_penalty: parseFloat(document.getElementById("param-frequency-penalty").value),
    num_ctx: parseInt(document.getElementById("param-num-ctx").value, 10),
    num_predict: parseInt(document.getElementById("param-num-predict").value, 10),
  };
}

function showStep(step) {
  currentStep = step;
  document.querySelectorAll(".wizard-panel").forEach((el) => el.classList.add("hidden"));
  document.getElementById(`wizard-step-${step}`).classList.remove("hidden");

  // 更新步骤指示器
  document.querySelectorAll(".wizard-step").forEach((el) => {
    const s = parseInt(el.dataset.step, 10);
    el.classList.toggle("active", s === step);
    el.classList.toggle("done", s < step);
  });

  // 按钮切换
  document.getElementById("wizard-prev").style.display = step > 1 ? "" : "none";
  document.getElementById("wizard-next").style.display = step < 3 ? "" : "none";
  document.getElementById("wizard-create").style.display = step === 3 ? "" : "none";
}

export async function openCreateModal(index) {
  pendingCreateIndex = index;
  const select = document.getElementById("create-model-select");
  const prompt = document.getElementById("create-system-prompt");
  const apiKeyInput = document.getElementById("create-api-key");
  const titleInput = document.getElementById("create-title");

  select.value = "DeepSeek-v4-flash";
  prompt.value = "使用中文回答";
  apiKeyInput.value = "";
  titleInput.value = "";

  // 从后端获取默认参数（消除前端硬编码重复）
  const params = await loadDefaultParams();

  document.getElementById("param-temperature").value = String(params.temperature ?? 1.1);
  document.getElementById("param-top-p").value = String(params.top_p ?? 0.95);
  document.getElementById("param-min-p").value = String(params.min_p ?? 0.1);
  document.getElementById("param-top-k").value = String(params.top_k ?? 100);
  document.getElementById("param-repeat-penalty").value = String(params.repeat_penalty ?? 1.25);
  document.getElementById("param-presence-penalty").value = String(params.presence_penalty ?? 0.4);
  document.getElementById("param-frequency-penalty").value = String(params.frequency_penalty ?? 0.0);
  document.getElementById("param-num-ctx").value = String(params.num_ctx ?? 131072);
  document.getElementById("param-num-predict").value = String(params.num_predict ?? 4096);

  updateParamDisplays();

  updateApiKeyField();
  showStep(1);
  document.getElementById("create-modal").classList.remove("hidden");
  select.focus();
}

export function closeCreateModal() {
  document.getElementById("create-modal").classList.add("hidden");
  pendingCreateIndex = null;
}

export function updateApiKeyField() {
  const select = document.getElementById("create-model-select");
  const field = document.getElementById("api-key-field");
  const label = document.getElementById("api-key-label");
  const input = document.getElementById("create-api-key");

  const modelKey = select.value;
  const model = state.models.find((m) => m.key === modelKey);
  if (!model) return;

  const provider = model.provider || "";
  const hasEnv = state.envStatus[provider] === true;

  // Ollama 创建时不要求 Key，连接失败时再处理
  if (hasEnv || provider === "ollama") {
    field.style.display = "none";
    input.value = "";
    input.required = false;
  } else {
    field.style.display = "block";
    const nameMap = { deepseek: "DeepSeek", dashscope: "DashScope" };
    const providerName = nameMap[provider] || provider;
    label.textContent = `${providerName} API 密钥`;
    input.placeholder = `请输入你的 ${providerName} API Key`;
    input.required = true;
  }
}

/** 更新所有参数滑块的数值显示 */
function updateParamDisplays() {
  const ids = [
    "temperature", "top-p", "min-p", "top-k",
    "repeat-penalty", "presence-penalty", "frequency-penalty",
  ];
  ids.forEach((id) => {
    const input = document.getElementById(`param-${id}`);
    const display = document.getElementById(`param-${id}-val`);
    if (input && display) display.textContent = input.value;
  });
}

// ── Export modal ──

export async function openExportModal() {
  const idx = state.currentSlotIndex;
  if (idx === null) return;

  // 防止重复弹窗
  if (document.querySelector(".export-content")) return;

  try {
    const data = await apiGet(`/api/slots/${idx}/chat/export`);

    // Build markdown export content
    const lines = [
      `# ${data.title || "对话导出"}`,
      "",
      `**模型**: ${data.model || "未知"}`,
      `**系统提示词**: ${data.system_prompt || "无"}`,
      `**创建时间**: ${data.created_at || "未知"}`,
      `**更新时间**: ${data.updated_at || "未知"}`,
      "",
      "---",
      "",
    ];

    for (const msg of data.messages || []) {
      const roleLabel = msg.role === "user" ? "👤 **你**" : "🤖 **AI**";
      lines.push(`### ${roleLabel}`);
      lines.push("");
      lines.push(msg.content || "");
      lines.push("");
    }

    const content = lines.join("\n");

    // Show in modal
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal-content export-content">
        <div class="modal-icon">📥</div>
        <div class="modal-title">导出对话</div>
        <p class="export-hint">复制下方内容或使用右下角的「复制全部」按钮</p>
        <textarea class="export-textarea" readonly>${content.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</textarea>
        <div class="modal-actions">
          <button class="modal-btn modal-btn-cancel" id="export-close">关闭</button>
          <button class="modal-btn modal-btn-confirm" id="export-copy">📋 复制全部</button>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    overlay.querySelector("#export-close").onclick = () => overlay.remove();
    overlay.querySelector("#export-copy").onclick = () => {
      const textarea = overlay.querySelector(".export-textarea");
      if (textarea) {
        navigator.clipboard.writeText(textarea.value).then(() => {
          showToast("已复制到剪贴板", "success");
        }).catch(() => {
          showToast("复制失败，请手动选择复制", "warning");
        });
      }
    };
    overlay.onclick = (e) => {
      if (e.target === overlay) overlay.remove();
    };
  } catch (e) {
    showToast("导出失败: " + e.message, "error");
  }
}

// ── Help Modal ──

export function openHelpModal() {
  document.getElementById("help-modal").classList.remove("hidden");
}

export function closeHelpModal() {
  document.getElementById("help-modal").classList.add("hidden");
}

// ── Init modal event listeners ──

export function initModalListeners() {
  const createModal = document.getElementById("create-modal");

  // ── 步骤导航 ──

  // 下一步
  document.getElementById("wizard-next").addEventListener("click", () => {
    if (currentStep === 1) {
      // 校验 Step 1：API Key
      const apiKeyField = document.getElementById("api-key-field");
      const apiKeyInput = document.getElementById("create-api-key");
      if (apiKeyField.style.display !== "none" && !apiKeyInput.value.trim()) {
        showToast("请填写该模型所需的 API 密钥", "warning");
        apiKeyInput.focus();
        return;
      }
      showStep(2);
    } else if (currentStep === 2) {
      showStep(3);
    }
  });

  // 上一步
  document.getElementById("wizard-prev").addEventListener("click", () => {
    if (currentStep > 1) showStep(currentStep - 1);
  });

  // 取消
  document.getElementById("wizard-cancel").addEventListener("click", closeCreateModal);

  // 创建存档
  document.getElementById("wizard-create").addEventListener("click", async () => {
    const idx = pendingCreateIndex;
    if (idx === null) return;

    const select = document.getElementById("create-model-select");
    const promptInput = document.getElementById("create-system-prompt");
    const apiKeyInput = document.getElementById("create-api-key");
    const apiKeyField = document.getElementById("api-key-field");
    const titleInput = document.getElementById("create-title");

    const model = select.value;
    const systemPrompt = promptInput.value.trim() || "使用中文回答";
    const apiKey = apiKeyField.style.display !== "none" ? apiKeyInput.value.trim() : "";

    try {
      await apiPost(`/api/slots/${idx}`, {
        model,
        system_prompt: systemPrompt,
        api_key: apiKey,
        title: titleInput.value.trim(),
        params: getParamValues(),
      });
      closeCreateModal();
      showToast("存档创建成功", "success");
      await openSlot(idx);
    } catch (e) {
      showToast("创建失败: " + e.message, "error");
    }
  });

  // 关闭弹窗
  createModal.addEventListener("click", (e) => {
    if (e.target === createModal) closeCreateModal();
  });

  // 模型切换 → 更新 API Key 字段
  document.getElementById("create-model-select").addEventListener("change", updateApiKeyField);

  // ── 参数滑块联动 ──
  const rangeIds = [
    "temperature", "top-p", "min-p", "top-k",
    "repeat-penalty", "presence-penalty", "frequency-penalty",
  ];
  rangeIds.forEach((id) => {
    const input = document.getElementById(`param-${id}`);
    if (input) {
      input.addEventListener("input", () => {
        const display = document.getElementById(`param-${id}-val`);
        if (display) display.textContent = input.value;
      });
    }
  });

  // ── 关闭确认弹窗 ──
  document.getElementById("modal-overlay").addEventListener("click", (e) => {
    if (e.target === document.getElementById("modal-overlay")) {
      document.getElementById("modal-overlay").classList.add("hidden");
    }
  });

  // ── 关闭帮助弹窗 ──
  document.getElementById("help-modal").addEventListener("click", (e) => {
    if (e.target === document.getElementById("help-modal")) {
      closeHelpModal();
    }
  });
}
