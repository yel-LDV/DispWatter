/* OTA firmware versions */

import { socket, on } from './ws.js';

export function initOta() {
    const view = document.getElementById('view-ota');
    if (!view) return;

    const listEl = view.querySelector('.ota-list');
    if (!listEl) return;

    loadVersions();

    view.querySelector('.btn-refresh')?.addEventListener('click', loadVersions);
}

async function loadVersions() {
    const listEl = document.querySelector('#view-ota .ota-list');
    if (!listEl) return;

    await socket.connect();
    listEl.innerHTML = '<p class="loading">Cargando versiones...</p>';

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
        listEl.innerHTML = '<p class="empty">No hay versiones disponibles</p>';
        return;
    }

    listEl.innerHTML = '';
    versions.forEach((v) => {
        const card = document.createElement('div');
        card.className = `ota-card type-${v.type || 'experimental'}`;

        const typeLabel = { stable: 'Estable', experimental: 'Experimental', insecure: 'Insegura' }[v.type] || v.type;
        const typeIcon = { stable: '✓', experimental: '◐', insecure: '⚠' }[v.type] || '?';

        card.innerHTML = `
            <div class="ota-header">
                <span class="ota-version">v${v.tag}</span>
                <span class="ota-type ${v.type}">${typeIcon} ${typeLabel}</span>
            </div>
            <div class="ota-meta">
                <span>${v.branch || 'desconocida'}</span>
                <span>${v.published_at ? new Date(v.published_at).toLocaleDateString() : ''}</span>
            </div>
            ${v.body ? `<div class="ota-body">${v.body.substring(0, 200)}</div>` : ''}
            <div class="ota-actions">
                <button class="btn btn-primary btn-update-ota" data-version="${v.tag}" data-size="${v.size || 0}">
                    Actualizar
                </button>
            </div>
        `;
        listEl.appendChild(card);
    });

    listEl.querySelectorAll('.btn-update-ota').forEach((btn) => {
        btn.addEventListener('click', (e) => {
            const version = e.target.dataset.version;
            startOtaUpdate(version);
        });
    });
}

async function startOtaUpdate(version) {
    await socket.connect();

    const progressEl = document.querySelector('#view-ota .ota-progress');
    if (progressEl) {
        progressEl.style.display = 'block';
        progressEl.textContent = 'Iniciando actualización...';
    }

    const result = await new Promise((resolve) => {
        const offProgress = on('ota_progress', (data) => {
            if (progressEl) {
                progressEl.textContent = `Estado: ${data.status} (v${data.version})`;
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
        socket.send({ event: 'start_ota_update', version });
        setTimeout(() => { offProgress(); offError(); resolve({ ok: false, error: 'timeout' }); }, 120000);
    });

    if (progressEl) {
        if (result.ok || result.status === 'complete') {
            progressEl.textContent = 'Actualización completada. El dispositivo se reiniciará.';
        } else {
            progressEl.textContent = `Error: ${result.error || 'Desconocido'}`;
        }
        setTimeout(() => { progressEl.style.display = 'none'; }, 5000);
    }
}
