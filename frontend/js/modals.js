/**
 * Modal management.
 *
 * Create-slot modal (supports single + dual mode wizard),
 * export modal, and API-key field logic.
 */

import { state } from "./state.js";
import { apiGet, apiPost } from "./api.js";
import { showToast } from "./toast.js";
import { loadSlots } from "./ui.js";
import { openSlot } from "./chat.js";

// ── Create Slot Modal ──

export let pendingCreateIndex = null;
let currentStep = 0;
let isDualMode = false;

/** 默认参数缓存 */
let defaultParams = null;

const MODEL1_ICON = "🎭";
const MODEL2_ICON = "🌟";

async function loadDefaultParams() {
  if (defaultParams) return defaultParams;
  try {
    defaultParams = await apiGet("/api/default-params");
  } catch (_) {
    defaultParams = {
      temperature: 1.1, min_p: 0.1, top_k: 100, top_p: 0.95,
      repeat_penalty: 1.25, presence_penalty: 0.4, frequency_penalty: 0.0,
      num_ctx: 131072, num_predict: 4096,
    };
  }
  return defaultParams;
}

function getParamValues(suffix = "") {
  const el = (id) => document.getElementById(`param${suffix}-${id}`);
  return {
    temperature: parseFloat(el("temperature").value),
    top_p: parseFloat(el("top-p").value),
    min_p: parseFloat(el("min-p").value),
    top_k: parseInt(el("top-k").value, 10),
    repeat_penalty: parseFloat(el("repeat-penalty").value),
    presence_penalty: parseFloat(el("presence-penalty").value),
    frequency_penalty: parseFloat(el("frequency-penalty").value),
    num_ctx: parseInt(el("num-ctx").value, 10),
    num_predict: parseInt(el("num-predict").value, 10),
  };
}

function showStep(step) {
  currentStep = step;

  // 处理步骤指示器
  const steps = document.querySelectorAll(".wizard-step");
  steps.forEach((el) => {
    const s = parseInt(el.dataset.step, 10);
    const isVisible = isDualMode
      ? (s === 0 || s >= 1)  // 双模型: 显示所有步骤
      : (s >= 0 && s <= 3);  // 单模型: 只显示 0-3
    el.style.display = isVisible ? "" : "none";

    el.classList.toggle("active", s === step);
    el.classList.toggle("done", s < step);
  });

  // 隐藏所有面板，显示当前
  document.querySelectorAll(".wizard-panel").forEach((el) => el.classList.add("hidden"));
  const panel = document.getElementById(`wizard-step-${step}`);
  if (panel) panel.classList.remove("hidden");

  // 按钮控制
  if (step === 0) {
    document.getElementById("wizard-prev").style.display = "none";
    document.getElementById("wizard-next").style.display = "";
    document.getElementById("wizard-create").style.display = "none";
  } else if (isDualMode) {
    if (step === 5) {
      document.getElementById("wizard-prev").style.display = "";
      document.getElementById("wizard-next").style.display = "none";
      document.getElementById("wizard-create").style.display = "";
    } else {
      document.getElementById("wizard-prev").style.display = "";
      document.getElementById("wizard-next").style.display = "";
      document.getElementById("wizard-create").style.display = "none";
    }
  } else {
    // 单模型
    if (step === 3) {
      document.getElementById("wizard-prev").style.display = "";
      document.getElementById("wizard-next").style.display = "none";
      document.getElementById("wizard-create").style.display = "";
    } else {
      document.getElementById("wizard-prev").style.display = step > 1 ? "" : "none";
      document.getElementById("wizard-next").style.display = "";
      document.getElementById("wizard-create").style.display = "none";
    }
  }
}

function populateModelSelect(selectId, selectedKey) {
  const select = document.getElementById(selectId);
  if (!select) return;
  select.innerHTML = "";
  (state.models || []).forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m.key;
    opt.textContent = m.key;
    if (m.key === selectedKey) opt.selected = true;
    select.appendChild(opt);
  });
}

/** 填充参数滑块 */
function populateParams(prefix) {
  const gridId = prefix ? `params-grid-m2` : `params-grid`;
  // params for model2 are populated with IDs like param2-temperature
  if (prefix) return; // HTML 已内联所有滑块
}

