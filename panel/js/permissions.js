/* Permissions view — manage device permissions */

import { state, selectedDevice } from './state.js';
import { socket, on } from './ws.js';
import { el, toast } from './ui.js';

export function initPermissions() {
    const view = document.getElementById('view-permissions');
    if (!view) return;

    loadPermissions();

    el('grantForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        await grantPermission();
    });

    el('btnRefreshPerms')?.addEventListener('click', loadPermissions);
}

async function loadPermissions() {
    const dev = selectedDevice();
    if (!dev) {
        toast('Selecciona un dispositivo primero', 'warning');
        return;
    }

    await socket.connect();

    const result = await new Promise((resolve) => {
        const off = on('permissions_result', (data) => {
            off();
            resolve(data);
        });
        socket.send({ event: 'get_permissions', device_id: dev.id });
        setTimeout(() => { off(); resolve({ permissions: [] }); }, 5000);
    });

    renderPermissions(result.permissions || []);
}

function renderPermissions(permissions) {
    const container = document.querySelector('#view-permissions .table-wrap table');
    if (!container) return;

    if (!permissions.length) {
        container.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--muted);">Sin permisos</td></tr>';
        return;
    }

    let html = '<thead><tr><th>Usuario</th><th>Correo</th><th>Rol</th><th>Acciones</th></tr></thead><tbody>';
    permissions.forEach((perm) => {
        const roleLabel = { owner: 'Owner', editor: 'Editor', viewer: 'Viewer' }[perm.role] || perm.role;
        html += `
            <tr>
                <td>${perm.username || '—'}</td>
                <td>${perm.email || '—'}</td>
                <td><span class="badge">${roleLabel}</span></td>
                <td>
                    <button class="btn btn-ghost btn-sm btn-revoke-perm" data-user-id="${perm.user_id}">
                        Revocar
                    </button>
                </td>
            </tr>
        `;
    });
    html += '</tbody>';
    container.innerHTML = html;

    container.querySelectorAll('.btn-revoke-perm').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const userId = btn.dataset.userId;
            if (confirm('¿Revocar este permiso?')) {
                await revokePermission(userId);
            }
        });
    });
}

async function grantPermission() {
    const dev = selectedDevice();
    if (!dev) {
        toast('Selecciona un dispositivo primero', 'warning');
        return;
    }

    const email = el('grantEmail')?.value?.trim();
    const role = el('grantRole')?.value;

    if (!email) {
        toast('Ingresa el correo del usuario', 'warning');
        return;
    }

    await socket.connect();

    const result = await new Promise((resolve) => {
        const off = on('permissions_result', (data) => {
            off();
            resolve(data);
        });
        socket.send({ event: 'grant_permission', device_id: dev.id, email, role });
        setTimeout(() => { off(); resolve({ ok: false, error: 'timeout' }); }, 5000);
    });

    if (result.ok) {
        toast(`Permiso ${role} otorgado a ${email}`, 'success');
        el('grantEmail').value = '';
        loadPermissions();
    } else {
        toast(result.error || result.message || 'Error al otorgar permiso', 'error');
    }
}

async function revokePermission(userId) {
    const dev = selectedDevice();
    if (!dev) return;

    await socket.connect();

    const result = await new Promise((resolve) => {
        const off = on('permissions_result', (data) => {
            off();
            resolve(data);
        });
        socket.send({ event: 'revoke_permission', device_id: dev.id, user_id: userId });
        setTimeout(() => { off(); resolve({ ok: false, error: 'timeout' }); }, 5000);
    });

    if (result.ok) {
        toast('Permiso revocado', 'success');
        loadPermissions();
    } else {
        toast(result.error || result.message || 'Error al revocar permiso', 'error');
    }
}
