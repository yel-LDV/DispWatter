/* Device Config sub-window — Parámetros del dispositivo con guardado/descarte obligatorio */

import { state } from '../state.js';
import { socket, on, off } from '../ws.js';
import { toast } from '../ui.js';
import { showModal } from '../modal_dialog.js';

let _listeners = [];
let _deviceId = null;
let _originalValues = {};
let _windowId = null;

export function render(container, deviceId) {
  // Clear previous listeners
  _listeners.forEach(({ event, fn }) => {
    import('../ws.js').then(mod => mod.off(event, fn));
  });
  _listeners = [];

  _deviceId = deviceId;

  // Store window ID for close handler
  const winEl = container.closest('.window');
  if (winEl) _windowId = winEl.id;

  // Show loading state while fetching fresh config from backend
  container.innerHTML = `
    <div class="section-title">
      <h2>💧 Parámetros</h2>
      <span class="section-sub">${deviceId}</span>
    </div>
    <div class="empty-state" style="padding:40px; text-align:center;">
      <p>Cargando configuración...</p>
    </div>
  `;

  // Fetch fresh config from backend instead of using cached state
  fetchDeviceConfig(deviceId, container);
}

function fetchDeviceConfig(deviceId, container) {
  // Use socket.request-style: send get_device_config and wait for response
  const requestId = `cfg_${Date.now()}`;
  
  // Listen for the response
  const responseFn = (data) => {
    if (data.request_id !== requestId) return;
    off('device_config_result', responseFn);
    
    if (!data.ok) {
      container.innerHTML = `
        <div class="section-title">
          <h2>💧 Parámetros</h2>
          <span class="section-sub">${deviceId}</span>
        </div>
        <div class="empty-state" style="padding:40px; text-align:center;">
          <p>Error al cargar configuración</p>
        </div>
      `;
      return;
    }

    renderConfigForm(container, deviceId, data.name, data.location, data.config);
  };
  on('device_config_result', responseFn);

  // Send request
  socket.send({ event: 'get_device_config', device_id: deviceId, request_id: requestId });

  // Timeout fallback: if no response in 5s, use cached state
  setTimeout(() => {
    const dev = (state.allDevices || state.devices || []).find(d => d.id === deviceId);
    if (!dev) return;
    // Check if we already got a response
    const existingForm = container.querySelector('#cfgName');
    if (existingForm) return; // Already rendered
    off('device_config_result', responseFn);
    const cfg = dev.config || {};
    renderConfigForm(container, deviceId, dev.name || '', dev.location || '', cfg);
  }, 5000);
}

