/* Taskbar — Barra de tareas inferior */

import { state } from './state.js';
import { el } from './ui.js';
import { windowManager } from './window_manager.js';

const APP_REGISTRY = {
  dashboard:   { icon: '◉', title: 'Dashboard' },
  devices:     { icon: '⚙', title: 'Dispositivos' },
  history:     { icon: '📊', title: 'Historial' },
  lcd:         { icon: '🖥', title: 'LCD' },
  permissions: { icon: '🔑', title: 'Permisos' },
  audit:       { icon: '⌁', title: 'Auditoría' },
  system:      { icon: '▤', title: 'Sistema' },
  settings:    { icon: '⚙', title: 'Ajustes' },
};

class Taskbar {
  static HEIGHT = 48;

  constructor() {
    this.el = null;
    this.clockInterval = null;
  }

  init() {
    this.el = el('taskbar');
    if (!this.el) return;

    this.el.innerHTML = `
      <div class="taskbar-apps" id="taskbarApps"></div>
      <div class="taskbar-right">
        <div class="taskbar-connection" id="taskbarConn">
          <span class="dot"></span>
          <span id="taskbarConnText">Desconectado</span>
        </div>
        <div class="taskbar-clock" id="taskbarClock">--:--</div>
        <div class="taskbar-user">
          <span id="taskbarUserName">—</span>
          <span id="taskbarUserRole" class="taskbar-user-role">—</span>
        </div>
      </div>
    `;

    this.startClock();
    this.updateUser();
    this.updateConnection();
    this.update();
  }

  startClock() {
    this._updateClock();
    this.clockInterval = setInterval(() => this._updateClock(), 1000);
  }

  _updateClock() {
    const clock = el('taskbarClock');
    if (!clock) return;
    const now = new Date();
    clock.textContent = now.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
  }

  updateUser() {
    const nameEl = el('taskbarUserName');
    const roleEl = el('taskbarUserRole');
    if (nameEl && state.user) nameEl.textContent = state.user.username;
    if (roleEl && state.user) roleEl.textContent = state.user.role || '';
  }

  updateConnection() {
    const conn = el('taskbarConn');
    const text = el('taskbarConnText');
    if (!conn || !text) return;

    if (state.connected) {
      conn.className = 'taskbar-connection connected';
      text.textContent = 'Conectado';
    } else {
      conn.className = 'taskbar-connection disconnected';
      text.textContent = 'Desconectado';
    }
  }

  update() {
    const appsContainer = el('taskbarApps');
    if (!appsContainer) return;

    appsContainer.innerHTML = '';

    for (const [id, w] of windowManager.windows) {
      const btn = document.createElement('button');
      btn.className = 'taskbar-app-btn';
      if (w.minimized) btn.classList.add('active');

      const info = APP_REGISTRY[w.appId];
      btn.innerHTML = `
        <span class="taskbar-app-btn-icon">${info ? info.icon : '●'}</span>
        <span>${w.title}</span>
      `;

      btn.addEventListener('click', () => {
        if (w.minimized) {
          windowManager.restore(id);
        } else {
          windowManager.minimize(id);
        }
      });

      appsContainer.appendChild(btn);
    }
  }
}

export const taskbar = new Taskbar();
