/* LCD app — Configuración del display LCD */

import { state } from '../state.js';
import { socket } from '../ws.js';
import { toast } from '../ui.js';

export function render(container) {
  container.innerHTML = `
    <div class="section-title">
      <h2>Configuración LCD</h2>
      <span class="section-sub">Personaliza qué se muestra en cada línea del display.</span>
    </div>
    <div class="card">
      <form class="lcd-form">
        <div class="form-grid">
          <div class="field">
            <label for="lcd-line0">Línea 1</label>
            <select name="line0_format">
              <option value="percent">Porcentaje de agua</option>
              <option value="liters">Litros</option>
              <option value="distance">Distancia</option>
              <option value="pump_status">Estado bomba</option>
              <option value="custom">Texto personalizado</option>
              <option value="empty">Vacío</option>
            </select>
          </div>
          <div class="field">
            <label for="lcd-line1">Línea 2</label>
            <select name="line1_format">
              <option value="percent">Porcentaje de agua</option>
              <option value="liters" selected>Litros</option>
              <option value="distance">Distancia</option>
              <option value="pump_status">Estado bomba</option>
              <option value="custom">Texto personalizado</option>
              <option value="empty">Vacío</option>
            </select>
          </div>
          <div class="field">
            <label>Unidad distancia</label>
            <select name="distance_unit">
              <option value="cm" selected>Centímetros (cm)</option>
              <option value="mm">Milímetros (mm)</option>
              <option value="m">Metros (m)</option>
            </select>
          </div>
          <div class="field">
            <label>Velocidad scroll (ms)</label>
            <input type="number" name="scroll_speed" min="100" max="500" value="200">
          </div>
          <div class="field">
            <label>Pausa final (seg)</label>
            <input type="number" name="scroll_pause" min="1" max="10" value="3">
          </div>
          <div class="field">
            <label>Texto personalizado L1</label>
            <input type="text" name="custom0" maxlength="64" placeholder="Texto opcional">
          </div>
          <div class="field">
            <label>Texto personalizado L2</label>
            <input type="text" name="custom1" maxlength="64" placeholder="Texto opcional">
          </div>
        </div>
        <div class="btn-row" style="margin-top:16px;">
          <button class="btn btn-primary" type="submit">Guardar configuración</button>
        </div>
      </form>
    </div>
  `;

  container.querySelector('.lcd-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const data = {
      event: 'set_lcd_config',
      device_id: state.selectedId,
      line0_format: fd.get('line0_format'),
      line1_format: fd.get('line1_format'),
      distance_unit: fd.get('distance_unit'),
      scroll_speed: parseInt(fd.get('scroll_speed')),
      scroll_pause: parseInt(fd.get('scroll_pause')),
      custom0: fd.get('custom0'),
      custom1: fd.get('custom1'),
    };
    socket.send(data);
    toast('Configuración LCD guardada', 'success');
  });
}