function updateParamDisplays(suffix = "") {
  const ids = [
    "temperature", "top-p", "min-p", "top-k",
    "repeat-penalty", "presence-penalty", "frequency-penalty",
  ];
  ids.forEach((id) => {
    const input = document.getElementById(`param${suffix}-${id}`);
    const display = document.getElementById(`param${suffix}-${id}-val`);
    if (input && display) display.textContent = input.value;
  });
}

export async function openCreateModal(index) {
  pendingCreateIndex = index;
  isDualMode = false;
  currentStep = 0;

  // 重置模式选择
  document.getElementById("dual-option-single").querySelector("input").checked = true;
  document.getElementById("dual-option-dual").querySelector("input").checked = false;

  // 重置 step3 显示
  document.getElementById("step3-single").style.display = "";
  document.getElementById("step3-dual").style.display = "none";

  // 隐藏模型1名称字段和 step2 系统提示词（单模型默认）
  document.getElementById("field-model1-name").style.display = "none";
  document.getElementById("step2-prompt-field").style.display = "none";
  document.getElementById("step1-icon").textContent = "🤖";
  document.getElementById("step1-title").textContent = "选择模型";

  // Populate model selects
  populateModelSelect("create-model-select", "DeepSeek-v4-flash");
  populateModelSelect("create-model2-select", "DeepSeek-v4-flash");

  // 重置值
  document.getElementById("create-model1-name").value = "";
  document.getElementById("create-model2-name").value = "";
  document.getElementById("create-api-key").value = "";
  document.getElementById("create-api-key-2").value = "";
  document.getElementById("create-title").value = "";
  document.getElementById("create-title-dual").value = "";
  document.getElementById("create-system-prompt").value = "使用中文回答";
  document.getElementById("create-system-prompt-single").value = "使用中文回答";
  document.getElementById("create-system-prompt-2").value = "使用中文回答";

  const params = await loadDefaultParams();
  // 模型1参数
  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = String(val);
  };
  setVal("param-temperature", params.temperature ?? 1.1);
  setVal("param-top-p", params.top_p ?? 0.95);
  setVal("param-min-p", params.min_p ?? 0.1);
  setVal("param-top-k", params.top_k ?? 100);
  setVal("param-repeat-penalty", params.repeat_penalty ?? 1.25);
  setVal("param-presence-penalty", params.presence_penalty ?? 0.4);
  setVal("param-frequency-penalty", params.frequency_penalty ?? 0.0);
  setVal("param-num-ctx", params.num_ctx ?? 131072);
  setVal("param-num-predict", params.num_predict ?? 4096);

  // 模型2参数
  setVal("param2-temperature", params.temperature ?? 1.1);
  setVal("param2-top-p", params.top_p ?? 0.95);
  setVal("param2-min-p", params.min_p ?? 0.1);
  setVal("param2-top-k", params.top_k ?? 100);
  setVal("param2-repeat-penalty", params.repeat_penalty ?? 1.25);
  setVal("param2-presence-penalty", params.presence_penalty ?? 0.4);
  setVal("param2-frequency-penalty", params.frequency_penalty ?? 0.0);
  setVal("param2-num-ctx", params.num_ctx ?? 131072);
  setVal("param2-num-predict", params.num_predict ?? 4096);

  updateParamDisplays();
  updateParamDisplays("2");
  updateApiKeyField();
  updateApiKeyField2();

  showStep(0);
  document.getElementById("create-modal").classList.remove("hidden");
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
  if (hasEnv || provider === "ollama") {
    field.style.display = "none";
    input.value = "";
    input.required = false;
  } else {
    field.style.display = "block";
    const nameMap = { deepseek: "DeepSeek", dashscope: "DashScope" };
    label.textContent = `${nameMap[provider] || provider} API 密钥`;
    input.placeholder = `请输入你的 ${nameMap[provider] || provider} API Key`;
    input.required = true;
  }
}

