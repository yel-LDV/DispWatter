/* Dashboard app — Tanque, métricas, telemetría, controles */

import { state, selectedDevice, setSelectedDevice } from '../state.js';
import { socket, on, off } from '../ws.js';
import { el, toast, formatDate, formatUptime, formatRssi, signalLevel } from '../ui.js';

let _listeners = [];

function offAll() {
  _listeners.forEach(({ event, fn }) => off(event, fn));
  _listeners = [];
}

function listen(event, fn) {
  on(event, fn);
  _listeners.push({ event, fn });
}

// Initialize dashboard with current data from state (sync_all may have already arrived)
function initDashboard(container) {
  const dev = (state.allDevices || state.devices || []).find(d => d.id === state.selectedId);
  if (!dev) return;

  // Set relay state from sync data
  const relayState = dev.relayState !== undefined ? dev.relayState : false;
  const relaySwitch = container.querySelector('.dash-relay-switch');
  if (relaySwitch) relaySwitch.checked = !!relayState;
  const relayEl = container.querySelector('#dash-relay');
  if (relayEl) relayEl.textContent = relayState ? 'ON' : 'OFF';

  // Set auto refill state
  const autoRefill = dev.autoRefill !== undefined ? dev.autoRefill : false;
  const autoSwitch = container.querySelector('.dash-auto-switch');
  if (autoSwitch) autoSwitch.checked = !!autoRefill;

  // Update telemetry display if cached data is available
  if (dev.waterPercent != null) {
    container.querySelector('#dash-percent').textContent = dev.waterPercent;
    container.querySelector('#dash-liters').textContent = dev.waterLiters ?? '—';
    container.querySelector('#dash-dist').textContent = dev.currentDist ?? '—';
    // Tank fill
    const fill = container.querySelector('.tank-fill');
    const pctDisplay = container.querySelector('.tank-percent');
    if (fill) {
      fill.style.height = dev.waterPercent + '%';
      if (dev.waterPercent < 15) {
        fill.style.background = 'linear-gradient(180deg, rgba(255,59,92,0.92), rgba(220,38,38,0.92))';
      } else if (dev.waterPercent < 30) {
        fill.style.background = 'linear-gradient(180deg, rgba(255,179,0,0.92), rgba(217,119,6,0.92))';
      } else {
        fill.style.background = 'linear-gradient(180deg, rgba(0,229,255,0.92), rgba(45,123,255,0.92))';
      }
    }
    if (pctDisplay) pctDisplay.textContent = dev.waterPercent + '%';
  }
  // Update status info
  container.querySelector('#dash-online').textContent = dev.online ? 'En línea' : 'Desconectado';
  container.querySelector('#dash-rssi').textContent = dev.rssi != null ? formatRssi(dev.rssi) : '—';
  container.querySelector('#dash-ip').textContent = dev.ip || '—';
  container.querySelector('#dash-firmware').textContent = dev.firmware_version || '—';
  container.querySelector('#dash-location').textContent = dev.location || '—';
  // Enable/disable switches based on online status
  const isOnline = dev && dev.online;
  const rSw = container.querySelector('.dash-relay-switch');
  const aSw = container.querySelector('.dash-auto-switch');
  if (rSw) rSw.disabled = !isOnline;
  if (aSw) aSw.disabled = !isOnline;
}

