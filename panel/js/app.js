import { initAuth, tryResume } from "./auth.js";
import { initTheme } from "./theme.js";
import { initRegister } from "./register.js";
import { state } from "./state.js";
import { socket, on } from "./ws.js";
import { el, toast } from "./ui.js";
import { windowManager } from "./window_manager.js";
import { taskbar } from "./taskbar.js";
import { appDrawer } from "./app_drawer.js";
import { createBellButton, initListeners } from "./notification_center.js";

let everConnected = false;
let isAuthenticated = false;

function updateConnectionStatus(connected) {
  state.connected = connected;
  if (taskbar.updateConnection) taskbar.updateConnection();
}

function authenticated() {
  isAuthenticated = true;
  updateConnectionStatus(true);
  if (!everConnected) {
    everConnected = true;
    toast("Sesión autenticada", "success");
  }
  // Open dashboard by default
  windowManager.open('dashboard');
}

function bindSocket() {
  on("open", async () => {
    updateConnectionStatus(true);
    // Solo intentar resume si aún no estamos autenticados.
    // Después del login, el backend ya no espera eventos resume.
    if (!isAuthenticated) {
      const resumed = await tryResume();
      if (resumed) isAuthenticated = true;
    }
  });
  on("close", () => updateConnectionStatus(false));
  on("error", (message) => {
    if (!message.request_id) toast(message.message || message.code || "Error del backend", "error");
  });
  // Global sync_all listener: store device list in state for all apps
  on("sync_all", (data) => {
    const devices = data.all_devices || data.devices || [];
    if (devices.length > 0) {
      state.allDevices = devices;
      state.devices = devices;
    }
  });
}

function bindDrawerToggle() {
  const toggle = el('drawerToggle');
  if (toggle) {
    toggle.addEventListener('click', () => appDrawer.toggle());
  }
}

function bindLogout() {
  // Logout is handled by auth.js, which hides login screen
  // After logout, hide desktop and show login
}

function showDesktop() {
  const desktop = el('desktop');
  const loginScreen = el('loginScreen');
  const registerScreen = el('registerScreen');

  if (desktop) desktop.classList.remove('hidden');
  if (loginScreen) loginScreen.classList.add('hidden');
  if (registerScreen) registerScreen.classList.add('hidden');

  // Initialize desktop components
  appDrawer.init();
  taskbar.init();
  windowManager._taskbar = taskbar;

  // Expose windowManager globally so lazy-loaded app modules can access it
  window.__windowManager = windowManager;

  // Create fixed notification bell button (absolute, top-right)
  createBellButton();
  initListeners();
}

function hideDesktop() {
  const desktop = el('desktop');
  if (desktop) desktop.classList.add('hidden');
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initRegister();
  initAuth(() => {
    authenticated();
    showDesktop();
  });

  bindSocket();
  bindDrawerToggle();
  bindLogout();
  bindRegisterToggle();

  socket.connect().catch(() => {
    updateConnectionStatus(false);
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
