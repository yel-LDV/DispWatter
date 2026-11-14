/* Permissions app — Gestión de permisos */

import { state } from '../state.js';
import { socket } from '../ws.js';
import { toast, confirmAction } from '../ui.js';

export function render(container) {
  container.innerHTML = `
    <div class="section-title">
      <h2>Permisos</h2>
      <span class="section-sub">Gestiona quién puede acceder a este dispositivo.</span>
    </div>
    <div class="card">
      <div class="card-head"><h2>Agregar permiso</h2></div>
      <form class="grant-form" style="margin-bottom:16px;">
        <div class="form-grid">
          <div class="field">
            <label>Correo del usuario</label>
            <input type="email" name="email" required placeholder="usuario@email.com">
          </div>
          <div class="field">
            <label>Rol</label>
            <select name="role">
              <option value="viewer">Viewer (solo ver)</option>
              <option value="editor">Editor (control bomba + config)</option>
              <option value="owner">Owner (todo)</option>
            </select>
          </div>
        </div>
        <div class="btn-row" style="margin-top:12px;">
          <button class="btn btn-primary" type="submit">Otorgar</button>
        </div>
      </form>
    </div>
    <div class="card" style="margin-top:16px;">
      <div class="card-head">
        <h2>Permisos actuales</h2>
        <button class="btn btn-ghost btn-sm perms-refresh" type="button">Actualizar</button>
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
  `;

  loadPermissions(container);

  container.querySelector('.grant-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    socket.send({
      event: 'grant_permission',
      device_id: state.selectedId,
      email: fd.get('email'),
      role: fd.get('role'),
    });
    toast('Permiso otorgado', 'success');
    loadPermissions(container);
  });

  container.querySelector('.perms-refresh').addEventListener('click', () => loadPermissions(container));
}

function loadPermissions(container) {
  socket.send({ event: 'get_permissions', device_id: state.selectedId });
}
