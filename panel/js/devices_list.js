/* Device history list with OTA per device */

import { state } from './state.js';
import { socket, on } from './ws.js';
import { openModal, closeModal, toast } from './ui.js';

export function initDevicesList() {
    const view = document.getElementById('view-devices');
    if (!view) return;

    renderDevicesList();

    view.querySelector('#btnRefreshDevices')?.addEventListener('click', renderDevicesList);
}

function renderDevicesList() {
    const body = document.getElementById('devicesBody');
    if (!body) return;

    const devices = state.allDevices || state.devices || [];
    if (!devices.length) {
        body.innerHTML = '<tr><td colspan="6" class="empty-state">Sin dispositivos.</td></tr>';
        return;
    }

    body.innerHTML = '';
    devices.forEach((dev) => {
        const tr = document.createElement('tr');
        const statusClass = dev.online ? 'badge online' : 'badge offline';
        const statusText = dev.online ? 'Online' : 'Offline';
        const lastSeen = dev.last_seen ? new Date(dev.last_seen).toLocaleString() : '—';

        tr.innerHTML = `
            <td>${dev.name || '—'}</td>
            <td class="mono">${dev.id}</td>
            <td><span class="${statusClass}">${statusText}</span></td>
            <td class="mono">v${dev.firmware_version || '—'}</td>
            <td>${lastSeen}</td>
            <td>
                <button class="btn btn-ghost btn-sm btn-device-ota" data-device-id="${dev.id}" data-device-name="${dev.name || dev.id}">
                    Actualizar firmware
                </button>
            </td>
        `;
        body.appendChild(tr);
    });

    body.querySelectorAll('.btn-device-ota').forEach((btn) => {
        btn.addEventListener('click', (e) => {
            const deviceId = e.target.dataset.deviceId;
            const deviceName = e.target.dataset.deviceName;
            openOtaModal(deviceId, deviceName);
        });
    });
}

async function openOtaModal(deviceId, deviceName) {
    const container = document.createElement('div');
    container.className = 'form-grid';

    const listDiv = document.createElement('div');
    listDiv.id = 'otaVersionList';
    listDiv.style.gridColumn = '1 / -1';
    listDiv.innerHTML = '<p class="loading">Cargando versiones...</p>';
    container.appendChild(listDiv);

    openModal(`Actualizar firmware: ${deviceName}`, container, [
        { label: 'Cerrar', className: 'btn-ghost', onClick: closeModal },
    ]);

    await loadOtaVersions(deviceId, listDiv);
}

async function loadOtaVersions(deviceId, listDiv) {
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
        listDiv.innerHTML = '<p class="empty">No hay versiones disponibles. Las versiones se publican automáticamente desde GitHub Releases cuando se compila el firmware con GitHub Actions.</p>';
        return;
    }

    listDiv.innerHTML = '';
    versions.forEach((v) => {
        const card = document.createElement('div');
        card.style.cssText = 'border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:8px;';

        const typeLabel = { stable: 'Estable', experimental: 'Experimental', insecure: 'Insegura' }[v.type] || v.type;
        const typeIcon = { stable: '✓', experimental: '◐', insecure: '⚠' }[v.type] || '?';
        const dateStr = v.published_at ? new Date(v.published_at).toLocaleDateString() : '';
        const forkBadge = v.is_fork ? ' <span style="color:var(--danger);font-size:0.8em;">(Fork)</span>' : '';

        card.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <strong>v${v.tag}</strong>
                <span style="font-size:0.85em;">${typeIcon} ${typeLabel}${forkBadge}</span>
            </div>
            <div style="font-size:0.8em;color:var(--muted);margin:4px 0;">
                ${v.branch || '—'} · ${dateStr}
            </div>
            ${v.body ? `<div style="font-size:0.85em;margin:6px 0;">${v.body.substring(0, 150)}</div>` : ''}
            <button class="btn btn-primary btn-sm btn-select-ota" data-version="${v.tag}" data-device-id="${deviceId}">
                Seleccionar
            </button>
        `;
        listDiv.appendChild(card);
    });

    listDiv.querySelectorAll('.btn-select-ota').forEach((btn) => {
        btn.addEventListener('click', (e) => {
            const version = e.target.dataset.version;
            const devId = e.target.dataset.deviceId;
            startOtaUpdate(devId, version);
        });
    });
}

async function startOtaUpdate(deviceId, version) {
    await socket.connect();

    const result = await new Promise((resolve) => {
        const offProgress = on('ota_progress', (data) => {
            if (data.status === 'complete' || data.status === 'error') {
                offProgress();
                offError();
                resolve(data);
            }
        });
        const offError = on('error', (data) => {
            offProgress();
            offError();
            resolve({ ok: false, error: data.message });
        });
        socket.send({ event: 'start_ota_update', device_id: deviceId, version });
        setTimeout(() => { offProgress(); offError(); resolve({ ok: false, error: 'timeout' }); }, 120000);
    });

    if (result.status === 'complete') {
        toast('Actualización completada. El dispositivo se reiniciará.', 'success');
    } else {
        toast(`Error: ${result.error || 'Desconocido'}`, 'error');
    }
}
