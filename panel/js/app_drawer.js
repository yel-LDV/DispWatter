/* AppDrawer — Barra lateral de aplicaciones */

import { windowManager } from './window_manager.js';

const APPS = [
  { id: 'dashboard',   icon: '◉', label: 'Dashboard' },
  { id: 'devices',     icon: '⚙', label: 'Dispositivos' },
  { id: 'history',     icon: '📊', label: 'Historial' },
  { id: 'lcd',         icon: '🖥', label: 'LCD' },
  { id: 'permissions', icon: '🔑', label: 'Permisos' },
  { id: 'audit',       icon: '⌁', label: 'Auditoría' },
  { id: 'system',      icon: '▤', label: 'Sistema' },
  { id: 'settings',    icon: '⚙', label: 'Ajustes' },
  { id: 'firmware_upload', icon: '⬆', label: 'Firmware' },
];

class AppDrawer {
  constructor() {
    this.visible = false;
    this.el = null;
    this.overlay = null;
  }

  init() {
    this.el = document.getElementById('appDrawer');
    this.overlay = document.getElementById('appDrawerOverlay');
    if (!this.el) return;

    this.el.innerHTML = `
      <button class="app-drawer-close" id="appDrawerClose" title="Cerrar">✕</button>
      <div class="app-drawer-header">
        <div class="logo-mark" aria-hidden="true">
          <img src="assets/logo.svg" alt="" width="22" height="22">
        </div>
        <div>
          <h1>DispWatter</h1>
          <div class="brand-sub">Aplicaciones</div>
        </div>
      </div>
      <div class="app-drawer-list" id="appDrawerList"></div>
    `;

    this._renderList();
    this._bindEvents();
  }

  _renderList() {
    const list = document.getElementById('appDrawerList');
    if (!list) return;

    list.innerHTML = '';
    for (const app of APPS) {
      const item = document.createElement('button');
      item.className = 'app-drawer-item';
      item.dataset.appId = app.id;
      item.innerHTML = `
        <span class="app-drawer-item-icon">${app.icon}</span>
        <span>${app.label}</span>
      `;
      item.addEventListener('click', () => this.openApp(app.id));
      list.appendChild(item);
    }
  }

  _bindEvents() {
    const closeBtn = document.getElementById('appDrawerClose');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => this.toggle());
    }
    if (this.overlay) {
      this.overlay.addEventListener('click', () => this.toggle());
    }
  }

  toggle() {
    this.visible = !this.visible;
    if (this.el) this.el.classList.toggle('open', this.visible);
    if (this.overlay) this.overlay.classList.toggle('visible', this.visible);
  }

  openApp(appId) {
    windowManager.open(appId);
    // Close drawer after opening
    if (this.visible) this.toggle();
  }
}

export const appDrawer = new AppDrawer();
