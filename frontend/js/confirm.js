/**
 * Confirmation modal.
 */
export function showConfirm(message, danger = false) {
  return new Promise((resolve) => {
    const overlay = document.getElementById("modal-overlay");
    const msgEl = document.getElementById("modal-message");
    const confirmBtn = document.getElementById("modal-confirm");
    const cancelBtn = document.getElementById("modal-cancel");

    if (!overlay || !msgEl || !confirmBtn || !cancelBtn) {
      resolve(false);
      return;
    }

    msgEl.textContent = message;
    overlay.classList.remove("hidden");
    confirmBtn.classList.toggle("danger", danger);

    const cleanup = () => {
      overlay.classList.add("hidden");
      confirmBtn.onclick = null;
      cancelBtn.onclick = null;
    };

    confirmBtn.onclick = () => {
      cleanup();
      resolve(true);
    };
    cancelBtn.onclick = () => {
      cleanup();
      resolve(false);
    };
  });
}
