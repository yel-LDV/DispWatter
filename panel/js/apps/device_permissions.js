/* Device Permissions sub-window — Permisos por dispositivo con guardado/descarte */

import { state } from '../state.js';
import { socket, on } from '../ws.js';
import { toast } from '../ui.js';
import { showModal } from '../modal_dialog.js';

let _listeners = [];
let _deviceId = null;
let _originalPermissions = []; // Snapshot at open time for diff
let _currentPermissions = [];  // Current state with changes
let _hasChanges = false;

export function render(container, deviceId) {
  _listeners.forEach(({ event, fn }) => {
    import('../ws.js').then(mod => mod.off(event, fn));
  });
  _listeners = [];

  _deviceId = deviceId;
  _hasChanges = false;

  const dev = (state.allDevices || state.devices || []).find(d => d.id === deviceId);
  const devName = dev ? (dev.name || deviceId) : deviceId;

  container.innerHTML = `
    <div class="section-title">
      <h2>🔑 Permisos</h2>
      <span class="section-sub">${devName}</span>
    </div>

    <!-- Add permission form -->
    <div class="card" style="margin-bottom:16px;">
      <h3 class="card-title">Agregar permiso</h3>
      <form class="grant-form" id="permGrantForm">
        <div class="form-group">
          <label class="form-label">Correo del usuario</label>
          <input type="email" class="form-input" id="permEmail" required placeholder="usuario@email.com">
        </div>
        <div class="form-group">
          <label class="form-label">Rol</label>
          <select class="form-input" id="permRole">
            <option value="viewer">Viewer (solo ver)</option>
            <option value="editor">Editor (control bomba + config)</option>
            <option value="owner">Owner (todo)</option>
          </select>
        </div>
        <div class="btn-row" style="margin-top:12px;">
          <button class="btn btn-primary" type="submit">Agregar</button>
        </div>
      </form>
    </div>

    <!-- Current permissions table -->
    <div class="card">
      <div class="card-head">
        <h3 class="card-title">Permisos actuales</h3>
        <button class="btn btn-ghost btn-sm" id="permRefresh">Actualizar</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Usuario</th><th>Correo</th><th>Rol</th><th>Acción</th></tr></thead>
          <tbody class="perms-body">
            <tr><td colspan="4" class="empty-state">Cargando...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Save/Discard buttons at bottom -->
    <div class="btn-row" style="margin-top:16px;">
      <button class="btn btn-primary" id="permSave">Guardar cambios</button>
      <button class="btn btn-ghost" id="permDiscard">Descartar</button>
    </div>
  `;

  // Load permissions
  loadPermissions(container);

  // Bind events
  container.querySelector('#permGrantForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const email = document.getElementById('permEmail')?.value?.trim();
    const role = document.getElementById('permRole')?.value;
    if (!email) {
      toast('Ingresa el correo del usuario', 'warning');
      return;
    }
    grantPermission(email, role, container);
  });

  container.querySelector('#permRefresh').addEventListener('click', () => {
    loadPermissions(container);
  });

  container.querySelector('#permSave').addEventListener('click', () => {
    saveAndClose(container);
  });

  container.querySelector('#permDiscard').addEventListener('click', () => {
    discardAndClose(container);
  });

  // Listen for permission results
  const resultFn = (data) => {
    if (data.permissions) {
      _originalPermissions = JSON.parse(JSON.stringify(data.permissions));
      _currentPermissions = JSON.parse(JSON.stringify(data.permissions));
      renderPermissionsTable(container, data.permissions);
    }
    if (data.ok !== undefined) {
      if (data.ok) {
        toast(data.message || 'Operación exitosa', 'success');
        loadPermissions(container);
      } else {
        toast(data.error || data.message || 'Error en la operación', 'error');
      }
    }
  };
  on('permissions_result', resultFn);
  _listeners.push({ event: 'permissions_result', fn: resultFn });
}

function loadPermissions(container) {
  socket.send({ event: 'get_permissions', device_id: _deviceId });
}

function renderPermissionsTable(container, permissions) {
  const tbody = container.querySelector('.perms-body');
  if (!tbody) return;

  if (!permissions || !permissions.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty-state">Sin permisos</td></tr>';
    return;
  }

  const roleLabels = { owner: 'Owner', editor: 'Editor', viewer: 'Viewer' };
  let html = '';
  permissions.forEach((perm) => {
    const roleLabel = roleLabels[perm.role] || perm.role;
    html += `
      <tr>
        <td>${perm.username || '—'}</td>
        <td>${perm.email || '—'}</td>
        <td><span class="badge">${roleLabel}</span></td>
        <td>
          <button class="btn btn-ghost btn-sm btn-revoke-perm" data-user-id="${perm.user_id}" data-email="${perm.email || ''}">
            Revocar
          </button>
        </td>
      </tr>
    `;
  });
  tbody.innerHTML = html;

  // Bind revoke buttons
  tbody.querySelectorAll('.btn-revoke-perm').forEach(btn => {
    btn.addEventListener('click', async () => {
      const userId = btn.dataset.userId;
      const email = btn.dataset.email;
      const result = await showModal(
        'Revocar permiso',
        `¿Revocar el permiso de ${email}? El usuario perderá el acceso a este dispositivo.`,
        { confirmText: 'Revocar', danger: true, icon: '🔑' }
      );
      if (result?.confirmed) {
        revokePermission(userId);
      }
    });
  });
}

function grantPermission(email, role, container) {
  socket.send({
    event: 'grant_permission',
    device_id: _deviceId,
    email,
    role,
  });
  _hasChanges = true;
  document.getElementById('permEmail').value = '';
}

function revokePermission(userId) {
  socket.send({
    event: 'revoke_permission',
    device_id: _deviceId,
    user_id: userId,
  });
  _hasChanges = true;
}

function saveAndClose(container) {
  // Changes are already applied via WebSocket, just close
  const winEl = container.closest('.window');
  if (winEl) {
    const wm = window.__windowManager;
    if (wm) {
      // Temporarily allow close
      const w = wm.get(winEl.id);
      if (w) w._forceClose = true;
      wm.close(winEl.id);
    }
  }
  toast('Permisos guardados', 'success');
}

function discardAndClose(container) {
  // Close without applying pending changes (changes already sent via WebSocket)
  const winEl = container.closest('.window');
  if (winEl) {
    const wm = window.__windowManager;
    if (wm) {
      const w = wm.get(winEl.id);
      if (w) w._forceClose = true;
      wm.close(winEl.id);
    }
  }
  toast('Cambios descartados', 'info');
}

export function checkBeforeClose(windowId) {
  // Returns a promise that resolves to true if close is allowed
  return new Promise((resolve) => {
    if (!_hasChanges) {
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
      '¿Qué deseas hacer con los cambios en los permisos?',
      {
        confirmText: 'Guardar cambios',
        cancelText: 'Descartar',
        icon: '🔑'
      }
    ).then(result => {
      if (result?.confirmed) {
        // Save changes (already applied via WebSocket)
        toast('Permisos guardados', 'success');
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
