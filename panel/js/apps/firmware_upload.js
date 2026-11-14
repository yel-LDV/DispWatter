/* Firmware Upload — Subir y gestionar firmware para OTA */

import { state } from '../state.js';
import { socket, on } from '../ws.js';
import { toast, confirmAction } from '../ui.js';

export function render(container) {
  container.innerHTML = `
    <div class="section-title">
      <h2>Gestión de Firmware</h2>
      <span class="section-sub">Sube firmware .bin desde otro dispositivo y actualiza el ESP32 por OTA.</span>
    </div>

    <!-- Upload form -->
    <div class="card">
      <div class="card-head"><h2>Subir firmware</h2></div>
      <div class="form-grid">
        <div class="field">
          <label>Nombre</label>
          <input type="text" class="fw-name" placeholder="ej: firmware-patch-1">
        </div>
        <div class="field">
          <label>Versión</label>
          <input type="text" class="fw-version" placeholder="ej: 1.0.2" required>
        </div>
        <div class="field">
          <label>Descripción</label>
          <input type="text" class="fw-description" placeholder="ej: corrección de sensor">
        </div>
        <div class="field">
          <label>Tipo</label>
          <select class="fw-type">
            <option value="custom">Custom</option>
            <option value="experimental">Experimental</option>
            <option value="stable">Estable</option>
          </select>
        </div>
        <div class="field" style="grid-column: 1 / -1;">
          <label>Archivo .bin</label>
          <input type="file" class="fw-file" accept=".bin">
        </div>
      </div>
      <div class="btn-row" style="margin-top:16px;">
        <button class="btn btn-primary fw-upload-btn" type="button">Subir firmware</button>
      </div>
      <p class="fw-upload-status" style="margin-top:10px; font-size:13px;"></p>
    </div>

    <!-- List -->
    <div class="card" style="margin-top:20px;">
      <div class="card-head">
        <h2>Firmware almacenados</h2>
        <button class="btn btn-ghost fw-refresh" type="button">Refrescar</button>
      </div>
      <div class="fw-list">
        <p class="loading">Cargando...</p>
      </div>
    </div>

    <!-- OTA progress -->
    <div class="fw-ota-progress" style="display:none; margin-top:16px;">
      <div class="card">
        <div class="card-head"><h2>Actualización OTA</h2></div>
        <p class="fw-ota-status">Iniciando...</p>
      </div>
    </div>
  `;

  // Upload button
  container.querySelector('.fw-upload-btn').addEventListener('click', () => handleUpload(container));

  // Refresh button
  container.querySelector('.fw-refresh').addEventListener('click', () => loadFirmwares(container));

  // Load initial list
  loadFirmwares(container);
}

async function handleUpload(container) {
  const name = (container.querySelector('.fw-name').value || '').trim();
  const version = (container.querySelector('.fw-version').value || '').trim();
  const description = (container.querySelector('.fw-description').value || '').trim();
  const firmwareType = container.querySelector('.fw-type').value;
  const fileInput = container.querySelector('.fw-file');
  const statusEl = container.querySelector('.fw-upload-status');

  if (!version) {
    toast('Introduce la versión del firmware', 'error');
    return;
  }
  if (!fileInput.files.length) {
    toast('Selecciona un archivo .bin', 'error');
    return;
  }

  const file = fileInput.files[0];
  statusEl.textContent = 'Leyendo archivo...';

  try {
    const arrayBuffer = await file.arrayBuffer();
    const uint8 = new Uint8Array(arrayBuffer);
    const hex = Array.from(uint8).map(b => b.toString(16).padStart(2, '0')).join('');

    statusEl.textContent = `Enviando (${(file.size / 1024).toFixed(1)} KB)...`;

    await socket.connect();

    const result = await new Promise((resolve) => {
      const off = on('firmware_upload_result', (data) => {
        off();
        resolve(data);
      });
      const offErr = on('error', (data) => {
        off();
        offErr();
        resolve({ ok: false, error: data.message });
      });
      socket.send({
        event: 'upload_firmware',
        name,
        version,
        binary_hex: hex,
        description: description || null,
        firmware_type: firmwareType,
      });
      setTimeout(() => { off(); offErr(); resolve({ ok: false, error: 'timeout' }); }, 60000);
    });

    if (result.ok) {
      statusEl.textContent = '';
      toast(`Firmware ${result.firmware.version} subido correctamente`, 'success');
      container.querySelector('.fw-name').value = '';
      container.querySelector('.fw-version').value = '';
      container.querySelector('.fw-description').value = '';
      fileInput.value = '';
      loadFirmwares(container);
    } else {
      statusEl.textContent = '';
      toast(result.error || 'Error al subir', 'error');
    }
  } catch (err) {
    statusEl.textContent = '';
    toast('Error al leer el archivo: ' + err.message, 'error');
  }
}