export function render(container, deviceId) {
  offAll();

  const onlineDevices = (state.allDevices || state.devices || []).filter(d => d.online);
  const selectedId = state.selectedId;

  container.innerHTML = `
    <!-- Dashboard header with device selector and refresh button -->
    <div class="dash-header">
      <div class="dash-header-left">
        <h2 class="dash-header-title">Estado del bebedero</h2>
      </div>
      <div class="dash-header-right">
        <select class="dash-device-select" id="dashDeviceSelect" title="Seleccionar dispositivo">
          ${onlineDevices.map(d => `
            <option value="${d.id}" ${d.id === selectedId ? 'selected' : ''}>
              ${d.name || d.id} (${d.id})
            </option>
          `).join('')}
          ${onlineDevices.length === 0 ? '<option value="">Sin dispositivos online</option>' : ''}
        </select>
        <button class="dash-refresh-btn" id="dashRefreshBtn" title="Actualizar datos">↻</button>
      </div>
    </div>

    <div class="section-title">
      <span class="badge pending" id="dashStatusBadge"><span class="dot"></span><span>Sin datos</span></span>
    </div>

    <div class="card-grid grid-4">
      <div class="metric">
        <div class="metric-label">Nivel de agua</div>
        <div class="metric-value cyan"><span id="dash-percent">—</span><span class="metric-unit">%</span></div>
      </div>
      <div class="metric">
        <div class="metric-label">Volumen</div>
        <div class="metric-value green"><span id="dash-liters">—</span><span class="metric-unit">L</span></div>
      </div>
      <div class="metric">
        <div class="metric-label">Distancia</div>
        <div class="metric-value"><span id="dash-dist">—</span><span class="metric-unit">mm</span></div>
      </div>
      <div class="metric">
        <div class="metric-label">Bomba</div>
        <div class="metric-value magenta" id="dash-relay">—</div>
      </div>
    </div>

    <div class="dashboard-grid">
      <div class="card tank-wrap">
        <div class="tank" role="img" aria-label="Nivel del depósito">
          <div class="tank-fill" style="height: 0%;"></div>
          <div class="tank-readout">
            <div class="tank-percent">—%</div>
            <div class="tank-caption">Nivel</div>
          </div>
        </div>
        <div class="control-stack">
          <label class="switch-row">
            <span class="switch-text">
              <span class="switch-title">Bomba</span>
              <span class="switch-state">—</span>
            </span>
            <span class="switch">
              <input type="checkbox" role="switch" class="dash-relay-switch" disabled>
              <span class="switch-track"><span class="switch-thumb"></span></span>
            </span>
          </label>
          <label class="switch-row">
            <span class="switch-text">
              <span class="switch-title">Llenado automático</span>
              <span class="switch-state">—</span>
            </span>
            <span class="switch">
              <input type="checkbox" role="switch" class="dash-auto-switch" disabled>
              <span class="switch-track"><span class="switch-thumb"></span></span>
            </span>
          </label>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h2>Telemetría y conexión</h2>
        </div>
        <div class="status-list">
          <div class="status-row"><span class="status-label">Estado</span><span class="status-value" id="dash-online">—</span></div>
          <div class="status-row"><span class="status-label">Señal WiFi</span><span class="status-value" id="dash-rssi">—</span></div>
          <div class="status-row"><span class="status-label">Dirección IP</span><span class="status-value" id="dash-ip">—</span></div>
          <div class="status-row"><span class="status-label">Uptime</span><span class="status-value" id="dash-uptime">—</span></div>
          <div class="status-row"><span class="status-label">Firmware</span><span class="status-value" id="dash-firmware">—</span></div>
          <div class="status-row"><span class="status-label">Ubicación</span><span class="status-value" id="dash-location">—</span></div>
        </div>
      </div>
    </div>
  `;

  // Habilitar switches cuando el dispositivo está online
  function enableSwitchesIfOnline(container) {
    const dev = selectedDevice();
    const isOnline = dev && dev.online;
    const relaySwitch = container.querySelector('.dash-relay-switch');
    const autoSwitch = container.querySelector('.dash-auto-switch');
    if (relaySwitch) relaySwitch.disabled = !isOnline;
    if (autoSwitch) autoSwitch.disabled = !isOnline;
  }

  // Listen for telemetry updates
  listen('telemetry', (data) => {
    if (data.device_id !== state.selectedId) return;
    updateTelemetry(data);
    enableSwitchesIfOnline(container);
  });

  listen('relay_state', (data) => {
    if (data.device_id !== state.selectedId) return;
    const relayOn = !!data.relay_state;
    const switchEl = container.querySelector('.dash-relay-switch');
    if (switchEl) {
      switchEl.checked = relayOn;
      switchEl.disabled = false;
    }
    const relayEl = container.querySelector('#dash-relay');
    if (relayEl) relayEl.textContent = relayOn ? 'ON' : 'OFF';
  });

  // Unified sync_all listener: refresh dashboard + update device selector
  listen('sync_all', () => {
    initDashboard(container);
    updateDeviceSelect(container);
  });

  // Listen for device_status to update online/offline in real time
  listen('device_status', (data) => {
    if (data.device_id !== state.selectedId) return;
    // Update the device in state so initDashboard() returns fresh data
    const devices = state.allDevices || state.devices || [];
    const idx = devices.findIndex(d => d.id === data.device_id);
    if (idx >= 0) {
      devices[idx].online = !!data.is_online;
      if (data.rssi !== undefined) devices[idx].rssi = data.rssi;
      if (data.ip) devices[idx].ip = data.ip;
      if (data.firmware) devices[idx].firmware_version = data.firmware;
    }
    // Refresh the entire dashboard with updated state
    initDashboard(container);
  });

  // Relay switch toggle
  container.querySelector('.dash-relay-switch')?.addEventListener('change', (e) => {
    socket.send({ event: 'set_relay', device_id: state.selectedId, state: e.target.checked });
  });

  // Auto switch toggle
  container.querySelector('.dash-auto-switch')?.addEventListener('change', (e) => {
    socket.send({ event: 'set_auto_refill', device_id: state.selectedId, auto_refill: e.target.checked });
  });

  // Initialize with current data from state (sync_all may have already arrived during login)
  initDashboard(container);

  // Device selector change handler
  const deviceSelect = container.querySelector('#dashDeviceSelect');
  if (deviceSelect) {
    deviceSelect.addEventListener('change', (e) => {
      const newDeviceId = e.target.value;
      if (newDeviceId) {
        setSelectedDevice(newDeviceId);
        initDashboard(container);
        toast(`Dispositivo cambiado a ${newDeviceId}`, 'info');
      }
    });
  }

  // Refresh button handler
  const refreshBtn = container.querySelector('#dashRefreshBtn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      socket.send({ event: 'sync' });
      toast('Actualizando datos...', 'info');
    });
  }

  // Notification bell is now a fixed button in the desktop, not in the dashboard

  // Update device selector options when sync_all arrives
  function updateDeviceSelect(container) {
    const select = container.querySelector('#dashDeviceSelect');
    if (!select) return;
    const onlineDevices = (state.allDevices || state.devices || []).filter(d => d.online);
    const currentVal = select.value;
    select.innerHTML = onlineDevices.map(d => `
      <option value="${d.id}" ${d.id === state.selectedId ? 'selected' : ''}>
        ${d.name || d.id} (${d.id})
      </option>
    `).join('') || '<option value="">Sin dispositivos online</option>';
    // Preserve selection if still available
    if (onlineDevices.find(d => d.id === currentVal)) {
      select.value = currentVal;
    }
  }
}

