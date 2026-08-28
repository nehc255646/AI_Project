/**
 * 全局应用状态 — 集中管理，供各模块共享。
 */

export const state = {
  view: "slots",           // "slots" | "chat"
  slots: [],
  currentSlotIndex: null,
  currentSlotData: null,
  streaming: false,
  abortController: null,
  currentReader: null,     // SSE 读取器，用于直接取消
  streamCancelled: false,  // 取消标志
  models: [],
  providers: [],
  envStatus: {},
  // 双模型状态
  dualEnabled: false,
  responseMode: "both",     // "model1" | "model2" | "both"
  firstModel: "model1",     // "model1" | "model2"
};
