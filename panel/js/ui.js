export function el(id) {
  return document.getElementById(id);
}

export function setText(id, value) {
  const node = el(id);
  if (node) {
    node.textContent = value === null || value === undefined || value === "" ? "—" : String(value);
  }
}

export function toast(message, type = "info", timeout = 4200) {
  const container = el("toastContainer");
  if (!container) return;
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.setAttribute("role", "status");
  node.textContent = message;
  container.appendChild(node);
  window.setTimeout(() => {
    node.style.opacity = "0";
    node.style.transform = "translateY(6px)";
    window.setTimeout(() => node.remove(), 220);
  }, timeout);
}

export function formatUptime(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "—";
  const days = Math.floor(value / 86400);
  const hours = Math.floor((value % 86400) / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function formatRssi(rssi) {
  const value = Number(rssi);
  if (!Number.isFinite(value) || value === 0) return "—";
  return `${value} dBm`;
}

export function signalLevel(rssi) {
  const value = Number(rssi);
  if (!Number.isFinite(value) || value === 0) return 0;
  if (value >= -55) return 4;
  if (value >= -67) return 3;
  if (value >= -78) return 2;
  return 1;
}

export function formatDate(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  return date.toLocaleString("es-ES", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export function closeModal() {
  const root = el("modalRoot");
  if (root) root.textContent = "";
}

export function openModal(title, contentNode, actions = []) {
  const root = el("modalRoot");
  if (!root) return null;
  root.textContent = "";

  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) closeModal();
  });

  const modal = document.createElement("div");
  modal.className = "modal";
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");

  const head = document.createElement("div");
  head.className = "modal-head";
  const heading = document.createElement("h2");
  heading.textContent = title;
  const close = document.createElement("button");
  close.className = "modal-close";
  close.type = "button";
  close.setAttribute("aria-label", "Cerrar");
  close.textContent = "×";
  close.addEventListener("click", closeModal);
  head.append(heading, close);

  const body = document.createElement("div");
  body.appendChild(contentNode);

  const footer = document.createElement("div");
  footer.className = "modal-actions";
  for (const action of actions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `btn ${action.className || "btn-ghost"}`;
    button.textContent = action.label;
    button.addEventListener("click", () => action.onClick && action.onClick());
    footer.appendChild(button);
  }

  modal.append(head, body, footer);
  overlay.appendChild(modal);
  root.appendChild(overlay);
  close.focus();
  return modal;
}

export function confirmAction(title, message, confirmLabel = "Confirmar", danger = true) {
  return new Promise((resolve) => {
    const content = document.createElement("p");
    content.className = "muted";
    content.textContent = message;
    openModal(title, content, [
      { label: "Cancelar", className: "btn-ghost", onClick: () => { closeModal(); resolve(false); } },
      {
        label: confirmLabel,
        className: danger ? "btn-danger" : "btn-primary",
        onClick: () => { closeModal(); resolve(true); },
      },
    ]);
  });
}
