/* Device Config app — Configuración de valores y bloqueo de menú del ESP32 */

import { state } from '../state.js';
import { socket, on } from '../ws.js';
import { toast } from '../ui.js';

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

  const cfg = dev.config || {};

  container.innerHTML = `
    <div class="section-title">
      <h2>⚙ Configurar</h2>
      <span class="section-sub">${dev.name || deviceId}</span>
    </div>

    <!-- General section -->
    <div class="card" style="margin-bottom:16px;">
      <h3 class="card-title">General</h3>
      <div class="form-group">
        <label class="form-label">Nombre del dispositivo</label>
        <input type="text" class="form-input" id="cfgName" value="${dev.name || ''}" maxlength="128" placeholder="Bebedero Principal">
      </div>
      <div class="form-group">
        <label class="form-label">Ubicación</label>
        <input type="text" class="form-input" id="cfgLocation" value="${dev.location || ''}" maxlength="128" placeholder="Granero">
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
      <button class="btn btn-ghost" id="cfgCancel">Cancelar</button>
    </div>
  `;

  // Bind save button
  container.querySelector('#cfgSave').addEventListener('click', () => saveConfig(dev.id));

  // Bind cancel button
  container.querySelector('#cfgCancel').addEventListener('click', () => {
    // Close this window
    const winEl = container.closest('.window');
    if (winEl) {
      import('../window_manager.js').then(mod => {
        // Find the window manager instance via app.js
        const wm = window.__windowManager;
        if (wm) wm.close(winEl.id);
      });
    }
  });

  // Listen for sync_all to update config values automatically
  const syncFn = (data) => {
    const devices = data.all_devices || data.devices || [];
    const updated = devices.find(d => d.id === deviceId);
    if (updated) {
      updateConfigDisplay(updated);
    }
  };
  on('sync_all', syncFn);
  _listeners.push({ event: 'sync_all', fn: syncFn });
}

function saveConfig(deviceId) {
  const name = document.getElementById('cfgName')?.value?.trim() || '';
  const location = document.getElementById('cfgLocation')?.value?.trim() || '';
  const capacity = parseFloat(document.getElementById('cfgCapacity')?.value) || 50;
  const bottom = parseFloat(document.getElementById('cfgBottom')?.value) || 900;
  const mirror = parseFloat(document.getElementById('cfgMirror')?.value) || 100;
  const minLevel = parseFloat(document.getElementById('cfgMinLevel')?.value) || 25;
  const maxLevel = parseFloat(document.getElementById('cfgMaxLevel')?.value) || 90;
  const minRelayOff = parseFloat(document.getElementById('cfgMinRelayOff')?.value) || 3;
  const overflowProtection = document.getElementById('cfgOverflow')?.checked ?? true;
  const autoRefill = document.getElementById('cfgAutoRefill')?.checked ?? true;
  const menuLock = document.getElementById('cfgMenuLock')?.checked ?? false;

  // Validate
  if (capacity < 0.1 || capacity > 100000) {
    toast('Capacidad inválida (0.1 - 100000)', 'error');
    return;
  }
  if (bottom < 10 || bottom > 12000) {
    toast('Distancia de fondo inválida (10 - 12000)', 'error');
    return;
  }
  if (mirror < 0 || mirror >= bottom) {
    toast('Distancia espejo inválida (0 - fondo)', 'error');
    return;
  }
  if (bottom - mirror < 20) {
    toast('Altura útil mínima: 20 mm', 'error');
    return;
  }
  if (minLevel < 0 || minLevel > 100 || maxLevel < 0 || maxLevel > 100 || minLevel >= maxLevel) {
    toast('Niveles inválidos (mín < máx)', 'error');
    return;
  }
  if (maxLevel - minLevel < 5) {
    toast('Diferencia mín/máx: al menos 5 puntos', 'error');
    return;
  }

  socket.send({
    event: 'update_device_config',
    device_id: deviceId,
    name: name,
    location: location,
    config: {
      capacity,
      bottom_dist_mm: bottom,
      mirror_dist_mm: mirror,
      min_level: minLevel,
      max_level: maxLevel,
      auto_refill: autoRefill,
      min_relay_off_min: minRelayOff,
      overflow_protection: overflowProtection,
      menu_lock: menuLock,
    },
  });

  toast('Guardando configuración...', 'info');
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