function renderConfigForm(container, deviceId, name, location, cfg) {
  // Store original values for comparison
  _originalValues = {
    name: name || '',
    location: location || '',
    capacity: cfg.capacity || 50,
    bottom: cfg.bottom_dist_mm || 900,
    mirror: cfg.mirror_dist_mm || 100,
    minLevel: cfg.min_level || 25,
    maxLevel: cfg.max_level || 90,
    minRelayOff: cfg.min_relay_off_min || 3,
    overflow: cfg.overflow_protection !== false,
    autoRefill: cfg.auto_refill,
    menuLock: cfg.menu_lock,
  };

  container.innerHTML = `
    <div class="section-title">
      <h2>💧 Parámetros</h2>
      <span class="section-sub">${name || deviceId}</span>
    </div>

    <!-- General section -->
    <div class="card" style="margin-bottom:16px;">
      <h3 class="card-title">General</h3>
      <div class="form-group">
        <label class="form-label">Nombre del dispositivo</label>
        <input type="text" class="form-input" id="cfgName" value="${name || ''}" maxlength="128" placeholder="Bebedero Principal">
      </div>
      <div class="form-group">
        <label class="form-label">Ubicación</label>
        <input type="text" class="form-input" id="cfgLocation" value="${location || ''}" maxlength="128" placeholder="Granero">
      </div>
    </div>

    <!-- Tank section -->
    <div class="card" style="margin-bottom:16px;">
      <h3 class="card-title">Tanque</h3>
      <div class="form-group">
        <label class="form-label">Capacidad (litros)</label>
        <input type="number" class="form-input" id="cfgCapacity" value="${cfg.capacity || 50}" min="0.1" max="100000" step="0.1">
      </div>
      <div class="form-group">
        <label class="form-label">Distancia fondo (mm)</label>
        <input type="number" class="form-input" id="cfgBottom" value="${cfg.bottom_dist_mm || 900}" min="10" max="12000" step="1">
      </div>
      <div class="form-group">
        <label class="form-label">Distancia espejo (mm)</label>
        <input type="number" class="form-input" id="cfgMirror" value="${cfg.mirror_dist_mm || 100}" min="0" step="1">
      </div>
      <div class="form-group">
        <label class="form-label">Nivel mínimo (%)</label>
        <input type="number" class="form-input" id="cfgMinLevel" value="${cfg.min_level || 25}" min="0" max="100" step="1">
      </div>
      <div class="form-group">
        <label class="form-label">Nivel máximo (%)</label>
        <input type="number" class="form-input" id="cfgMaxLevel" value="${cfg.max_level || 90}" min="0" max="100" step="1">
      </div>
    </div>

    <!-- Pump section -->
    <div class="card" style="margin-bottom:16px;">
      <h3 class="card-title">Bomba</h3>
      <div class="form-group">
        <label class="form-label">Tiempo mín. apagado (min)</label>
        <input type="number" class="form-input" id="cfgMinRelayOff" value="${cfg.min_relay_off_min || 3}" min="0" max="60" step="0.5">
      </div>
      <div class="form-group form-group-switch">
        <label class="form-label">Protección desborde</label>
        <label class="switch">
          <input type="checkbox" id="cfgOverflow" ${cfg.overflow_protection !== false ? 'checked' : ''}>
          <span class="switch-slider"></span>
        </label>
      </div>
      <div class="form-group form-group-switch">
        <label class="form-label">Llenado automático</label>
        <label class="switch">
          <input type="checkbox" id="cfgAutoRefill" ${cfg.auto_refill ? 'checked' : ''}>
          <span class="switch-slider"></span>
        </label>
      </div>
    </div>

    <!-- Menu lock section -->
    <div class="card" style="margin-bottom:16px;">
      <h3 class="card-title">Menú de ajustes (ESP32)</h3>
      <div class="form-group form-group-switch">
        <label class="form-label">Bloquear menú de ajustes</label>
        <label class="switch">
          <input type="checkbox" id="cfgMenuLock" ${cfg.menu_lock ? 'checked' : ''}>
          <span class="switch-slider"></span>
        </label>
        <small class="form-hint">Si está activado, el dispositivo no abrirá el menú de ajustes al presionar Power+Back en el ESP32.</small>
      </div>
    </div>

    <!-- Actions -->
    <div class="btn-row">
      <button class="btn btn-primary" id="cfgSave">Guardar cambios</button>
      <button class="btn btn-ghost" id="cfgDiscard">Descartar</button>
    </div>
  `;

  // Bind save button
  container.querySelector('#cfgSave').addEventListener('click', () => saveAndClose());

  // Bind discard button
  container.querySelector('#cfgDiscard').addEventListener('click', () => discardAndClose());

  // Listen for sync_all to update config values automatically
  const syncFn = (data) => {
    const devices = data.all_devices || data.devices || [];
    const updated = devices.find(d => d.id === deviceId);
    if (updated) {
      updateConfigDisplay(updated);
      // Update original values after sync
      const cfg = updated.config || {};
      _originalValues = {
        name: updated.name || '',
        location: updated.location || '',
        capacity: cfg.capacity || 50,
        bottom: cfg.bottom_dist_mm || 900,
        mirror: cfg.mirror_dist_mm || 100,
        minLevel: cfg.min_level || 25,
        maxLevel: cfg.max_level || 90,
        minRelayOff: cfg.min_relay_off_min || 3,
        overflow: cfg.overflow_protection !== false,
        autoRefill: cfg.auto_refill,
        menuLock: cfg.menu_lock,
      };
    }
  };
  on('sync_all', syncFn);
  _listeners.push({ event: 'sync_all', fn: syncFn });
}

function getCurrentValues() {
  return {
    name: document.getElementById('cfgName')?.value?.trim() || '',
    location: document.getElementById('cfgLocation')?.value?.trim() || '',
    capacity: parseFloat(document.getElementById('cfgCapacity')?.value) || 50,
    bottom: parseFloat(document.getElementById('cfgBottom')?.value) || 900,
    mirror: parseFloat(document.getElementById('cfgMirror')?.value) || 100,
    minLevel: parseFloat(document.getElementById('cfgMinLevel')?.value) || 25,
    maxLevel: parseFloat(document.getElementById('cfgMaxLevel')?.value) || 90,
    minRelayOff: parseFloat(document.getElementById('cfgMinRelayOff')?.value) || 3,
    overflow: document.getElementById('cfgOverflow')?.checked ?? true,
    autoRefill: document.getElementById('cfgAutoRefill')?.checked ?? true,
    menuLock: document.getElementById('cfgMenuLock')?.checked ?? false,
  };
}

function hasChanges() {
  const current = getCurrentValues();
  return (
    current.name !== _originalValues.name ||
    current.location !== _originalValues.location ||
    current.capacity !== _originalValues.capacity ||
    current.bottom !== _originalValues.bottom ||
    current.mirror !== _originalValues.mirror ||
    current.minLevel !== _originalValues.minLevel ||
    current.maxLevel !== _originalValues.maxLevel ||
    current.minRelayOff !== _originalValues.minRelayOff ||
    current.overflow !== _originalValues.overflow ||
    current.autoRefill !== _originalValues.autoRefill ||
    current.menuLock !== _originalValues.menuLock
  );
}