function updateTelemetry(data) {
  const container = document.querySelector('.window-content:has(#dash-percent)');
  if (!container) return;

  const pct = data.water_percent ?? '—';
  const liters = data.water_liters ?? '—';
  const dist = data.distance_mm ?? '—';

  container.querySelector('#dash-percent').textContent = pct;
  container.querySelector('#dash-liters').textContent = liters;
  container.querySelector('#dash-dist').textContent = dist;

  // Tank fill
  const fill = container.querySelector('.tank-fill');
  const pctDisplay = container.querySelector('.tank-percent');
  if (fill && typeof pct === 'number') {
    fill.style.height = pct + '%';
    // Color by level
    if (pct < 15) {
      fill.style.background = 'linear-gradient(180deg, rgba(255,59,92,0.92), rgba(220,38,38,0.92))';
    } else if (pct < 30) {
      fill.style.background = 'linear-gradient(180deg, rgba(255,179,0,0.92), rgba(217,119,6,0.92))';
    } else {
      fill.style.background = 'linear-gradient(180deg, rgba(0,229,255,0.92), rgba(45,123,255,0.92))';
    }
  }
  if (pctDisplay) pctDisplay.textContent = typeof pct === 'number' ? pct + '%' : '—%';

  // Status
  const dev = selectedDevice();
  if (dev) {
    container.querySelector('#dash-online').textContent = dev.online ? 'En línea' : 'Desconectado';
    container.querySelector('#dash-rssi').textContent = dev.rssi != null ? formatRssi(dev.rssi) : '—';
    container.querySelector('#dash-ip').textContent = dev.ip || '—';
    container.querySelector('#dash-uptime').textContent = dev.uptime ? formatUptime(dev.uptime) : '—';
    container.querySelector('#dash-firmware').textContent = dev.firmware || '—';
    container.querySelector('#dash-location').textContent = dev.location || '—';
  }
}
