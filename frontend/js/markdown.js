/**
 * Markdown rendering and code-block enhancement.
 */
import { marked } from "marked";
import hljs from "highlight.js";

// ── Configure marked ──

marked.setOptions({
  gfm: true,
  breaks: true,
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value;
      } catch (_) { /* fall through */ }
    }
    try {
      return hljs.highlightAuto(code).value;
    } catch (_) { /* fall through */ }
    return code;
  },
});

// ── Render ──

export function renderMarkdown(text) {
  try {
    return marked.parse(text);
  } catch (_) {
    return text.replace(/\n/g, "<br>");
  }
}

// ── Code-block enhancement (copy button) ──

export function enhanceCodeBlocks(container) {
  container.querySelectorAll("pre").forEach((pre) => {
    if (pre.querySelector(".code-header")) return;

    const code = pre.querySelector("code");
    if (!code) return;

    const lang = (code.className.match(/language-(\w+)/) || [])[1] || "";
    const header = document.createElement("div");
    header.className = "code-header";
    header.innerHTML = `
      <span class="code-lang">${lang || "code"}</span>
      <button class="copy-btn">复制</button>
    `;

    const copyBtn = header.querySelector(".copy-btn");
    copyBtn.addEventListener("click", () => {
      const text = code.textContent || "";
      navigator.clipboard
        .writeText(text)
        .then(() => {
          copyBtn.textContent = "✓ 已复制";
          copyBtn.classList.add("copied");
          setTimeout(() => {
            copyBtn.textContent = "复制";
            copyBtn.classList.remove("copied");
          }, 2000);
        })
        .catch(() => {
          copyBtn.textContent = "复制失败";
          copyBtn.classList.add("copied");
          setTimeout(() => {
            copyBtn.textContent = "复制";
            copyBtn.classList.remove("copied");
          }, 2000);
        });
    });

    pre.parentNode.insertBefore(header, pre);
  });

  // Re-highlight
  container.querySelectorAll("pre code").forEach((block) => {
    try {
      hljs.highlightElement(block);
    } catch (_) { /* ignore */ }
  });
}
