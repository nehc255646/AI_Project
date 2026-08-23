/**
 * 自定义全局背景管理 — 图片选择、上传/删除、透明度与模糊度调节。
 *
 * 设置持久化到 localStorage（ai_chat_background）：
 *   { enabled: boolean, url: string, opacity: 0-1, blur: px }
 * 背景图来源为后端 /backgrounds 静态目录（可手动放文件或弹层内上传）。
 */

import { apiGet } from "./api.js";
import { showToast } from "./toast.js";

const STORAGE_KEY = "ai_chat_background";
const DEFAULTS = { enabled: false, url: "", opacity: 0.35, blur: 0 };

let settings = { ...DEFAULTS };
let uploadedUrl = ""; // 本次会话刚上传的图片，便于上传后自动选中

/** 读取设置（容错：解析失败回退默认） */
function loadSettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      settings = {
        enabled: !!parsed.enabled && typeof parsed.url === "string" && parsed.url !== "",
        url: typeof parsed.url === "string" ? parsed.url : "",
        opacity: clamp(Number(parsed.opacity), DEFAULTS.opacity),
        blur: Math.max(0, Math.min(20, Number(parsed.blur) || 0)),
      };
    }
  } catch (_) { /* ignore */ }
}

function clamp(v, fallback) {
  return Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : fallback;
}

function saveSettings() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch (_) { /* ignore */ }
}

/** 把设置应用到 DOM（CSS 变量 + 图层显隐） */
export function applyBackground() {
  const root = document.documentElement;
  const layer = document.getElementById("bg-layer");
  if (!layer) return;

  const active = settings.enabled && settings.url;
  root.style.setProperty("--bg-image", active ? `url("${settings.url}")` : "none");
  root.style.setProperty("--bg-dim", String(settings.enabled ? settings.opacity : 0));
  root.style.setProperty("--bg-blur", `${settings.blur}px`);
  layer.classList.toggle("active", !!active);
}

function persistAndApply() {
  saveSettings();
  applyBackground();
  syncControls();
}

// ── 弹层 UI ──

async function renderGallery() {
  const grid = document.getElementById("bg-gallery");
  if (!grid) return;
  grid.innerHTML = `<div class="bg-gallery-loading">加载中…</div>`;

  let items = [];
  try {
    items = await apiGet("/api/backgrounds");
  } catch (e) {
    grid.innerHTML = `<div class="bg-gallery-empty">图片加载失败：${e.message}</div>`;
    return;
  }
  if (!items.length) {
    grid.innerHTML = `<div class="bg-gallery-empty">暂无背景图，点击上方按钮上传，
或手动放入 backend/backgrounds/ 目录</div>`;
    return;
  }

  grid.innerHTML = items.map((it) => `
    <button class="bg-thumb ${settings.url === it.url ? "selected" : ""}"
            data-bg-url="${it.url}" data-bg-name="${it.name}" type="button"
            title="${it.name}">
      <img src="${it.url}" alt="${it.name}" loading="lazy">
      <span class="bg-thumb-delete" data-bg-name="${it.name}" data-bg-url="${it.url}" title="删除">✕</span>
    </button>
  `).join("");
}

function syncControls() {
  const enableToggle = document.getElementById("bg-enable-toggle");
  const opacitySlider = document.getElementById("bg-opacity-slider");
  const blurSlider = document.getElementById("bg-blur-slider");
  const opacityValue = document.getElementById("bg-opacity-value");
  const blurValue = document.getElementById("bg-blur-value");

  if (enableToggle) enableToggle.checked = settings.enabled;
  if (opacitySlider) opacitySlider.value = String(Math.round(settings.opacity * 100));
  if (blurSlider) blurSlider.value = String(settings.blur);
  if (opacityValue) opacityValue.textContent = `${Math.round(settings.opacity * 100)}%`;
  if (blurValue) blurValue.textContent = `${settings.blur}px`;

  // 无选中图片时禁用调节项
  const disabled = !settings.url;
  [opacitySlider, blurSlider].forEach((el) => { if (el) el.disabled = disabled; });
  document.getElementById("bg-clear-btn")?.classList.toggle("disabled", !settings.url);
}

