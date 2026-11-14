/* Audit app — Registro de eventos */

import { socket } from '../ws.js';
import { formatDate } from '../ui.js';

export function render(container) {
  container.innerHTML = `
    <div class="section-title">
      <h2>Auditoría</h2>
      <span class="section-sub">Últimos 250 eventos del sistema.</span>
    </div>
    <div class="card">
      <div class="card-head">
        <h2>Registro</h2>
        <button class="btn btn-ghost btn-sm audit-refresh" type="button">Actualizar</button>
      </div>
      <div class="form-grid" style="margin-bottom:16px;">
        <div class="field">
          <label>Filtrar por acción</label>
          <input type="text" class="audit-filter-action" placeholder="LOGIN, WIFI, DEVICE…">
        </div>
        <div class="field">
          <label>Filtrar por dispositivo</label>
          <input type="text" class="audit-filter-device" placeholder="WATTER-001">
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Fecha</th><th>Acción</th><th>Usuario</th><th>Dispositivo</th><th>Detalle</th></tr>
          </thead>
          <tbody class="audit-body">
            <tr><td colspan="5" class="empty-state">Sin eventos cargados.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  `;

  loadAudit(container);

  container.querySelector('.audit-refresh').addEventListener('click', () => loadAudit(container));
  container.querySelector('.audit-filter-action').addEventListener('input', () => filterAudit(container));
  container.querySelector('.audit-filter-device').addEventListener('input', () => filterAudit(container));
}

let _auditEntries = [];

function loadAudit(container) {
  socket.send({ event: 'get_audit', limit: 250 });
}

function filterAudit(container) {
  const actionFilter = (container.querySelector('.audit-filter-action').value || '').toLowerCase();
  const deviceFilter = (container.querySelector('.audit-filter-device').value || '').toLowerCase();

  const filtered = _auditEntries.filter(entry => {
    if (actionFilter && !(entry.action || '').toLowerCase().includes(actionFilter)) return false;
    if (deviceFilter && !(entry.device_id || '').toLowerCase().includes(deviceFilter)) return false;
    return true;
  });

  renderAudit(container, filtered);
}

function renderAudit(container, entries) {
  const tbody = container.querySelector('.audit-body');
  if (!tbody) return;

  if (!entries || !entries.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Sin eventos.</td></tr>';
    return;
  }

  tbody.innerHTML = entries.map(e => `
    <tr>
      <td>${formatDate(e.timestamp)}</td>
      <td class="mono">${e.action || '—'}</td>
      <td>${e.username || '—'}</td>
      <td class="mono">${e.device_id || '—'}</td>
      <td>${e.detail || '—'}</td>
    </tr>
  `).join('');
}
