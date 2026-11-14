/* Device Settings Hub — Ventana principal de ajustes con categorías */

import { state } from '../state.js';
import { toast } from '../ui.js';

let _deviceId = null;

export function render(container, deviceId) {
  _deviceId = deviceId;

  const dev = (state.allDevices || state.devices || []).find(d => d.id === deviceId);
  const devName = dev ? (dev.name || deviceId) : deviceId;

  container.innerHTML = `
    <div class="section-title">
      <h2>⚙ Ajustes</h2>
      <span class="section-sub">${devName}</span>
    </div>

    <div class="settings-hub-grid">
      <div class="settings-hub-card" data-category="parameters">
        <div class="settings-hub-icon">💧</div>
        <div class="settings-hub-label">Parámetros</div>
        <div class="settings-hub-desc">Tanque, bomba, niveles y bloqueo de menú</div>
      </div>

      <div class="settings-hub-card" data-category="permissions">
        <div class="settings-hub-icon">🔑</div>
        <div class="settings-hub-label">Permisos</div>
        <div class="settings-hub-desc">Gestionar quién puede acceder a este dispositivo</div>
      </div>
    </div>
  `;

  // Bind category cards
  container.querySelectorAll('.settings-hub-card').forEach(card => {
    card.addEventListener('click', () => {
      const category = card.dataset.category;
      const wm = window.__windowManager;
      if (!wm) return;

      if (category === 'parameters') {
        wm.open('device_config', { singleInstance: false, _deviceId: deviceId });
      } else if (category === 'permissions') {
        wm.open('device_permissions', { singleInstance: false, _deviceId: deviceId });
      }
    });
  });
}
