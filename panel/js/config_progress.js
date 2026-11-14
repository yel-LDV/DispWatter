/* Config Progress — Ventana modal de progreso al guardar configuración del dispositivo */

import { on, off } from '../ws.js';

let _overlay = null;
let _window = null;
let _statusIcon = null;
let _statusText = null;
let _detailText = null;
let _acceptBtn = null;

function createOverlay() {
  _overlay = document.createElement('div');
  _overlay.className = 'config-progress-overlay';
  _overlay.innerHTML = `
    <div class="config-progress-window">
      <div class="config-progress-icon" id="cfgProgressIcon">⏳</div>
      <h3 class="config-progress-title">Guardando configuración</h3>
      <p class="config-progress-status" id="cfgProgressStatus">Enviando al backend...</p>
      <p class="config-progress-detail" id="cfgProgressDetail"></p>
      <button class="btn btn-primary" id="cfgProgressAccept" style="display:none;">Aceptar</button>
    </div>
  `;
  document.body.appendChild(_overlay);

  _statusIcon = document.getElementById('cfgProgressIcon');
  _statusText = document.getElementById('cfgProgressStatus');
  _detailText = document.getElementById('cfgProgressDetail');
  _acceptBtn = document.getElementById('cfgProgressAccept');
}

function setStatus(icon, status, detail = '') {
  if (_statusIcon) _statusIcon.textContent = icon;
  if (_statusText) _statusText.textContent = status;
  if (_detailText) _detailText.textContent = detail;
}

function showAccept() {
  if (_acceptBtn) _acceptBtn.style.display = 'inline-block';
}

function hide() {
  if (_overlay && _overlay.parentNode) {
    _overlay.parentNode.removeChild(_overlay);
  }
  _overlay = null;
  _window = null;
  _statusIcon = null;
  _statusText = null;
  _detailText = null;
  _acceptBtn = null;
}

/**
 * Muestra la ventana de progreso y espera hasta que se complete o se cancele.
 * @param {string} deviceId - ID del dispositivo
 * @returns {Promise<{ok: boolean, error: string}>} Resultado de la operación
 */
export function showConfigProgress(deviceId) {
  return new Promise((resolve) => {
    // Create overlay if not exists
    if (!_overlay) {
      createOverlay();
    }

    // Initial state
    setStatus('⏳', 'Enviando al backend...', `Dispositivo: ${deviceId}`);
    _acceptBtn.style.display = 'none';

    // Listen for the result event — static import, no delay
    const handler = (data) => {
      if (data.device_id !== deviceId) return;

      if (data.ok) {
        setStatus('✅', 'Configuración aplicada exitosamente', `El dispositivo ${deviceId} recibió y aplicó la configuración.`);
      } else {
        const errorMsg = data.error || 'desconocido';
        let userMsg = '';
        if (errorMsg === 'device_offline') {
          userMsg = 'El dispositivo no está conectado. La configuración se guardó en el servidor y se aplicará cuando el dispositivo se reconecte.';
        } else if (errorMsg === 'timeout') {
          userMsg = 'El dispositivo no respondió a tiempo. La configuración se guardó en el servidor y se intentará enviar cuando el dispositivo esté disponible.';
        } else {
          userMsg = `Error: ${errorMsg}`;
        }
        setStatus('⚠️', 'No se pudo enviar al dispositivo', userMsg);
      }

      showAccept();

      // Bind accept button
      const acceptHandler = () => {
        off('update_device_config_result', handler);
        hide();
        resolve({ ok: data.ok, error: data.error || '' });
      };
      _acceptBtn.addEventListener('click', acceptHandler);
    };
    on('update_device_config_result', handler);

    // Timeout fallback: if no response in 15s, show as failed
    setTimeout(() => {
      // Check if already resolved by checking if accept button is visible
      if (_acceptBtn && _acceptBtn.style.display === 'none') {
        setStatus('⚠️', 'Tiempo de espera agotado', 'El backend no respondió. La configuración se guardó en el servidor.');
        showAccept();
        const timeoutResolve = () => {
          hide();
          resolve({ ok: false, error: 'timeout_backend' });
        };
        _acceptBtn.addEventListener('click', timeoutResolve);
      }
    }, 15000);
  });
}
