import { el, formatDate, toast } from "./ui.js";
import { socket } from "./ws.js";

function actionClass(action) {
  if (!action) return "";
  if (action.startsWith("LOGIN")) return "info";
  if (action.startsWith("WIFI")) return "online";
  if (action.startsWith("SYSTEM")) return "pending";
  if (action.startsWith("DEVICE") && action.includes("FAILED")) return "offline";
  if (action.includes("FAILED") || action.includes("BLOCKED")) return "offline";
  return "";
}

export function renderAudit(entries) {
  const body = el("auditBody");
  if (!body) return;
  body.textContent = "";

  if (!entries.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "empty-state";
    cell.textContent = "Sin eventos.";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }

  for (const entry of entries) {
    const row = document.createElement("tr");

    const date = document.createElement("td");
    date.className = "mono";
    date.textContent = formatDate(entry.created_at);

    const action = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `badge ${actionClass(entry.action)}`;
    badge.textContent = entry.action;
    action.appendChild(badge);

    const actor = document.createElement("td");
    actor.textContent = entry.actor || "SYSTEM";

    const device = document.createElement("td");
    device.className = "mono";
    device.textContent = entry.device_id || "—";

    const details = document.createElement("td");
    details.textContent = entry.details || "—";

    row.append(date, action, actor, device, details);
    body.appendChild(row);
  }
}

export async function loadAudit() {
  const action = el("auditFilterAction")?.value.trim() || "";
  const deviceId = el("auditFilterDevice")?.value.trim() || "";
  try {
    const result = await socket.request({
      event: "get_audit",
      action,
      device_id: deviceId,
    });
    if (result.event === "audit_result") {
      renderAudit(result.entries || []);
    } else {
      toast(result.message || "No se pudo consultar la auditoría", "error");
    }
  } catch (error) {
    toast(error.message, "error");
  }
}

export function initAudit() {
  el("btnRefreshAudit")?.addEventListener("click", loadAudit);
}