/** 绑定主题弹层内的背景区块事件（幂等） */
let wired = false;
function wireEvents() {
  if (wired) return;
  wired = true;

  $("#bg-upload-btn")?.addEventListener("click", () => $("#bg-upload-input")?.click());

  $("#bg-upload-input")?.addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    await uploadBackground(file);
  });

  // 拖拽上传
  const zone = $("#bg-upload-btn")?.closest(".bg-actions");
  ["dragover", "dragleave", "drop"].forEach((evt) => {
    zone?.addEventListener(evt, (e) => {
      e.preventDefault();
      zone.classList.toggle("dragover", evt === "dragover");
      if (evt === "drop") {
        const file = e.dataTransfer?.files?.[0];
        if (file) uploadBackground(file);
      }
    });
  });

  // 缩略图选择 / 删除（事件委托）
  $("#bg-gallery")?.addEventListener("click", async (e) => {
    const delBtn = e.target.closest(".bg-thumb-delete");
    if (delBtn) {
      await deleteBackground(delBtn.dataset.bgName, delBtn.dataset.bgUrl);
      return;
    }
    const thumb = e.target.closest(".bg-thumb");
    if (!thumb) return;
    settings.url = thumb.dataset.bgUrl;
    settings.enabled = true;
    persistAndApply();
    markSelected(thumb.dataset.bgUrl);
  });

  // 启用开关
  $("#bg-enable-toggle")?.addEventListener("change", (e) => {
    if (!settings.url && e.target.checked) {
      showToast("请先选择一张背景图", "warning");
      e.target.checked = false;
      return;
    }
    settings.enabled = e.target.checked;
    persistAndApply();
  });

  // 滑杆
  $("#bg-opacity-slider")?.addEventListener("input", (e) => {
    settings.opacity = Number(e.target.value) / 100;
    applyBackground();
    const v = $("#bg-opacity-value"); if (v) v.textContent = `${e.target.value}%`;
  });
  $("#bg-opacity-slider")?.addEventListener("change", saveSettings);

  $("#bg-blur-slider")?.addEventListener("input", (e) => {
    settings.blur = Number(e.target.value);
    applyBackground();
    const v = $("#bg-blur-value"); if (v) v.textContent = `${e.target.value}px`;
  });
  $("#bg-blur-slider")?.addEventListener("change", saveSettings);

  // 清除
  $("#bg-clear-btn")?.addEventListener("click", () => {
    settings = { ...DEFAULTS };
    persistAndApply();
    renderGallery();
  });
}

function $(sel) { return document.querySelector(sel); }

function markSelected(url) {
  document.querySelectorAll("#bg-gallery .bg-thumb").forEach((el) => {
    el.classList.toggle("selected", el.dataset.bgUrl === url);
  });
}

async function uploadBackground(file) {
  if (!/^image\//.test(file.type)) {
    showToast("仅支持图片文件", "error");
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    showToast("图片不能超过 10MB", "error");
    return;
  }
  const btn = $("#bg-upload-btn");
  if (btn) btn.disabled = true;
  try {
    // FormData 上传不能手动设置 Content-Type（需保留 multipart boundary）
    const res = await fetch("/api/backgrounds", { method: "POST", body: (() => {
      const fd = new FormData();
      fd.append("file", file);
      return fd;
    })() });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);

    uploadedUrl = data.url;
    settings.url = data.url;
    settings.enabled = true;
    persistAndApply();
    await renderGallery();
    markSelected(data.url);
    showToast("背景已上传并应用", "success");
  } catch (err) {
    showToast("上传失败：" + err.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function deleteBackground(name, url) {
  try {
    const res = await fetch(`/api/backgrounds/${encodeURIComponent(name)}`, { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
    showToast("背景图已删除", "success");
    // 若删除的是当前使用的背景则一并停用
    if (settings.url === url) {
      settings = { ...DEFAULTS };
      persistAndApply();
    }
    await renderGallery();
  } catch (err) {
    showToast("删除失败：" + err.message, "error");
  }
}

/** 打开主题弹层时刷新画廊与控件状态 */
export function refreshBackgroundPanel() {
  syncControls();
  renderGallery();
}

/** 启动初始化 */
export function initBackground() {
  loadSettings();
  applyBackground();
  wireEvents();
}