export function updateApiKeyField2() {
  const select = document.getElementById("create-model2-select");
  const field = document.getElementById("api-key-field-2");
  const label = document.getElementById("api-key-label-2");
  const input = document.getElementById("create-api-key-2");

  const modelKey = select.value;
  const model = state.models.find((m) => m.key === modelKey);
  if (!model) return;

  const provider = model.provider || "";
  const hasEnv = state.envStatus[provider] === true;
  if (hasEnv || provider === "ollama") {
    field.style.display = "none";
    input.value = "";
    input.required = false;
  } else {
    field.style.display = "block";
    const nameMap = { deepseek: "DeepSeek", dashscope: "DashScope" };
    label.textContent = `${nameMap[provider] || provider} API 密钥`;
    input.placeholder = `请输入你的 ${nameMap[provider] || provider} API Key`;
    input.required = true;
  }
}

// ── Export modal ──

export async function openExportModal() {
  const idx = state.currentSlotIndex;
  if (idx === null) return;

  if (document.querySelector(".export-content")) return;

  try {
    const data = await apiGet(`/api/slots/${idx}/chat/export`);

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

function syncSystemPromptSource() {
  // 仅双模型模式同步（单模型模式的提示词在 step3 单独输入，不可被覆盖）
  if (!isDualMode) return;
  const sp = document.getElementById("create-system-prompt").value;
  const spSingle = document.getElementById("create-system-prompt-single");
  if (spSingle) spSingle.value = sp;
}

export function initModalListeners() {
  const createModal = document.getElementById("create-modal");

  // ── 模式选择 ──
  document.querySelectorAll('input[name="dual-mode"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      const singleRadio = document.getElementById("dual-option-single").querySelector("input");
      isDualMode = !singleRadio.checked;
      if (isDualMode) {
        // 双模型模式
        document.getElementById("field-model1-name").style.display = "block";
        document.getElementById("step1-icon").textContent = MODEL1_ICON;
        document.getElementById("step1-title").textContent = "模型 1 配置";
        // Step 2 显示模型1系统提示词
        document.getElementById("step2-prompt-field").style.display = "";
        // Step 3 显示模型2配置
        document.getElementById("step3-single").style.display = "none";
        document.getElementById("step3-dual").style.display = "block";
        document.getElementById("step3-icon").textContent = MODEL2_ICON;
        document.getElementById("step3-title").textContent = "模型 2 配置";
        populateModelSelect("create-model2-select", "DeepSeek-v4-flash");
      } else {
        document.getElementById("field-model1-name").style.display = "none";
        document.getElementById("step1-icon").textContent = "🤖";
        document.getElementById("step1-title").textContent = "选择模型";
        // Step 2 隐藏系统提示词（单模型的提示词在 Step 3）
        document.getElementById("step2-prompt-field").style.display = "none";
        document.getElementById("step3-single").style.display = "";
        document.getElementById("step3-dual").style.display = "none";
        document.getElementById("step3-icon").textContent = "💬";
        document.getElementById("step3-title").textContent = "设置提示词";
      }
      showStep(0); // 停留在步骤0，但更新UI
    });
  });

  // ── 步骤导航 ──
  document.getElementById("wizard-next").addEventListener("click", () => {
    if (currentStep === 0) {
      // 从模式选择进入
      if (isDualMode) {
        showStep(1);
      } else {
        showStep(1);
      }
    } else if (currentStep === 1) {
      // Step 1 → Step 2（校验API Key）
      const apiKeyField = document.getElementById("api-key-field");
      const apiKeyInput = document.getElementById("create-api-key");
      if (apiKeyField.style.display !== "none" && !apiKeyInput.value.trim()) {
        showToast("请填写该模型所需的 API 密钥", "warning");
        apiKeyInput.focus();
        return;
      }
      showStep(2);
    } else if (currentStep === 2) {
      if (isDualMode) {
        // 双模型: step 2 → step 3 (模型2)
        syncSystemPromptSource();
        showStep(3);
      } else {
        // 单模型: step 2 的参数结束 → step 3 提示词
        syncSystemPromptSource();
        showStep(3);
      }
    } else if (currentStep === 3) {
      if (isDualMode) {
        // 校验模型2 API Key
        const apiKeyField2 = document.getElementById("api-key-field-2");
        const apiKeyInput2 = document.getElementById("create-api-key-2");
        if (apiKeyField2.style.display !== "none" && !apiKeyInput2.value.trim()) {
          showToast("请填写模型 2 所需的 API 密钥", "warning");
          apiKeyInput2.focus();
          return;
        }
        showStep(4);
      }
    } else if (currentStep === 4) {
      if (isDualMode) {
        showStep(5); // 标题
      }
    }
  });

  document.getElementById("wizard-prev").addEventListener("click", () => {
    if (currentStep > 0) {
      showStep(currentStep - 1);
    }
  });

  document.getElementById("wizard-cancel").addEventListener("click", closeCreateModal);

  // ── 创建存档 ──
  document.getElementById("wizard-create").addEventListener("click", async () => {
    const idx = pendingCreateIndex;
    if (idx === null) return;

    if (isDualMode) {
      // ── 双模型创建 ──
      const model1Select = document.getElementById("create-model-select");
      const model1Name = document.getElementById("create-model1-name").value.trim() || "1号";
      const model1Model = model1Select.value;
      const model1Key = document.getElementById("api-key-field").style.display !== "none"
        ? document.getElementById("create-api-key").value.trim() : "";
      const model1Prompt = document.getElementById("create-system-prompt").value.trim() || "使用中文回答";
      const model1Params = getParamValues("");

      const model2Select = document.getElementById("create-model2-select");
      const model2Name = document.getElementById("create-model2-name").value.trim() || "2号";
      const model2Model = model2Select.value;
      const model2Key = document.getElementById("api-key-field-2").style.display !== "none"
        ? document.getElementById("create-api-key-2").value.trim() : "";
      const model2Prompt = document.getElementById("create-system-prompt-2").value.trim() || "使用中文回答";
      const model2Params = getParamValues("2");

      try {
        await apiPost(`/api/slots/${idx}`, {
          model: model1Model,
          system_prompt: model1Prompt,
          api_key: model1Key,
          params: model1Params,
          title: document.getElementById("create-title-dual").value.trim(),
          dual_enabled: true,
          model1_name: model1Name,
          model2_name: model2Name,
          pass_mode: document.querySelector('input[name="pass-mode"]:checked')?.value || "user",
          model2: {
            model: model2Model,
            system_prompt: model2Prompt,
            api_key: model2Key,
            params: model2Params,
          },
        });
        closeCreateModal();
        showToast("双模型存档创建成功", "success");
        await openSlot(idx);
      } catch (e) {
        showToast("创建失败: " + e.message, "error");
      }
    } else {
      // ── 单模型创建（原有逻辑） ──
      const select = document.getElementById("create-model-select");
      const promptInput = document.getElementById("create-system-prompt-single");
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
          params: getParamValues(""),
        });
        closeCreateModal();
        showToast("存档创建成功", "success");
        await openSlot(idx);
      } catch (e) {
        showToast("创建失败: " + e.message, "error");
      }
    }
  });

  // 关闭弹窗
  createModal.addEventListener("click", (e) => {
    if (e.target === createModal) closeCreateModal();
  });

  // 模型切换 API Key 联动
  document.getElementById("create-model-select").addEventListener("change", updateApiKeyField);
  document.getElementById("create-model2-select").addEventListener("change", updateApiKeyField2);

  // 参数滑块联动
  const setupRangeListeners = (suffix = "") => {
    const ids = [
      "temperature", "top-p", "min-p", "top-k",
      "repeat-penalty", "presence-penalty", "frequency-penalty",
    ];
    ids.forEach((id) => {
      const input = document.getElementById(`param${suffix}-${id}`);
      if (input) {
        input.addEventListener("input", () => {
          const display = document.getElementById(`param${suffix}-${id}-val`);
          if (display) display.textContent = input.value;
        });
      }
    });
  };
  setupRangeListeners("");
  setupRangeListeners("2");

  // 确认弹窗
  document.getElementById("modal-overlay").addEventListener("click", (e) => {
    if (e.target === document.getElementById("modal-overlay")) {
      document.getElementById("modal-overlay").classList.add("hidden");
    }
  });

  // 帮助弹窗
  document.getElementById("help-modal").addEventListener("click", (e) => {
    if (e.target === document.getElementById("help-modal")) {
      closeHelpModal();
    }
  });
}
