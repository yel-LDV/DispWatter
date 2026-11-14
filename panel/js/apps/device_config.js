/* Device Config sub-window — Parámetros del dispositivo con guardado/descarte obligatorio */

import { state } from '../state.js';
import { socket, on, off } from '../ws.js';
import { toast } from '../ui.js';
import { showModal } from '../modal_dialog.js';
import { showConfigProgress } from '../config_progress.js';

let _listeners = [];
let _deviceId = null;
let _originalValues = {};
let _windowId = null;

export function render(container, deviceId) {
  try {
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
  } catch (err) {
    console.error('[device_config] render() error:', err);
    container.innerHTML = `
      <div class="section-title">
        <h2>💧 Parámetros</h2>
        <span class="section-sub">${deviceId}</span>
      </div>
      <div class="empty-state" style="padding:40px; text-align:center;">
        <p style="color:#e53e3e;">Error: ${err?.message || 'Desconocido'}</p>
      </div>
    `;
  }
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

  // Timeout fallback: if no response in 10s, use cached state from sync_all
  // sync_all sends config fields as flat properties (camelCase), not nested under 'config'
  setTimeout(() => {
    const dev = (state.allDevices || state.devices || []).find(d => d.id === deviceId);
    if (!dev) return;
    // Check if we already got a response
    const existingForm = container.querySelector('#cfgName');
    if (existingForm) return; // Already rendered
    off('device_config_result', responseFn);
    // Map sync_all flat fields to the snake_case format expected by renderConfigForm
    const cfg = {
      capacity: dev.capacity ?? 50,
      bottom_dist_mm: dev.bottomDist ?? 900,
      mirror_dist_mm: dev.mirrorDist ?? 100,
      min_level: dev.minLevel ?? 25,
      max_level: dev.maxLevel ?? 90,
      auto_refill: dev.autoRefill ?? true,
      min_relay_off_min: dev.minRelayOffMin ?? 3,
      overflow_protection: dev.overflowProtection !== false,
      menu_lock: dev.menuLock ?? false,
      wifi_lock: dev.wifiLock ?? false,
      device_lock: dev.deviceLock ?? false,
      pump_lock: dev.pumpLock ?? false,
      sensor_lock: dev.sensorLock ?? false,
      firmware_lock: dev.firmwareLock ?? false,
      security_lock: dev.securityLock ?? false,
    };
    renderConfigForm(container, deviceId, dev.name || '', dev.location || '', cfg);
  }, 10000);
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
    wifiLock: cfg.wifi_lock || false,
    deviceLock: cfg.device_lock || false,
    pumpLock: cfg.pump_lock || false,
    sensorLock: cfg.sensor_lock || false,
    firmwareLock: cfg.firmware_lock || false,
    securityLock: cfg.security_lock || false,
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

    <!-- Security locks section -->
    <div class="card" style="margin-bottom:16px;">
      <h3 class="card-title">Bloqueos de seguridad</h3>
      <div class="form-group form-group-switch">
        <label class="form-label">Bloquear configuración WiFi</label>
        <label class="switch">
          <input type="checkbox" id="cfgWifiLock" ${cfg.wifi_lock ? 'checked' : ''}>
          <span class="switch-slider"></span>
        </label>
      </div>
      <div class="form-group form-group-switch">
        <label class="form-label">Bloquear configuración dispositivo</label>
        <label class="switch">
          <input type="checkbox" id="cfgDeviceLock" ${cfg.device_lock ? 'checked' : ''}>
          <span class="switch-slider"></span>
        </label>
      </div>
      <div class="form-group form-group-switch">
        <label class="form-label">Bloquear bomba</label>
        <label class="switch">
          <input type="checkbox" id="cfgPumpLock" ${cfg.pump_lock ? 'checked' : ''}>
          <span class="switch-slider"></span>
        </label>
      </div>
      <div class="form-group form-group-switch">
        <label class="form-label">Bloquear sensor</label>
        <label class="switch">
          <input type="checkbox" id="cfgSensorLock" ${cfg.sensor_lock ? 'checked' : ''}>
          <span class="switch-slider"></span>
        </label>
      </div>
      <div class="form-group form-group-switch">
        <label class="form-label">Bloquear firmware</label>
        <label class="switch">
          <input type="checkbox" id="cfgFirmwareLock" ${cfg.firmware_lock ? 'checked' : ''}>
          <span class="switch-slider"></span>
        </label>
      </div>
      <div class="form-group form-group-switch">
        <label class="form-label">Bloquear seguridad</label>
        <label class="switch">
          <input type="checkbox" id="cfgSecurityLock" ${cfg.security_lock ? 'checked' : ''}>
          <span class="switch-slider"></span>
        </label>
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
  // sync_all sends config as flat camelCase properties, not nested under 'config'
  const syncFn = (data) => {
    const devices = data.all_devices || data.devices || [];
    const updated = devices.find(d => d.id === deviceId);
    if (updated) {
      updateConfigDisplay(updated);
      // Update original values after sync - map from sync_all flat fields
      _originalValues = {
        name: updated.name || '',
        location: updated.location || '',
        capacity: updated.capacity ?? 50,
        bottom: updated.bottomDist ?? 900,
        mirror: updated.mirrorDist ?? 100,
        minLevel: updated.minLevel ?? 25,
        maxLevel: updated.maxLevel ?? 90,
        minRelayOff: updated.minRelayOffMin ?? 3,
        overflow: updated.overflowProtection !== false,
        autoRefill: updated.autoRefill ?? true,
        menuLock: updated.menuLock ?? false,
        wifiLock: updated.wifiLock ?? false,
        deviceLock: updated.deviceLock ?? false,
        pumpLock: updated.pumpLock ?? false,
        sensorLock: updated.sensorLock ?? false,
        firmwareLock: updated.firmwareLock ?? false,
        securityLock: updated.securityLock ?? false,
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
    wifiLock: document.getElementById('cfgWifiLock')?.checked ?? false,
    deviceLock: document.getElementById('cfgDeviceLock')?.checked ?? false,
    pumpLock: document.getElementById('cfgPumpLock')?.checked ?? false,
    sensorLock: document.getElementById('cfgSensorLock')?.checked ?? false,
    firmwareLock: document.getElementById('cfgFirmwareLock')?.checked ?? false,
    securityLock: document.getElementById('cfgSecurityLock')?.checked ?? false,
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
    current.menuLock !== _originalValues.menuLock ||
    current.wifiLock !== _originalValues.wifiLock ||
    current.deviceLock !== _originalValues.deviceLock ||
    current.pumpLock !== _originalValues.pumpLock ||
    current.sensorLock !== _originalValues.sensorLock ||
    current.firmwareLock !== _originalValues.firmwareLock ||
    current.securityLock !== _originalValues.securityLock
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
      wifi_lock: current.wifiLock,
      device_lock: current.deviceLock,
      pump_lock: current.pumpLock,
      sensor_lock: current.sensorLock,
      firmware_lock: current.firmwareLock,
      security_lock: current.securityLock,
    },
  });
}

