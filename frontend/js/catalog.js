/**
 * 模型目录 — 用户自建 OpenAI 兼容供应商与模型。
 */

import { state } from "./state.js";
import { apiGet, apiPost, apiPatch, apiDelete } from "./api.js";
import { showToast } from "./toast.js";
import { showConfirm } from "./confirm.js";
import { escapeHtml } from "./utils.js";

let selectedId = null; // null = 新建
let draftModels = []; // { localId, id?, model_id, display_name }

export async function refreshCatalog() {
  try {
    state.providers = await apiGet("/api/providers");
  } catch (e) {
    state.providers = [];
    throw e;
  }
  try {
    state.models = await apiGet("/api/models");
  } catch (_) {
    state.models = [];
  }
}

export async function initCatalog() {
  try {
    await refreshCatalog();
  } catch (e) {
    showToast("加载模型目录失败: " + e.message, "error");
  }
}

export function openCatalogModal() {
  const modal = document.getElementById("catalog-modal");
  if (!modal) return;
  modal.classList.remove("hidden");
  selectedId = (state.providers && state.providers[0]) ? state.providers[0].id : "new";
  if (selectedId === "new" || !state.providers?.length) {
    selectedId = "new";
    startNewDraft();
  } else {
    loadProviderIntoForm(selectedId);
  }
  renderProviderList();
  renderForm();
}

export function closeCatalogModal() {
  document.getElementById("catalog-modal")?.classList.add("hidden");
}

function startNewDraft() {
  selectedId = "new";
  draftModels = [emptyModelRow()];
}

function emptyModelRow() {
  return { localId: "n" + Math.random().toString(36).slice(2, 8), id: null, model_id: "", display_name: "" };
}

function currentProvider() {
  if (selectedId === "new" || selectedId == null) return null;
  return (state.providers || []).find((p) => p.id === selectedId) || null;
}

function loadProviderIntoForm(id) {
  selectedId = id;
  const p = currentProvider();
  draftModels = (p?.models || []).map((m) => ({
    localId: "m" + m.id,
    id: m.id,
    model_id: m.model_id || "",
    display_name: m.display_name || "",
  }));
  if (!draftModels.length) draftModels = [emptyModelRow()];
}

function renderProviderList() {
  const list = document.getElementById("catalog-provider-list");
  if (!list) return;
  const providers = state.providers || [];
  if (!providers.length) {
    list.innerHTML = `<div class="catalog-empty-side">还没有供应商</div>`;
  } else {
    list.innerHTML = providers.map((p) => {
      const active = p.id === selectedId ? "active" : "";
      const count = (p.models || []).length;
      return `<button type="button" class="catalog-provider-item ${active}" data-id="${p.id}">
        <span class="catalog-provider-name">${escapeHtml(p.display_name || p.slug)}</span>
        <span class="catalog-provider-meta">${escapeHtml(p.slug)} · ${count} 个模型</span>
      </button>`;
    }).join("");
  }
  list.querySelectorAll(".catalog-provider-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      loadProviderIntoForm(parseInt(btn.dataset.id, 10));
      renderProviderList();
      renderForm();
    });
  });
}

