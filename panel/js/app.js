import { initAuth, tryResume } from "./auth.js";
import { initDevices, renderDashboard, renderDeviceSelect, updateDeviceStatus, updateRelayState, updateTelemetry } from "./devices.js";
import { initWifi, renderWifi, refreshWifi } from "./wifi.js";
import { initSystem } from "./system.js";
import { initAudit, loadAudit, renderAudit } from "./audit.js";
import { initTheme } from "./theme.js";
import { initRegister } from "./register.js";
import { state, selectedDevice } from "./state.js";
import { backendEndpoint, socket, on } from "./ws.js";
import { el, toast } from "./ui.js";

const VIEW_TITLES = {
  dashboard: "Dashboard",
  networks: "Redes WiFi",
  device: "Dispositivo",
  audit: "Auditoría",
  history: "Historial",
  lcd: "Configuración LCD",
  permissions: "Permisos",
};

let currentView = "dashboard";
let everConnected = false;

function setConnectionBadge(connected, text) {
  const badge = el("connStatusBadge");
  const label = el("connStatusText");
  if (!badge || !label) return;
  badge.className = `badge ${connected ? "online" : "offline"}`;
  label.textContent = text || (connected ? "Conectado" : "Desconectado");
}

function removeSystemView() {
  document.querySelector('[data-view="system"]')?.remove();
  el("view-system")?.remove();
}

function showView(name) {
  currentView = name;
  document.querySelectorAll(".view").forEach((view) => view.classList.add("hidden"));
  el(`view-${name}`)?.classList.remove("hidden");
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === name);
  });
  el("viewTitle").textContent = VIEW_TITLES[name] || name;
  if (name === "dashboard") renderDashboard(false);
  if (name === "networks") {
    renderWifi();
    const dev = selectedDevice();
    if (dev?.online) refreshWifi();
  }
  if (name === "device") renderDashboard(true);
  if (name === "audit") loadAudit();
}

function handleSync(message) {
  state.devices = Array.isArray(message.devices) ? message.devices : [];
  renderDeviceSelect();
  renderDashboard(true);
  renderWifi();
  if (currentView === "audit") loadAudit();
}

function authenticated() {
  setConnectionBadge(true, "Conectado");
  if (!everConnected) {
    everConnected = true;
    toast("Sesión autenticada", "success");
  }
  if (currentView === "audit") loadAudit();
}

function bindNav() {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => showView(item.dataset.view));
  });
}

function bindPasswordToggles() {
  document.querySelectorAll("[data-toggle-password]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = el(button.dataset.togglePassword);
      if (!input) return;
      const reveal = input.type === "password";
      input.type = reveal ? "text" : "password";
      button.textContent = reveal ? "Ocultar" : "Ver";
      button.setAttribute("aria-pressed", String(reveal));
    });
  });
}

function bindSocket() {
  on("open", async () => {
    setConnectionBadge(true, "Conectado");
    const resumed = await tryResume();
    if (!resumed) setConnectionBadge(true, "Sin sesión");
  });
  on("close", () => setConnectionBadge(false, "Reconectando…"));
  on("sync_all", handleSync);
  on("telemetry", updateTelemetry);
  on("relay_state", updateRelayState);
  on("device_status", updateDeviceStatus);
  on("audit_result", (message) => {
    if (Array.isArray(message.entries)) renderAudit(message.entries);
  });
  on("error", (message) => {
    if (!message.request_id) toast(message.message || message.code || "Error del backend", "error");
  });
}

function bindDeviceChanges() {
  window.addEventListener("device-changed", () => {
    const dev = selectedDevice();
    renderWifi();
    if (dev?.online && currentView === "networks") refreshWifi();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initRegister();
  removeSystemView();
  el("backendEndpoint").textContent = backendEndpoint();
  initAuth(authenticated);
  initDevices();
  initWifi();
  // initSystem conserva las acciones remotas del dispositivo (reinicio/sleep/reset),
  // pero el apartado de control de servicios del servidor ya no forma parte del panel.
  initSystem();
  initAudit();
  bindNav();
  bindPasswordToggles();
  bindSocket();
  bindDeviceChanges();
  bindRegisterToggle();
  showView("dashboard");
  socket.connect().catch(() => {
    setConnectionBadge(false, "Sin backend");
    toast("No se pudo conectar con el backend. Reintentando…", "error");
    socket.scheduleReconnect();
  });
});

function bindRegisterToggle() {
  const showRegister = el("showRegister");
  const showLogin = el("showLogin");
  const loginScreen = el("loginScreen");
  const registerScreen = el("registerScreen");
  
  if (showRegister) {
    showRegister.addEventListener("click", (e) => {
      e.preventDefault();
      loginScreen?.classList.add("hidden");
      registerScreen?.classList.remove("hidden");
    });
  }
  if (showLogin) {
    showLogin.addEventListener("click", (e) => {
      e.preventDefault();
      registerScreen?.classList.add("hidden");
      loginScreen?.classList.remove("hidden");
    });
  }
}
