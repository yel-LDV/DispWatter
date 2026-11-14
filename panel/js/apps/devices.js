/* Devices app — Lista unificada (detalle se abre en ventana flotante) */

import { state } from '../state.js';
import { socket, on } from '../ws.js';
import { toast, confirmAction } from '../ui.js';

let _syncListener = null;

export function render(container) {
  container.innerHTML = `
    <div class="section-title">
      <h2>Dispositivos</h2>
      <span class="section-sub">Todos los dispositivos registrados. Haz click en el nombre para ver detalles.</span>
    </div>
    <div class="card">
      <div class="card-head">
        <h2>Lista de dispositivos</h2>
        <div class="btn-row">
          <button class="btn btn-ghost btn-sm devices-add-toggle" type="button">+ Agregar</button>
          <button class="btn btn-ghost btn-sm devices-refresh" type="button">Actualizar</button>
        </div>
      </div>
      <div class="devices-add-form" style="display:none; padding:12px; border-bottom:1px solid var(--border);">
        <form class="devices-add-inline" style="display:flex; gap:8px; align-items:center;">
          <input type="text" class="devices-add-input" placeholder="ID del dispositivo (ej: WATTER-004)" style="flex:1; padding:6px 10px; border:1px solid var(--border); border-radius:6px; background:var(--bg); color:var(--text);" required>
          <button type="submit" class="btn btn-sm" style="white-space:nowrap;">Agregar</button>
          <button type="button" class="btn btn-ghost btn-sm devices-add-cancel" style="white-space:nowrap;">Cancelar</button>
        </form>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Nombre</th><th>ID</th><th>Estado</th><th>Firmware</th></tr>
          </thead>
          <tbody class="devices-body">
            <tr><td colspan="4" class="empty-state">Cargando...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  `;

  loadDevices();

  container.querySelector('.devices-refresh').addEventListener('click', loadDevices);

  // Add device form toggle
  const addToggle = container.querySelector('.devices-add-toggle');
  const addForm = container.querySelector('.devices-add-form');
  const addCancel = container.querySelector('.devices-add-cancel');
  const addInline = container.querySelector('.devices-add-inline');
  const addInput = container.querySelector('.devices-add-input');

  addToggle.addEventListener('click', () => {
    addForm.style.display = 'block';
    addInput.focus();
  });
  addCancel.addEventListener('click', () => {
    addForm.style.display = 'none';
    addInput.value = '';
  });
  addInline.addEventListener('submit', async (e) => {
    e.preventDefault();
    const deviceId = addInput.value.trim();
    if (!deviceId) return;
    addInput.value = '';
    addForm.style.display = 'none';
    socket.send({ event: 'add_device', device_id: deviceId });
    toast(`Agregando dispositivo ${deviceId}...`, 'info');
  });

  // Listen for sync_all response to refresh the list automatically
  _syncListener = on('sync_all', (data) => {
    const devices = data.all_devices || data.devices || [];
    state.allDevices = devices;
    renderDeviceList();
  });

  // Listen for device_status to update online/offline in real time
  const statusFn = (data) => {
    const devices = state.allDevices || state.devices || [];
    const idx = devices.findIndex(d => d.id === data.device_id);
    if (idx >= 0) {
      devices[idx].online = !!data.is_online;
      if (data.rssi !== undefined) devices[idx].rssi = data.rssi;
      if (data.ip) devices[idx].ip = data.ip;
      if (data.firmware) devices[idx].firmware_version = data.firmware;
    }
    renderDeviceList();
  };
  on('device_status', statusFn);
}

function requestSync() {
  socket.send({ event: 'sync' });
}

function loadDevices() {
  requestSync();
  renderDeviceList();
}

function renderDeviceList() {
  const tbody = document.querySelector('.devices-body');
  if (!tbody) return;

  const devices = state.allDevices || state.devices || [];
  if (!devices.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty-state">Sin dispositivos.</td></tr>';
    return;
  }

  tbody.innerHTML = devices.map(d => `
    <tr>
      <td><a href="#" class="device-name-link" data-id="${d.id}">${d.name || '—'}</a></td>
      <td class="mono">${d.id || '—'}</td>
      <td><span class="badge ${d.online ? 'online' : 'offline'}"><span class="dot"></span>${d.online ? 'Online' : 'Offline'}</span></td>
      <td class="mono">${d.firmware_version || d.firmware || '—'}</td>
    </tr>
  `).join('');

  // Click on device name opens detail window
  tbody.querySelectorAll('.device-name-link').forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      openDeviceDetail(link.dataset.id);
    });
  });
}

function openDeviceDetail(deviceId) {
  // Import windowManager to open a new floating window
  import('../window_manager.js').then(wm => {
    wm.windowManager.open('device_detail', {
      singleInstance: false,
      title: deviceId,
      width: 500,
      height: 450,
      x: Math.max(50, (window.innerWidth - 500) / 2 + Math.random() * 40),
      y: Math.max(50, (window.innerHeight - 450) / 2 + Math.random() * 40),
      _deviceId: deviceId
    });
  });
}