function renderForm() {
  const wrap = document.getElementById("catalog-form-wrap");
  if (!wrap) return;
  const p = currentProvider();
  const isNew = selectedId === "new" || !p;
  const useEnv = isNew ? false : !!p.use_env_key;

  wrap.innerHTML = `
    <div class="catalog-form-header">
      <div>
        <div class="catalog-form-title">${isNew ? "✨ 自定义提供商" : "编辑提供商"}</div>
        <p class="catalog-form-hint">配置与 OpenAI 兼容的提供商（chat/completions）。</p>
      </div>
    </div>
    <div class="create-field">
      <label class="create-label">提供商 ID</label>
      <input type="text" id="cat-slug" class="create-input" maxlength="64"
        placeholder="myprovider" ${isNew ? "" : "disabled"}
        value="${escapeHtml(isNew ? "" : (p.slug || ""))}" />
      <p class="create-hint">使用小写字母、数字、连字符或下划线，创建后不可修改</p>
    </div>
    <div class="create-field">
      <label class="create-label">显示名称</label>
      <input type="text" id="cat-name" class="create-input" maxlength="64"
        placeholder="我的 AI 提供商" value="${escapeHtml(isNew ? "" : (p.display_name || ""))}" />
    </div>
    <div class="create-field">
      <label class="create-label">基础 URL</label>
      <input type="text" id="cat-base-url" class="create-input" maxlength="512"
        placeholder="https://api.myprovider.com/v1"
        value="${escapeHtml(isNew ? "" : (p.base_url || ""))}" />
    </div>
    <div class="create-field">
      <label class="pass-mode-option catalog-env-row">
        <input type="checkbox" id="cat-use-env" ${useEnv ? "checked" : ""} />
        <span>从环境变量读取 API 密钥</span>
      </label>
    </div>
    <div class="create-field" id="cat-env-field" style="${useEnv ? "" : "display:none"}">
      <label class="create-label">环境变量名</label>
      <input type="text" id="cat-env-name" class="create-input" maxlength="64"
        placeholder="MYPROVIDER_API_KEY"
        value="${escapeHtml(isNew ? "" : (p.api_key_env || ""))}" />
      <p class="create-hint">运行时读取该变量；创建时不必已经设置</p>
    </div>
    <div class="create-field" id="cat-key-field" style="${useEnv ? "display:none" : ""}">
      <label class="create-label">API 密钥</label>
      <input type="password" id="cat-api-key" class="create-input" maxlength="256"
        placeholder="${isNew ? "可选。本地无鉴权端点可留空" : (p.has_api_key ? "已保存，留空保持不变" : "可选。本地无鉴权端点可留空")}"
        autocomplete="off" />
      <p class="create-hint">可选。如果你通过环境变量管理认证，可勾选上方选项。</p>
    </div>
    <div class="create-field">
      <label class="create-label">模型</label>
      <div id="cat-model-rows"></div>
      <button type="button" class="catalog-text-btn" id="cat-add-model">+ 添加模型</button>
    </div>
    <div class="catalog-form-actions">
      <button type="button" class="modal-btn modal-btn-confirm" id="cat-save-btn">保存</button>
      ${isNew ? "" : `<button type="button" class="modal-btn modal-btn-cancel catalog-danger" id="cat-delete-btn">删除供应商</button>`}
    </div>
  `;

  document.getElementById("cat-use-env")?.addEventListener("change", (e) => {
    const on = e.target.checked;
    document.getElementById("cat-env-field").style.display = on ? "" : "none";
    document.getElementById("cat-key-field").style.display = on ? "none" : "";
  });
  document.getElementById("cat-add-model")?.addEventListener("click", () => {
    collectDraftModelsFromDom();
    draftModels.push(emptyModelRow());
    renderModelRows();
  });
  document.getElementById("cat-save-btn")?.addEventListener("click", saveForm);
  document.getElementById("cat-delete-btn")?.addEventListener("click", deleteCurrentProvider);
  renderModelRows();
}

function renderModelRows() {
  const box = document.getElementById("cat-model-rows");
  if (!box) return;
  box.innerHTML = draftModels.map((m) => `
    <div class="catalog-model-row" data-local="${escapeHtml(m.localId)}">
      <input type="text" class="create-input cat-mid" placeholder="model-id" value="${escapeHtml(m.model_id)}" />
      <input type="text" class="create-input cat-dname" placeholder="显示名称" value="${escapeHtml(m.display_name)}" />
      <button type="button" class="catalog-icon-btn cat-test" title="发送 hello 测试" ${m.id ? "" : "disabled"}>${m.id ? "测试" : "—"}</button>
      <button type="button" class="catalog-icon-btn cat-del" title="删除">🗑</button>
    </div>
    <div class="catalog-test-result" data-result-for="${escapeHtml(m.localId)}"></div>
  `).join("");

  box.querySelectorAll(".catalog-model-row").forEach((row) => {
    const localId = row.dataset.local;
    row.querySelector(".cat-del")?.addEventListener("click", () => removeModelRow(localId));
    row.querySelector(".cat-test")?.addEventListener("click", () => testModelRow(localId, row.querySelector(".cat-test")));
  });
}

function collectDraftModelsFromDom() {
  const box = document.getElementById("cat-model-rows");
  if (!box) return;
  box.querySelectorAll(".catalog-model-row").forEach((row) => {
    const localId = row.dataset.local;
    const item = draftModels.find((m) => m.localId === localId);
    if (!item) return;
    item.model_id = row.querySelector(".cat-mid")?.value.trim() || "";
    item.display_name = row.querySelector(".cat-dname")?.value.trim() || "";
  });
}

async function removeModelRow(localId) {
  collectDraftModelsFromDom();
  const item = draftModels.find((m) => m.localId === localId);
  if (!item) return;
  if (item.id && selectedId !== "new") {
    const ok = await showConfirm("确定删除这个模型吗？被存档引用时将无法删除。", true);
    if (!ok) return;
    try {
      await apiDelete(`/api/providers/${selectedId}/models/${item.id}`);
      showToast("模型已删除", "success");
      await refreshCatalog();
    } catch (e) {
      showToast(e.message || "删除失败", "error");
      return;
    }
  }
  draftModels = draftModels.filter((m) => m.localId !== localId);
  if (!draftModels.length) draftModels = [emptyModelRow()];
  const p = currentProvider();
  if (p) {
    const fresh = (state.providers || []).find((x) => x.id === selectedId);
    if (fresh) loadProviderIntoForm(selectedId);
  }
  renderProviderList();
  renderModelRows();
}

