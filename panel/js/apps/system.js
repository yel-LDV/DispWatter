/* System app — Acciones remotas del dispositivo */

import { state } from '../state.js';
import { socket } from '../ws.js';
import { toast, confirmAction } from '../ui.js';

export function render(container) {
  container.innerHTML = `
    <div class="section-title">
      <h2>Sistema</h2>
      <span class="section-sub">Acciones remotas del dispositivo seleccionado.</span>
    </div>
    <div class="card">
      <div class="card-head"><h2>Acciones del dispositivo</h2></div>
      <div class="form-grid">
        <div class="field">
          <label>Minutos de deep sleep</label>
          <input type="number" class="system-sleep-min" min="1" max="1440" value="60">
        </div>
        <div class="check-row" style="padding-top:0;">
          <span class="field-hint">El relé se apaga antes de reiniciar o dormir.</span>
        </div>
      </div>
      <div class="btn-row" style="margin-top:16px;">
        <button class="btn btn-ghost system-reboot" type="button">Reiniciar ESP32</button>
        <button class="btn btn-ghost system-sleep" type="button">Dormir</button>
        <button class="btn btn-magenta system-reset" type="button">Reset de fábrica</button>
        <button class="btn btn-danger system-delete" type="button">Eliminar del panel</button>
      </div>
    </div>
    <div class="notice">
      <span aria-hidden="true">⚠</span>
      <span>El reset de fábrica borra <span class="mono">/config.json</span> del ESP32. Requiere rol administrador.</span>
    </div>
  `;

  container.querySelector('.system-reboot').addEventListener('click', () => {
    confirmAction('¿Reiniciar el dispositivo?').then(ok => {
      if (ok) {
        socket.send({ event: 'reboot', device_id: state.selectedId });
        toast('Reinicio enviado', 'success');
      }
    });
  });

  container.querySelector('.system-sleep').addEventListener('click', () => {
    const minutes = parseInt(container.querySelector('.system-sleep-min').value) || 60;
    confirmAction(`¿Poner en deep sleep ${minutes} min?`).then(ok => {
      if (ok) {
        socket.send({ event: 'sleep', device_id: state.selectedId, minutes });
        toast(`Sleep ${minutes} min enviado`, 'success');
      }
    });
  });

  container.querySelector('.system-reset').addEventListener('click', () => {
    confirmAction('¿Reset de fábrica? Se borrará toda la configuración del dispositivo.').then(ok => {
      if (ok) {
        socket.send({ event: 'factory_reset', device_id: state.selectedId });
        toast('Reset de fábrica enviado', 'success');
      }
    });
  });

  container.querySelector('.system-delete').addEventListener('click', () => {
    confirmAction('¿Eliminar el dispositivo del panel? Esta acción no se puede deshacer.').then(ok => {
      if (ok) {
        socket.send({ event: 'delete_device', device_id: state.selectedId });
        toast('Dispositivo eliminado', 'success');
      }
    });
  });
}