function validateValues(current) {
  if (current.capacity < 0.1 || current.capacity > 100000) {
    toast('Capacidad inválida (0.1 - 100000)', 'error');
    return false;
  }
  if (current.bottom < 10 || current.bottom > 12000) {
    toast('Distancia de fondo inválida (10 - 12000)', 'error');
    return false;
  }
  if (current.mirror < 0 || current.mirror >= current.bottom) {
    toast('Distancia espejo inválida (0 - fondo)', 'error');
    return false;
  }
  if (current.bottom - current.mirror < 20) {
    toast('Altura útil mínima: 20 mm', 'error');
    return false;
  }
  if (current.minLevel < 0 || current.minLevel > 100 || current.maxLevel < 0 || current.maxLevel > 100 || current.minLevel >= current.maxLevel) {
    toast('Niveles inválidos (mín < máx)', 'error');
    return false;
  }
  if (current.maxLevel - current.minLevel < 5) {
    toast('Diferencia mín/máx: al menos 5 puntos', 'error');
    return false;
  }
  return true;
}

function sendConfig(current) {
  socket.send({
    event: 'update_device_config',
    device_id: _deviceId,
    name: current.name,
    location: current.location,
    config: {
      capacity: current.capacity,
      bottom_dist_mm: current.bottom,
      mirror_dist_mm: current.mirror,
      min_level: current.minLevel,
      max_level: current.maxLevel,
      auto_refill: current.autoRefill,
      min_relay_off_min: current.minRelayOff,
      overflow_protection: current.overflow,
      menu_lock: current.menuLock,
    },
  });
}

function saveAndClose() {
  const current = getCurrentValues();
  if (!validateValues(current)) return;
  sendConfig(current);
  toast('Guardando configuración...', 'info');
  // Update original values so close doesn't trigger dialog
  _originalValues = { ...current };
  // Close the window
  if (_windowId) {
    const wm = window.__windowManager;
    if (wm) {
      const w = wm.get(_windowId);
      if (w) w._forceClose = true;
      wm.close(_windowId);
    }
  }
}

function discardAndClose() {
  if (_windowId) {
    const wm = window.__windowManager;
    if (wm) {
      const w = wm.get(_windowId);
      if (w) w._forceClose = true;
      wm.close(_windowId);
    }
  }
  toast('Cambios descartados', 'info');
}

export function checkBeforeClose(windowId) {
  // Returns a promise that resolves to true if close is allowed
  return new Promise((resolve) => {
    if (!hasChanges()) {
      // No changes, allow close immediately
      const wm = window.__windowManager;
      if (wm) {
        const w = wm.get(windowId);
        if (w) w._forceClose = true;
      }
      resolve(true);
      return;
    }
    showModal(
      'Cambios sin guardar',
      '¿Qué deseas hacer con los cambios en los parámetros?',
      {
        confirmText: 'Guardar cambios',
        cancelText: 'Descartar',
        icon: '💧'
      }
    ).then(result => {
      if (result?.confirmed) {
        const current = getCurrentValues();
        if (validateValues(current)) {
          sendConfig(current);
          toast('Configuración guardada', 'success');
        } else {
          // Validation failed, don't close
          resolve(false);
          return;
        }
      } else {
        toast('Cambios descartados', 'info');
      }
      // Allow close
      const wm = window.__windowManager;
      if (wm) {
        const w = wm.get(windowId);
        if (w) w._forceClose = true;
      }
      resolve(true);
    });
  });
}

function updateConfigDisplay(updated) {
  const container = document.querySelector('.window-content:has(#cfgSave)');
  if (!container) return;

  const cfg = updated.config || {};

  const nameEl = container.querySelector('#cfgName');
  if (nameEl) nameEl.value = updated.name || '';

  const locEl = container.querySelector('#cfgLocation');
  if (locEl) locEl.value = updated.location || '';

  const capEl = container.querySelector('#cfgCapacity');
  if (capEl) capEl.value = cfg.capacity || 50;

  const bottomEl = container.querySelector('#cfgBottom');
  if (bottomEl) bottomEl.value = cfg.bottom_dist_mm || 900;

  const mirrorEl = container.querySelector('#cfgMirror');
  if (mirrorEl) mirrorEl.value = cfg.mirror_dist_mm || 100;

  const minEl = container.querySelector('#cfgMinLevel');
  if (minEl) minEl.value = cfg.min_level || 25;

  const maxEl = container.querySelector('#cfgMaxLevel');
  if (maxEl) maxEl.value = cfg.max_level || 90;

  const minRelayEl = container.querySelector('#cfgMinRelayOff');
  if (minRelayEl) minRelayEl.value = cfg.min_relay_off_min || 3;

  const overflowEl = container.querySelector('#cfgOverflow');
  if (overflowEl) overflowEl.checked = cfg.overflow_protection !== false;

  const autoEl = container.querySelector('#cfgAutoRefill');
  if (autoEl) autoEl.checked = cfg.auto_refill;

  const menuLockEl = container.querySelector('#cfgMenuLock');
  if (menuLockEl) menuLockEl.checked = cfg.menu_lock;
}