async function testModelRow(localId, btn) {
  collectDraftModelsFromDom();
  const item = draftModels.find((m) => m.localId === localId);
  const resultEl = document.querySelector(`[data-result-for="${localId}"]`);
  if (!item?.id || selectedId === "new") {
    showToast("请先保存供应商后再测试", "warning");
    return;
  }
  if (btn) {
    btn.disabled = true;
    btn.textContent = "…";
  }
  if (resultEl) resultEl.textContent = "正在测试…";
  try {
    const res = await apiPost(`/api/providers/${selectedId}/models/${item.id}/test`, {});
    if (res.ok) {
      const preview = res.preview ? ` → ${res.preview}` : "（空回复）";
      const msg = `成功 ${res.latency_ms}ms${preview}`;
      if (resultEl) resultEl.textContent = msg;
      showToast("测试成功", "success");
    } else {
      const msg = res.error || "测试失败";
      if (resultEl) resultEl.textContent = msg;
      showToast(msg, "error");
    }
  } catch (e) {
    if (resultEl) resultEl.textContent = e.message || "测试失败";
    showToast(e.message || "测试失败", "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "测试";
    }
  }
}

async function saveForm() {
  collectDraftModelsFromDom();
  const slug = document.getElementById("cat-slug")?.value.trim() || "";
  const displayName = document.getElementById("cat-name")?.value.trim() || "";
  const baseUrl = document.getElementById("cat-base-url")?.value.trim() || "";
  const useEnv = !!document.getElementById("cat-use-env")?.checked;
  const envName = document.getElementById("cat-env-name")?.value.trim() || "";
  const apiKey = document.getElementById("cat-api-key")?.value.trim() || "";
  const modelsPayload = draftModels
    .filter((m) => m.model_id)
    .map((m) => ({ model_id: m.model_id, display_name: m.display_name, id: m.id }));

  if (!displayName) {
    showToast("请填写显示名称", "warning");
    return;
  }
  if (!baseUrl) {
    showToast("请填写基础 URL", "warning");
    return;
  }
  if (useEnv && !envName) {
    showToast("请填写环境变量名", "warning");
    return;
  }

  const saveBtn = document.getElementById("cat-save-btn");
  if (saveBtn) saveBtn.disabled = true;
  try {
    if (selectedId === "new") {
      if (!slug) {
        showToast("请填写提供商 ID", "warning");
        return;
      }
      const created = await apiPost("/api/providers", {
        slug,
        display_name: displayName,
        base_url: baseUrl,
        api_key: useEnv ? "" : apiKey,
        use_env_key: useEnv,
        api_key_env: useEnv ? envName : "",
        models: modelsPayload.map(({ model_id, display_name }) => ({ model_id, display_name })),
      });
      await refreshCatalog();
      selectedId = created.id;
      loadProviderIntoForm(created.id);
      showToast("供应商已创建", "success");
    } else {
      const patch = {
        display_name: displayName,
        base_url: baseUrl,
        use_env_key: useEnv,
        api_key_env: useEnv ? envName : "",
      };
      if (!useEnv && apiKey) patch.api_key = apiKey;
      await apiPatch(`/api/providers/${selectedId}`, patch);
      for (const m of modelsPayload) {
        if (m.id) {
          await apiPatch(`/api/providers/${selectedId}/models/${m.id}`, {
            model_id: m.model_id,
            display_name: m.display_name,
          });
        } else {
          await apiPost(`/api/providers/${selectedId}/models`, {
            model_id: m.model_id,
            display_name: m.display_name,
          });
        }
      }
      await refreshCatalog();
      loadProviderIntoForm(selectedId);
      showToast("已保存", "success");
    }
    renderProviderList();
    renderForm();
  } catch (e) {
    showToast(e.message || "保存失败", "error");
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

async function deleteCurrentProvider() {
  if (selectedId === "new") return;
  const p = currentProvider();
  const ok = await showConfirm(`确定删除供应商「${p?.display_name || p?.slug || ""}」吗？其下模型会一并删除。`, true);
  if (!ok) return;
  try {
    await apiDelete(`/api/providers/${selectedId}`);
    await refreshCatalog();
    if (state.providers.length) {
      loadProviderIntoForm(state.providers[0].id);
    } else {
      startNewDraft();
    }
    renderProviderList();
    renderForm();
    showToast("供应商已删除", "success");
  } catch (e) {
    showToast(e.message || "删除失败", "error");
  }
}

export function bindCatalogUi() {
  document.getElementById("catalog-btn-slot")?.addEventListener("click", openCatalogModal);
  document.getElementById("catalog-btn-chat")?.addEventListener("click", openCatalogModal);
  document.getElementById("catalog-close-btn")?.addEventListener("click", closeCatalogModal);
  document.getElementById("catalog-modal")?.addEventListener("click", (e) => {
    if (e.target.id === "catalog-modal") closeCatalogModal();
  });
  document.getElementById("catalog-add-provider")?.addEventListener("click", () => {
    startNewDraft();
    renderProviderList();
    renderForm();
    document.getElementById("cat-slug")?.focus();
  });
}
