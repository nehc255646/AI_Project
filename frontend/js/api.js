/**
 * API helper functions with automatic retry.
 *
 * Uses exponential backoff for transient failures.
 */

const API_BASE = "";
const MAX_RETRIES = 2;

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function apiFetch(path, options = {}, retries = MAX_RETRIES) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });

      if (res.ok) {
        return res.json();
      }

      // Structured error handling
      let detail;
      try {
        detail = await res.json();
      } catch (_) {
        detail = { message: `请求失败: ${res.status}` };
      }

      // 4xx 错误不重试（客户端错误），标记后抛出
      if (res.status >= 400 && res.status < 500) {
        const err = new Error(detail.message || detail.detail || `HTTP ${res.status}`);
        err.status = res.status;
        throw err;
      }

      // 5xx 错误重试
      if (attempt < retries) {
        const delay = Math.min(1000 * Math.pow(2, attempt), 4000);
        await sleep(delay);
        continue;
      }

      throw new Error(detail.message || detail.detail || `HTTP ${res.status}`);
    } catch (e) {
      if (e.name === "AbortError") throw e;

      // 4xx 客户端错误不重试
      if (e.status && e.status >= 400 && e.status < 500) throw e;

      // 指数退避重试（网络断开、5xx 等临时故障）
      if (attempt < retries) {
        const delay = Math.min(1000 * Math.pow(2, attempt), 4000);
        await sleep(delay);
        continue;
      }

      // 重试耗尽后给出友好提示
      if (e instanceof TypeError && e.message === "Failed to fetch") {
        throw new Error("无法连接到服务器，请确认后端服务已启动");
      }
      throw e;
    }
  }
}

export function apiGet(path, options) {
  return apiFetch(path, { ...options, method: "GET" });
}

export function apiPost(path, body) {
  return apiFetch(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function apiPatch(path, body) {
  return apiFetch(path, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function apiDelete(path, body) {
  return apiFetch(path, {
    method: "DELETE",
    body: body ? JSON.stringify(body) : undefined,
  });
}
