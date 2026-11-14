/* Device Detail app — Información y acciones de un dispositivo individual */

import { state } from '../state.js';
import { socket, on } from '../ws.js';
import { toast } from '../ui.js';
import { showModal } from '../modal_dialog.js';

let _listeners = [];

export function render(container, deviceId) {
  // Clear previous listeners
  _listeners.forEach(({ event, fn }) => {
    import('../ws.js').then(mod => mod.off(event, fn));
  });
  _listeners = [];

  // Find device in state
  const dev = (state.allDevices || state.devices || []).find(d => d.id === deviceId);
  if (!dev) {
    container.innerHTML = `
      <div class="empty-state" style="padding:40px; text-align:center;">
        <p>Dispositivo no encontrado: ${deviceId}</p>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div class="section-title">
      <h2>${dev.name || deviceId}</h2>
      <span class="section-sub">Detalle del dispositivo</span>
    </div>
    <div class="card">
      <div class="status-list">
        <div class="status-row"><span class="status-label">Nombre</span><span class="status-value">${dev.name || '—'}</span></div>
        <div class="status-row"><span class="status-label">ID</span><span class="status-value mono">${dev.id}</span></div>
        <div class="status-row"><span class="status-label">Estado</span><span class="status-value"><span class="badge ${dev.online ? 'online' : 'offline'}"><span class="dot"></span>${dev.online ? 'Online' : 'Offline'}</span></span></div>
        <div class="status-row"><span class="status-label">Firmware</span><span class="status-value mono">${dev.firmware_version || dev.firmware || '—'}</span></div>
        <div class="status-row"><span class="status-label">Ubicación</span><span class="status-value">${dev.location || '—'}</span></div>
        <div class="status-row"><span class="status-label">IP</span><span class="status-value mono">${dev.ip || '—'}</span></div>
      </div>
      <div class="btn-row" style="margin-top:16px;">
        <button class="btn btn-primary device-settings" data-id="${dev.id}">⚙ Ajustes</button>
      </div>
      <div class="btn-row" style="margin-top:8px;">
        <button class="btn btn-ghost device-reboot" data-id="${dev.id}">Reiniciar</button>
        <button class="btn btn-ghost device-sleep" data-id="${dev.id}">Dormir</button>
        <button class="btn btn-magenta device-reset" data-id="${dev.id}">Reset fábrica</button>
      </div>
      <div class="btn-row" style="margin-top:8px; padding-top:12px; border-top:1px solid var(--border);">
        <button class="btn btn-ghost device-delete" data-id="${dev.id}" style="color:var(--neon-magenta);">Eliminar dispositivo</button>
      </div>
    </div>
  `;

  // Bind Ajustes button — opens device_settings_hub window
  container.querySelector('.device-settings').addEventListener('click', () => {
    const wm = window.__windowManager;
    if (wm) {
      wm.open('device_settings_hub', { singleInstance: false, _deviceId: dev.id });
    }
  });

  // Bind action buttons — each opens a blocking modal dialog
  container.querySelector('.device-reboot').addEventListener('click', async () => {
    const result = await showModal(
      'Reiniciar dispositivo',
      `¿Reiniciar ${dev.id}? El dispositivo se reiniciará y perderá la conexión temporalmente.`,
      { confirmText: 'Reiniciar', danger: false, icon: '↻' }
    );
    if (result?.confirmed) {
      socket.send({ event: 'reboot', device_id: dev.id });
      toast(`Reiniciando ${dev.id}...`, 'info');
    }
  });

  container.querySelector('.device-sleep').addEventListener('click', async () => {
    const result = await showModal(
      'Poner en deep sleep',
      `¿Enviar ${dev.id} a deep sleep por 60 minutos? El dispositivo no responderá hasta que despierte.`,
      { confirmText: 'Dormir', danger: false, icon: '⏾' }
    );
    if (result?.confirmed) {
      socket.send({ event: 'sleep', device_id: dev.id, minutes: 60 });
      toast(`Enviando ${dev.id} a deep sleep...`, 'info');
    }
  });

  container.querySelector('.device-reset').addEventListener('click', async () => {
    const result = await showModal(
      'Reset de fábrica',
      `¿Resetear ${dev.id} a fábrica? Se borrará toda la configuración incluyendo WiFi, vinculación y calibración. Esta acción no se puede deshacer.`,
      { confirmText: 'Resetear', danger: true, icon: '⚠' }
    );
    if (result?.confirmed) {
      socket.send({ event: 'factory_reset', device_id: dev.id });
      toast(`Reset de fábrica para ${dev.id}...`, 'info');
    }
  });

  container.querySelector('.device-delete').addEventListener('click', async () => {
    const result = await showModal(
      'Eliminar dispositivo',
      `¿Eliminar ${dev.id} del panel y de la base de datos? Esta acción no se puede deshacer y el dispositivo dejará de aparecer en el panel.`,
      { confirmText: 'Eliminar', danger: true, icon: '✕' }
    );
    if (result?.confirmed) {
      socket.send({ event: 'delete_device', device_id: dev.id });
      toast(`Eliminando ${dev.id}...`, 'info');
    }
  });

  // Listen for sync_all to update device info automatically
  const syncFn = (data) => {
    const devices = data.all_devices || data.devices || [];
    const updated = devices.find(d => d.id === deviceId);
    if (updated) {
      updateDetailDisplay(updated);
    }
  };
  on('sync_all', syncFn);
  _listeners.push({ event: 'sync_all', fn: syncFn });

  // Listen for device_status to update online/offline in real time
  const statusFn = (data) => {
    if (data.device_id !== deviceId) return;
    // Update in state
    const devices = state.allDevices || state.devices || [];
    const idx = devices.findIndex(d => d.id === deviceId);
    if (idx >= 0) {
      devices[idx].online = !!data.is_online;
      if (data.rssi !== undefined) devices[idx].rssi = data.rssi;
      if (data.ip) devices[idx].ip = data.ip;
      if (data.firmware) devices[idx].firmware_version = data.firmware;
    }
    // Update the displayed status badge
    const badgeEl = container.querySelector('.badge');
    if (badgeEl) {
      badgeEl.className = `badge ${data.is_online ? 'online' : 'offline'}`;
      badgeEl.innerHTML = `<span class="dot"></span>${data.is_online ? 'Online' : 'Offline'}`;
    }
    const ipEl = container.querySelector('.status-row:has(> .status-label:has(+:contains("IP")))');
    // Update IP if available
    if (data.ip) {
      const statusRows = container.querySelectorAll('.status-row .status-value');
      if (statusRows.length >= 6) statusRows[5].textContent = data.ip;
    }
  };
  on('device_status', statusFn);
  _listeners.push({ event: 'device_status', fn: statusFn });
}

function updateDetailDisplay(updated) {
  const container = document.querySelector('.window-content:has(.device-reboot[data-id="' + updated.id + '"])');
  if (!container) return;
  const statusRows = container.querySelectorAll('.status-row .status-value');
  if (statusRows.length >= 6) {
    statusRows[0].textContent = updated.name || '—';
    statusRows[2].innerHTML = `<span class="badge ${updated.online ? 'online' : 'offline'}"><span class="dot"></span>${updated.online ? 'Online' : 'Offline'}</span>`;
    statusRows[3].textContent = updated.firmware_version || updated.firmware || '—';
    statusRows[4].textContent = updated.location || '—';
    statusRows[5].textContent = updated.ip || '—';
  }
  const titleEl = container.querySelector('.section-title h2');
  if (titleEl) titleEl.textContent = updated.name || updated.id;
}