async function loadFirmwares(container) {
  const listEl = container.querySelector('.fw-list');
  listEl.innerHTML = '<p class="loading">Cargando...</p>';

  await socket.connect();

  const result = await new Promise((resolve) => {
    const off = on('firmware_list_result', (data) => {
      off();
      resolve(data);
    });
    socket.send({ event: 'list_firmwares' });
    setTimeout(() => { off(); resolve({ firmwares: [] }); }, 10000);
  });

  const firmwares = result.firmwares || [];
  if (!firmwares.length) {
    listEl.innerHTML = '<p class="empty">No hay firmware almacenados</p>';
    return;
  }

  listEl.innerHTML = '';
  firmwares.forEach((fw) => {
    const card = document.createElement('div');
    card.className = 'fw-card';
    const typeLabel = { stable: 'Estable', experimental: 'Experimental', custom: 'Custom' }[fw.firmware_type] || fw.firmware_type;
    const typeIcon = { stable: '✓', experimental: '◐', custom: '⚙' }[fw.firmware_type] || '?';
    const sizeKB = (fw.size / 1024).toFixed(1);
    const date = fw.uploaded_at ? new Date(fw.uploaded_at).toLocaleString() : '';

    card.innerHTML = `
      <div class="fw-card-header">
        <span class="fw-card-version">v${fw.version}</span>
        <span class="fw-card-type ${fw.firmware_type}">${typeIcon} ${typeLabel}</span>
      </div>
      <div class="fw-card-meta">
        <span>${fw.name}</span>
        <span>${sizeKB} KB</span>
        <span>${date}</span>
      </div>
      ${fw.description ? `<div class="fw-card-desc">${fw.description}</div>` : ''}
      <div class="fw-card-sha"><span class="mono">${fw.sha256.substring(0, 16)}...</span></div>
      <div class="fw-card-actions">
        <button class="btn btn-primary btn-flash-fw" data-firmware-id="${fw.id}" data-version="${fw.version}">
          Flashear
        </button>
        <button class="btn btn-ghost btn-delete-fw" data-firmware-id="${fw.id}">
          Eliminar
        </button>
      </div>
    `;
    listEl.appendChild(card);
  });

  // Flash buttons
  listEl.querySelectorAll('.btn-flash-fw').forEach((btn) => {
    btn.addEventListener('click', () => {
      const firmwareId = btn.dataset.firmwareId;
      const version = btn.dataset.version;
      startOtaFromUpload(firmwareId, version, container);
    });
  });

  // Delete buttons
  listEl.querySelectorAll('.btn-delete-fw').forEach((btn) => {
    btn.addEventListener('click', () => {
      const firmwareId = btn.dataset.firmwareId;
      confirmAction('¿Eliminar este firmware?').then(ok => {
        if (ok) deleteFirmware(firmwareId, container);
      });
    });
  });
}

async function startOtaFromUpload(firmwareId, version, container) {
  if (!state.selectedId) {
    toast('Selecciona un dispositivo primero', 'error');
    return;
  }

  const progressEl = container.querySelector('.fw-ota-progress');
  const statusEl = container.querySelector('.fw-ota-status');
  progressEl.style.display = 'block';
  statusEl.textContent = 'Preparando actualización...';

  await socket.connect();

  const result = await new Promise((resolve) => {
    const offProgress = on('ota_progress', (data) => {
      if (statusEl) {
        const statusText = {
          preparing: 'Preparando...',
          pushing: `Enviando al dispositivo... (${data.progress || 0}%)`,
          verifying: 'Verificando...',
          complete: 'Actualización completada. El dispositivo se reiniciará.',
          error: `Error: ${data.error || 'Desconocido'}`,
        };
        statusEl.textContent = statusText[data.status] || data.status;
      }
      if (data.status === 'complete' || data.status === 'error') {
        offProgress();
        resolve(data);
      }
    });
    const offError = on('error', (data) => {
      offProgress();
      offError();
      resolve({ ok: false, error: data.message });
    });
    socket.send({
      event: 'start_ota_from_upload',
      device_id: state.selectedId,
      firmware_id: parseInt(firmwareId),
    });
    setTimeout(() => { offProgress(); offError(); resolve({ ok: false, error: 'timeout' }); }, 120000);
  });

  if (result.status === 'complete') {
    toast('Firmware actualizado correctamente', 'success');
  } else {
    toast(result.error || 'Error en la actualización', 'error');
  }
  setTimeout(() => { progressEl.style.display = 'none'; }, 8000);
}

async function deleteFirmware(firmwareId, container) {
  await socket.connect();

  const result = await new Promise((resolve) => {
    const off = on('ack', (data) => { off(); resolve(data); });
    const offErr = on('error', (data) => { off(); offErr(); resolve({ ok: false, error: data.message }); });
    socket.send({ event: 'delete_firmware', firmware_id: parseInt(firmwareId) });
    setTimeout(() => { off(); offErr(); resolve({ ok: false, error: 'timeout' }); }, 10000);
  });

  if (result.ok) {
    toast('Firmware eliminado', 'success');
    loadFirmwares(container);
  } else {
    toast(result.error || 'Error al eliminar', 'error');
  }
}
