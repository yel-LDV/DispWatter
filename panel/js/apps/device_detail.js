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

  const cfg = dev.config || {};

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

      <!-- Menu lock section -->
      <div style="margin-top:16px; padding-top:12px; border-top:1px solid var(--border);">
        <h3 class="card-title" style="font-size:14px; margin-bottom:12px;">🔒 Bloqueo de menús (ESP32)</h3>
        <div class="form-group form-group-switch">
          <label class="form-label">Bloquear menú general</label>
          <label class="switch">
            <input type="checkbox" class="menu-lock-switch" data-lock="menu_lock" ${cfg.menu_lock ? 'checked' : ''}>
            <span class="switch-slider"></span>
          </label>
          <small class="form-hint">Impide abrir el menú de ajustes con Power+Back.</small>
        </div>
        <div class="form-group form-group-switch">
          <label class="form-label">Bloquear WiFi</label>
          <label class="switch">
            <input type="checkbox" class="menu-lock-switch" data-lock="wifi_lock" ${cfg.wifi_lock ? 'checked' : ''}>
            <span class="switch-slider"></span>
          </label>
          <small class="form-hint">Bloquea la sección de WiFi en el menú.</small>
        </div>
        <div class="form-group form-group-switch">
          <label class="form-label">Bloquear dispositivo</label>
          <label class="switch">
            <input type="checkbox" class="menu-lock-switch" data-lock="device_lock" ${cfg.device_lock ? 'checked' : ''}>
            <span class="switch-slider"></span>
          </label>
          <small class="form-hint">Bloquea reinicio, dormir y reset de fábrica.</small>
        </div>
        <div class="form-group form-group-switch">
          <label class="form-label">Bloquear bomba</label>
          <label class="switch">
            <input type="checkbox" class="menu-lock-switch" data-lock="pump_lock" ${cfg.pump_lock ? 'checked' : ''}>
            <span class="switch-slider"></span>
          </label>
          <small class="form-hint">Bloquea el control manual de la bomba.</small>
        </div>
        <div class="form-group form-group-switch">
          <label class="form-label">Bloquear sensores</label>
          <label class="switch">
            <input type="checkbox" class="menu-lock-switch" data-lock="sensor_lock" ${cfg.sensor_lock ? 'checked' : ''}>
            <span class="switch-slider"></span>
          </label>
          <small class="form-hint">Bloquea la calibración del sensor.</small>
        </div>
        <div class="form-group form-group-switch">
          <label class="form-label">Bloquear firmware</label>
          <label class="switch">
            <input type="checkbox" class="menu-lock-switch" data-lock="firmware_lock" ${cfg.firmware_lock ? 'checked' : ''}>
            <span class="switch-slider"></span>
          </label>
          <small class="form-hint">Bloquea las actualizaciones de firmware.</small>
        </div>
        <div class="form-group form-group-switch">
          <label class="form-label">Bloquear seguridad</label>
          <label class="switch">
            <input type="checkbox" class="menu-lock-switch" data-lock="security_lock" ${cfg.security_lock ? 'checked' : ''}>
            <span class="switch-slider"></span>
          </label>
          <small class="form-hint">Bloquea desvinculación y factory reset.</small>
        </div>
      </div>

      <!-- Firmware section -->
      <div style="margin-top:16px; padding-top:12px; border-top:1px solid var(--border);">
        <h3 class="card-title" style="font-size:14px; margin-bottom:12px;">📦 Firmware</h3>
        <div class="status-list">
          <div class="status-row"><span class="status-label">Versión actual</span><span class="status-value mono" id="firmwareCurrent">${dev.firmware_version || dev.firmware || '—'}</span></div>
        </div>
        <div class="btn-row" style="margin-top:12px;">
          <button class="btn btn-primary device-ota" data-id="${dev.id}">Actualizar firmware</button>
        </div>
        <div id="otaList" class="ota-list-container" style="display:none; margin-top:12px;"></div>
        <div id="otaProgress" class="ota-progress-container" style="display:none; margin-top:12px;"></div>
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

  // Bind menu lock switches — send update_device_config immediately on toggle
  container.querySelectorAll('.menu-lock-switch').forEach(switchEl => {
    switchEl.addEventListener('change', () => {
      const lockKey = switchEl.dataset.lock;
      const checked = switchEl.checked;
      // Send menu lock update to backend
      socket.send({
        event: 'update_device_config',
        device_id: dev.id,
        name: '',
        location: '',
        config: { [lockKey]: checked },
      });
      toast(`${lockKey.replace('_lock', '')} ${checked ? 'bloqueado' : 'desbloqueado'}`, 'info');
    });
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

  // Bind OTA button — load available firmware versions
  container.querySelector('.device-ota').addEventListener('click', () => {
    loadOtaVersions(dev.id, container);
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
  const fwEl = container.querySelector('#firmwareCurrent');
  if (fwEl) fwEl.textContent = updated.firmware_version || updated.firmware || '—';
}

// ── OTA Firmware Update ──────────────────────────────────────────────

async function loadOtaVersions(deviceId, container) {
  const listEl = container.querySelector('#otaList');
  const progressEl = container.querySelector('#otaProgress');
  const btnEl = container.querySelector('.device-ota');

  // If already showing list, toggle off
  if (listEl.style.display !== 'none' && !progressEl.querySelector('.ota-progress-bar')) {
    listEl.style.display = 'none';
    btnEl.textContent = 'Actualizar firmware';
    return;
  }

  // Fetch available versions and show list
  btnEl.disabled = true;
  btnEl.textContent = 'Buscando actualizaciones...';

  await socket.connect();

  const result = await new Promise((resolve) => {
    const off = on('ota_versions_result', (data) => {
      off();
      resolve(data);
    });
    socket.send({ event: 'list_ota_versions' });
    setTimeout(() => { off(); resolve({ versions: [] }); }, 15000);
  });

  const versions = result.versions || [];
  if (!versions.length) {
    btnEl.disabled = false;
    btnEl.textContent = 'Actualizar firmware';
    toast('No hay versiones disponibles en GitHub', 'warning');
    return;
  }

  const currentFw = (state.allDevices || state.devices || []).find(d => d.id === deviceId);
  const currentVersion = currentFw?.firmware_version || currentFw?.firmware || '';

  // Show all versions as a selectable list
  btnEl.disabled = false;
  btnEl.textContent = 'Cerrar lista';
  listEl.style.display = 'block';
  listEl.innerHTML = '';

  versions.forEach((v) => {
    const typeLabel = { stable: 'Estable', experimental: 'Experimental', insecure: 'Insegura' }[v.type] || v.type;
    const typeIcon = { stable: '✓', experimental: '◐', insecure: '⚠' }[v.type] || '?';
    const isCurrent = v.tag === currentVersion;

    const card = document.createElement('div');
    card.className = `ota-card-detail type-${v.type || 'experimental'}${isCurrent ? ' current' : ''}`;
    card.style.cssText = `
      padding: 12px;
      margin-bottom: 8px;
      border-radius: 8px;
      border: 1px solid ${isCurrent ? 'var(--neon-red)' : 'var(--border)'};
      background: ${isCurrent ? 'rgba(220,38,38,0.05)' : 'rgba(255,255,255,0.02)'};
    `;
    card.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <span style="font-weight:600; font-size:14px; color:var(--text-0);">v${v.tag}</span>
        <span style="font-size:12px; color:var(--text-2);">${typeIcon} ${typeLabel}</span>
      </div>
      <div style="font-size:12px; color:var(--text-2); margin-bottom:4px;">
        ${v.branch || 'desconocida'}${v.published_at ? ' · ' + new Date(v.published_at).toLocaleDateString() : ''}
      </div>
      ${v.body ? `<div style="font-size:12px; color:var(--text-1); margin-bottom:8px; line-height:1.4;">${v.body.substring(0, 150)}${v.body.length > 150 ? '...' : ''}</div>` : ''}
      <div style="display:flex; justify-content:flex-end;">
        ${isCurrent
          ? '<span style="font-size:12px; color:var(--neon-red);">✓ Versión actual</span>'
          : `<button class="btn btn-sm btn-install-ota" data-version="${v.tag}" data-size="${v.size || 0}">Instalar</button>`
        }
      </div>
    `;
    listEl.appendChild(card);
  });

  // Bind install buttons
  listEl.querySelectorAll('.btn-install-ota').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const version = btn.dataset.version;
      await startOtaUpdate(deviceId, container, version);
    });
  });
}

async function startOtaUpdate(deviceId, container, version) {
  const progressEl = container.querySelector('#otaProgress');
  const btnEl = container.querySelector('.device-ota');

  // Show confirmation
  const result = await showModal(
    'Actualizar firmware',
    `¿Actualizar el dispositivo a <strong>v${version}</strong>? El dispositivo se reiniciará automáticamente después de la actualización.`,
    { confirmText: 'Actualizar', danger: true, icon: '📦' }
  );
  if (!result?.confirmed) return;

  // Show progress bar
  progressEl.style.display = 'block';
  progressEl.innerHTML = `
    <div style="padding:12px;">
      <div style="font-size:13px; color:var(--text-1); margin-bottom:8px;" id="otaStatus">Iniciando actualización a v${version}...</div>
      <div class="ota-progress-bar" style="height:4px; border-radius:2px; background:var(--border); overflow:hidden;">
        <div class="ota-progress-fill" style="height:100%; width:0%; background:var(--neon-red); transition:width 0.3s;"></div>
      </div>
    </div>
  `;
  btnEl.disabled = true;
  btnEl.textContent = 'Actualizando...';

  const statusEl = progressEl.querySelector('#otaStatus');
  const fillEl = progressEl.querySelector('.ota-progress-fill');

  const updateProgress = (status, message) => {
    if (statusEl) statusEl.textContent = message;
    const widths = { downloading: '30%', pushing: '60%', verifying: '80%', complete: '100%', error: '100%' };
    if (fillEl && widths[status]) fillEl.style.width = widths[status];
  };

  const otaResult = await new Promise((resolve) => {
    const offProgress = on('ota_progress', (data) => {
      const statusMessages = {
        downloading: `Descargando v${data.version}...`,
        pushing: `Enviando firmware al dispositivo...`,
        verifying: `Verificando actualización...`,
        complete: `Actualización completada. El dispositivo se reiniciará.`,
        error: `Error: ${data.error || 'Desconocido'}`,
      };
      updateProgress(data.status, statusMessages[data.status] || data.status);
      if (data.status === 'complete' || data.status === 'error') {
        offProgress();
        offError();
        resolve({ ok: data.status === 'complete', status: data.status });
      }
    });
    const offError = on('error', (data) => {
      offProgress();
      offError();
      updateProgress('error', `Error: ${data.message || 'Desconocido'}`);
      resolve({ ok: false, status: 'error' });
    });
    socket.send({ event: 'start_ota_update', device_id: deviceId, version });
    setTimeout(() => {
      offProgress();
      offError();
      updateProgress('error', 'Tiempo de espera agotado');
      resolve({ ok: false, status: 'error' });
    }, 120000);
  });

  // Restore button state
  btnEl.disabled = false;
  btnEl.textContent = 'Actualizar firmware';

  if (otaResult.ok) {
    toast('Firmware actualizado exitosamente', 'success');
  } else {
    toast('La actualización falló', 'error');
  }

  // Hide progress after delay
  setTimeout(() => {
    progressEl.style.display = 'none';
    progressEl.innerHTML = '';
  }, 5000);
}
