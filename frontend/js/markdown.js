/**
 * Markdown 渲染与代码块增强（复制按钮、语法高亮）。
 */
import { marked } from "marked";
import hljs from "highlight.js/lib/core";

import javascript from "highlight.js/lib/languages/javascript";
import typescript from "highlight.js/lib/languages/typescript";
import python from "highlight.js/lib/languages/python";
import bash from "highlight.js/lib/languages/bash";
import json from "highlight.js/lib/languages/json";
import xml from "highlight.js/lib/languages/xml";
import css from "highlight.js/lib/languages/css";
import sql from "highlight.js/lib/languages/sql";
import java from "highlight.js/lib/languages/java";
import cpp from "highlight.js/lib/languages/cpp";
import csharp from "highlight.js/lib/languages/csharp";
import go from "highlight.js/lib/languages/go";
import rust from "highlight.js/lib/languages/rust";
import yaml from "highlight.js/lib/languages/yaml";
import markdownLang from "highlight.js/lib/languages/markdown";

// 按需注册常用语言
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("python", python);
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("shell", bash);
hljs.registerLanguage("json", json);
hljs.registerLanguage("xml", xml);
hljs.registerLanguage("html", xml);
hljs.registerLanguage("css", css);
hljs.registerLanguage("sql", sql);
hljs.registerLanguage("java", java);
hljs.registerLanguage("cpp", cpp);
hljs.registerLanguage("c", cpp);
hljs.registerLanguage("csharp", csharp);
hljs.registerLanguage("go", go);
hljs.registerLanguage("rust", rust);
hljs.registerLanguage("yaml", yaml);
hljs.registerLanguage("markdown", markdownLang);

// ── 配置 marked ──

marked.setOptions({
  gfm: true,
  breaks: true,
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value;
      } catch (_) { /* 继续后续逻辑 */ }
    }
    try {
      return hljs.highlightAuto(code).value;
    } catch (_) { /* 继续后续逻辑 */ }
    return code;
  },
});

// ── 渲染 ──

const DISALLOWED_TAGS = new Set([
  "script", "style", "iframe", "object", "embed", "link", "meta", "base",
  "form", "input", "button", "textarea", "select", "option", "video", "audio",
  "source", "frame", "frameset", "svg", "math", "noscript", "template", "dialog",
]);

const ALLOWED_ATTRS = new Set([
  "class", "id", "title", "alt", "target", "rel", "width", "height",
  "dir", "lang", "start", "type", "value", "align", "role", "aria-hidden",
  "spellcheck", "data-language",
]);

/** 移除危险标签与属性（on* 事件、javascript: 协议等），防止 AI 输出注入 HTML */
function sanitizeHtml(html) {
  const template = document.createElement("template");
  template.innerHTML = html;

  const walk = (parent) => {
    for (const child of [...parent.children]) {
      const tag = child.tagName.toLowerCase();
      if (DISALLOWED_TAGS.has(tag)) {
        child.remove();
        continue;
      }
      for (const attr of [...child.attributes]) {
        const name = attr.name.toLowerCase();
        const value = (attr.value || "").trim().toLowerCase();
        if (name.startsWith("on") || name === "style") {
          child.removeAttribute(attr.name);
        } else if (
          (name === "href" || name === "src") &&
          (value.startsWith("javascript:") || value.startsWith("vbscript:") ||
           (value.startsWith("data:") && !value.startsWith("data:image/")))
        ) {
          child.removeAttribute(attr.name);
        } else if (!ALLOWED_ATTRS.has(name)) {
          child.removeAttribute(attr.name);
        }
      }
      walk(child);
    }
  };
  walk(template.content);
  return template.innerHTML;
}

export function renderMarkdown(text) {
  try {
    return sanitizeHtml(marked.parse(text));
  } catch (_) {
    return text.replace(/\n/g, "<br>");
  }
}

// ── 代码块增强（复制按钮） ──

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

  // 重新高亮
  container.querySelectorAll("pre code").forEach((block) => {
    try {
      hljs.highlightElement(block);
    } catch (_) { /* 忽略 */ }
  });
}