async function saveAndClose() {
  const current = getCurrentValues();
  if (!validateValues(current)) return;
  
  // Show progress window — blocks until result is shown and user accepts
  sendConfig(current);
  const result = await showConfigProgress(_deviceId);
  
  // Update original values so close doesn't trigger dialog
  _originalValues = { ...current };
  
  // Close the window after user accepts the result
  if (_windowId) {
    const wm = window.__windowManager;
    if (wm) {
      const w = wm.get(_windowId);
      if (w) w._forceClose = true;
      wm.close(_windowId);
    }
  }
  
  // Show toast based on result
  if (result.ok) {
    toast('Configuración aplicada exitosamente', 'success');
  } else {
    const errorMsg = result.error || 'desconocido';
    if (errorMsg === 'device_offline') {
      toast('Dispositivo offline — config guardada en servidor', 'warning');
    } else if (errorMsg === 'timeout') {
      toast('Timeout — config guardada en servidor', 'warning');
    } else {
      toast('Error al enviar configuración', 'error');
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
    ).then(async result => {
      if (result?.confirmed) {
        const current = getCurrentValues();
        if (validateValues(current)) {
          // Show progress window for save from close dialog
          sendConfig(current);
          const saveResult = await showConfigProgress(_deviceId);
          
          if (saveResult.ok) {
            toast('Configuración aplicada exitosamente', 'success');
          } else {
            const errorMsg = saveResult.error || 'desconocido';
            if (errorMsg === 'device_offline') {
              toast('Dispositivo offline — config guardada en servidor', 'warning');
            } else if (errorMsg === 'timeout') {
              toast('Timeout — config guardada en servidor', 'warning');
            } else {
              toast('Error al enviar configuración', 'error');
            }
          }
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

  // sync_all sends config as flat camelCase properties, not nested under 'config'
  // But device_config_result sends nested 'config' with snake_case.
  // Handle both formats.
  const cfg = updated.config || {};
  // If no nested config, use flat properties from sync_all
  const hasNestedConfig = Object.keys(cfg).length > 0;
  const getVal = (snakeKey, camelKey, fallback) => {
    if (hasNestedConfig && snakeKey in cfg) return cfg[snakeKey];
    if (camelKey in updated) return updated[camelKey];
    return fallback;
  };

  const nameEl = container.querySelector('#cfgName');
  if (nameEl) nameEl.value = updated.name || '';

  const locEl = container.querySelector('#cfgLocation');
  if (locEl) locEl.value = updated.location || '';

  const capEl = container.querySelector('#cfgCapacity');
  if (capEl) capEl.value = getVal('capacity', 'capacity', 50);

  const bottomEl = container.querySelector('#cfgBottom');
  if (bottomEl) bottomEl.value = getVal('bottom_dist_mm', 'bottomDist', 900);

  const mirrorEl = container.querySelector('#cfgMirror');
  if (mirrorEl) mirrorEl.value = getVal('mirror_dist_mm', 'mirrorDist', 100);

  const minEl = container.querySelector('#cfgMinLevel');
  if (minEl) minEl.value = getVal('min_level', 'minLevel', 25);

  const maxEl = container.querySelector('#cfgMaxLevel');
  if (maxEl) maxEl.value = getVal('max_level', 'maxLevel', 90);

  const minRelayEl = container.querySelector('#cfgMinRelayOff');
  if (minRelayEl) minRelayEl.value = getVal('min_relay_off_min', 'minRelayOffMin', 3);

  const overflowEl = container.querySelector('#cfgOverflow');
  if (overflowEl) overflowEl.checked = getVal('overflow_protection', 'overflowProtection', true) !== false;

  const autoEl = container.querySelector('#cfgAutoRefill');
  if (autoEl) autoEl.checked = getVal('auto_refill', 'autoRefill', true);

  const menuLockEl = container.querySelector('#cfgMenuLock');
  if (menuLockEl) menuLockEl.checked = getVal('menu_lock', 'menuLock', false);

  const wifiLockEl = container.querySelector('#cfgWifiLock');
  if (wifiLockEl) wifiLockEl.checked = getVal('wifi_lock', 'wifiLock', false);

  const deviceLockEl = container.querySelector('#cfgDeviceLock');
  if (deviceLockEl) deviceLockEl.checked = getVal('device_lock', 'deviceLock', false);

  const pumpLockEl = container.querySelector('#cfgPumpLock');
  if (pumpLockEl) pumpLockEl.checked = getVal('pump_lock', 'pumpLock', false);

  const sensorLockEl = container.querySelector('#cfgSensorLock');
  if (sensorLockEl) sensorLockEl.checked = getVal('sensor_lock', 'sensorLock', false);

  const firmwareLockEl = container.querySelector('#cfgFirmwareLock');
  if (firmwareLockEl) firmwareLockEl.checked = getVal('firmware_lock', 'firmwareLock', false);

  const securityLockEl = container.querySelector('#cfgSecurityLock');
  if (securityLockEl) securityLockEl.checked = getVal('security_lock', 'securityLock', false);
}
