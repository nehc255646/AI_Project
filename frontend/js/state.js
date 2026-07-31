/**
 * Global application state.
 *
 * Centralised so modules can share state without DOM queries or
 * passing values through call chains.
 */

export const state = {
  view: "slots",           // "slots" | "chat"
  slots: [],
  currentSlotIndex: null,
  currentSlotData: null,
  streaming: false,
  abortController: null,
  currentReader: null,     // SSE reader，用于直接取消
  streamCancelled: false,  // 取消标志（双重保障）
  models: [],
  envStatus: {},
  // 双模型状态
  dualEnabled: false,
  responseMode: "both",     // "model1" | "model2" | "both"
  firstModel: "model1",     // "model1" | "model2"
};
