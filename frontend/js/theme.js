/**
 * 主题管理 — 切换 data-theme（强调色）与 data-mode（明暗）、localStorage 持久化与选择弹层。
 */

const STORAGE_KEY = "ai_chat_theme";
const MODE_STORAGE_KEY = "ai_chat_theme_mode";

export const THEMES = [
  { key: "cosmic", name: "宇宙紫蓝", swatches: ["#8b5cf6", "#6366f1", "#3b82f6", "#06b6d4"] },
  { key: "emerald", name: "翡翠绿", swatches: ["#10b981", "#059669", "#14b8a6", "#22d3ee"] },
  { key: "sunset", name: "暖橙日落", swatches: ["#f97316", "#fb923c", "#f43f5e", "#eab308"] },
  { key: "sakura", name: "樱花粉", swatches: ["#ec4899", "#d946ef", "#f472b6", "#c084fc"] },
  { key: "ocean", name: "深海青", swatches: ["#0ea5e9", "#2563eb", "#06b6d4", "#67e8f9"] },
];

/** 应用主题：设置 <html data-theme> 并持久化（cosmic 为默认，移除属性） */
export function applyTheme(key) {
  const theme = THEMES.find((t) => t.key === key) || THEMES[0];
  if (theme.key === "cosmic") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", theme.key);
  }
  try {
    localStorage.setItem(STORAGE_KEY, theme.key);
  } catch (_) { /* 隐私模式等场景下静默失败 */ }
  document.querySelectorAll("#theme-list .theme-option").forEach((el) => {
    el.classList.toggle("active", el.dataset.themeKey === theme.key);
  });
}

/** 应用明暗模式：设置 <html data-mode> 并持久化（dark 为默认，移除属性） */
export function applyMode(mode) {
  const normalized = mode === "light" ? "light" : "dark";
  if (normalized === "light") {
    document.documentElement.setAttribute("data-mode", "light");
  } else {
    document.documentElement.removeAttribute("data-mode");
  }
  try {
    localStorage.setItem(MODE_STORAGE_KEY, normalized);
  } catch (_) { /* ignore */ }
  syncMetaThemeColor(normalized);
  document.querySelectorAll("#theme-list .mode-option").forEach((el) => {
    el.classList.toggle("active", el.dataset.modeKey === normalized);
  });
}

/** 同步浏览器地址栏/状态栏颜色 */
function syncMetaThemeColor(mode) {
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", mode === "light" ? "#f8fafc" : "#0a0e17");
}

/** 读取已保存的明暗模式；无记录时跟随系统偏好 */
function getInitialMode() {
  try {
    const saved = localStorage.getItem(MODE_STORAGE_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch (_) { /* ignore */ }
  try {
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  } catch (_) {
    return "dark";
  }
}

/** 启动时应用已保存的主题与明暗模式（head 内联脚本已提前设置，此处兜底并同步选中态） */
export function initTheme() {
  let saved = null;
  try {
    saved = localStorage.getItem(STORAGE_KEY);
  } catch (_) { /* ignore */ }
  if (saved) applyTheme(saved);
  applyMode(getInitialMode());
}

/** 打开主题选择弹层（顶部为深浅色分段切换，下方为彩色主题列表） */
export function openThemeModal() {
  const list = document.getElementById("theme-list");
  const modal = document.getElementById("theme-modal");
  if (!list || !modal) return;

  let current = "cosmic";
  try { current = localStorage.getItem(STORAGE_KEY) || "cosmic"; } catch (_) { /* ignore */ }
  let currentMode = "dark";
  try { currentMode = localStorage.getItem(MODE_STORAGE_KEY) || "dark"; } catch (_) { /* ignore */ }

  if (!list.dataset.rendered) {
    list.innerHTML = `
      <div class="mode-switch">
        <button class="mode-option" data-mode-key="dark" type="button">🌙 深色</button>
        <button class="mode-option" data-mode-key="light" type="button">☀️ 浅色</button>
      </div>
      ` + THEMES.map(
        (t) => `
      <button class="theme-option" data-theme-key="${t.key}" type="button">
        <span class="theme-swatch-row">
          ${t.swatches.map((c) => `<span class="theme-swatch" style="background:${c}"></span>`).join("")}
        </span>
        <span class="theme-name">${t.name}</span>
        <span class="theme-check">✓</span>
      </button>`
      ).join("");
    list.dataset.rendered = "1";
    list.addEventListener("click", (e) => {
      const modeOpt = e.target.closest(".mode-option");
      if (modeOpt) {
        applyMode(modeOpt.dataset.modeKey);
        return;
      }
      const opt = e.target.closest(".theme-option");
      if (opt) applyTheme(opt.dataset.themeKey);
    });
  }

  list.querySelectorAll(".theme-option").forEach((el) => {
    el.classList.toggle("active", el.dataset.themeKey === current);
  });
  list.querySelectorAll(".mode-option").forEach((el) => {
    el.classList.toggle("active", el.dataset.modeKey === currentMode);
  });

  modal.classList.remove("hidden");
}

/** 关闭主题选择弹层 */
export function closeThemeModal() {
  document.getElementById("theme-modal")?.classList.add("hidden");
}
