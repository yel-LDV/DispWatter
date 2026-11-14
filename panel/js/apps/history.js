/* History app — Gráfico y tabla de telemetría histórica */

import { state } from '../state.js';
import { socket } from '../ws.js';
import { formatDate } from '../ui.js';

export function render(container) {
  container.innerHTML = `
    <div class="section-title">
      <h2>Historial</h2>
      <span class="section-sub">Telemetría del dispositivo seleccionado.</span>
    </div>
    <div class="card">
      <div class="card-head">
        <h2>Gráfico</h2>
        <div class="btn-row">
          <select class="select-inline history-period">
            <option value="24h">24 horas</option>
            <option value="7d" selected>7 días</option>
            <option value="30d">30 días</option>
          </select>
          <button class="btn btn-ghost btn-sm history-refresh" type="button">Actualizar</button>
        </div>
      </div>
      <div class="history-stats" style="margin-bottom:16px;"></div>
      <canvas class="history-chart" height="200" style="width:100%;background:var(--card-bg);border-radius:8px;"></canvas>
      <div class="table-wrap" style="margin-top:16px;max-height:300px;overflow-y:auto;">
        <table>
          <thead><tr><th>Fecha</th><th>% Agua</th><th>Litros</th><th>Bomba</th></tr></thead>
          <tbody class="history-body">
            <tr><td colspan="4" class="empty-state">Selecciona un dispositivo.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  `;

  container.querySelector('.history-refresh').addEventListener('click', () => loadHistory(container));
  container.querySelector('.history-period').addEventListener('change', () => loadHistory(container));
  loadHistory(container);
}

function loadHistory(container) {
  const period = container.querySelector('.history-period').value;
  const deviceId = state.selectedId;
  if (!deviceId) return;

  socket.send({ event: 'get_history', device_id: deviceId, period });

  // Simple placeholder chart
  const canvas = container.querySelector('.history-chart');
  if (canvas) {
    const ctx = canvas.getContext('2d');
    canvas.width = canvas.offsetWidth;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = 'var(--text-2)';
    ctx.font = '14px Inter';
    ctx.textAlign = 'center';
    ctx.fillText('Gráfico de telemetría', canvas.width / 2, canvas.height / 2);
  }
}
