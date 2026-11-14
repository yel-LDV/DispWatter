/* ModalDialog — Ventana modal bloqueante encima de todas las ventanas */

import { windowManager } from './window_manager.js';

let _activeModal = null;   // { windowId, resolve, backdrop }
let _modalZBase = 9999;    // Siempre encima de ventanas normales (zCounter ~100+)

/**
 * Muestra un diálogo modal bloqueante.
 * @param {string} title — Título del diálogo
 * @param {string} message — Mensaje (texto o HTML) o descripción
 * @param {object} [options]
 * @param {string} [options.confirmText='Aceptar'] — Texto del botón de confirmación
 * @param {string} [options.cancelText='Cancelar'] — Texto del botón de cancelar
 * @param {boolean} [options.danger=false] — Si true, el botón de confirmación es rojo
 * @param {string} [options.icon='⚠'] — Icono en la barra de título
 * @param {Function} [options.onConfirm] — Callback async antes de cerrar. Si retorna false, no cierra. Si retorna otro valor, se incluye en el resultado.
 * @returns {Promise<object>} { confirmed: boolean, result?: any } — result contiene el valor retornado por onConfirm
 */
export function showModal(title, message, options = {}) {
  if (_activeModal) {
    // Ya hay un modal activo, no permitir otro
    return Promise.resolve({ confirmed: false });
  }

  const confirmText = options.confirmText || options.confirmLabel || 'Aceptar';
  const cancelText = options.cancelText || options.cancelLabel || 'Cancelar';
  const danger = options.danger || false;
  const icon = options.icon || '⚠';
  const onConfirm = options.onConfirm || null;

  return new Promise((resolve) => {
    // Create backdrop overlay that blocks interaction with all windows
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop';
    backdrop.style.cssText = `
      position: fixed;
      inset: 0;
      z-index: ${_modalZBase};
      background: rgba(0, 0, 0, 0.6);
      backdrop-filter: blur(4px);
    `;

    // Create modal window element
    const modalWin = document.createElement('div');
    modalWin.className = 'modal-dialog-window';
    const modalId = `modal-${Date.now()}`;
    modalWin.id = modalId;
    modalWin.style.cssText = `
      position: fixed;
      z-index: ${_modalZBase + 1};
      width: min(460px, calc(100vw - 48px));
      left: 50%;
      top: 50%;
      transform: translate(-50%, -50%);
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 32px 80px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(220, 38, 38, 0.3);
      backdrop-filter: blur(20px);
      background: linear-gradient(180deg, rgba(30, 18, 32, 0.97) 0%, rgba(15, 11, 19, 0.99) 100%);
      animation: modal-in 0.2s ease-out;
    `;

    // Titlebar
    const titlebar = document.createElement('div');
    titlebar.style.cssText = `
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 0 16px;
      height: 40px;
      flex-shrink: 0;
      background: rgba(220, 38, 38, 0.1);
      border-bottom: 1px solid rgba(220, 38, 38, 0.2);
      user-select: none;
    `;
    titlebar.innerHTML = `
      <span style="font-size:14px; opacity:0.9; width:18px; text-align:center;">${icon}</span>
      <span style="flex:1; font-size:13px; font-weight:600; color:var(--text-0); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${title}</span>
    `;

    // Body — support HTML messages
    const body = document.createElement('div');
    body.style.cssText = `
      padding: 24px 24px 16px;
      font-size: 14px;
      line-height: 1.6;
      color: var(--text-1);
    `;
    if (message.includes('<')) {
      body.innerHTML = message;
    } else {
      body.textContent = message;
    }

    // Footer with buttons
    const footer = document.createElement('div');
    footer.style.cssText = `
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      padding: 16px 24px;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
    `;

    const cancelButton = document.createElement('button');
    cancelButton.type = 'button';
    cancelButton.textContent = cancelText;
    cancelButton.style.cssText = `
      padding: 8px 20px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: transparent;
      color: var(--text-1);
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s;
    `;
    cancelButton.addEventListener('mouseenter', () => {
      cancelButton.style.borderColor = 'rgba(255,255,255,0.2)';
      cancelButton.style.background = 'rgba(255,255,255,0.05)';
    });
    cancelButton.addEventListener('mouseleave', () => {
      cancelButton.style.borderColor = 'var(--border)';
      cancelButton.style.background = 'transparent';
    });
    cancelButton.addEventListener('click', () => closeModal({ confirmed: false }));

    const confirmButton = document.createElement('button');
    confirmButton.type = 'button';
    confirmButton.textContent = confirmText;
    if (danger) {
      confirmButton.style.cssText = `
        padding: 8px 20px;
        border-radius: 8px;
        border: none;
        background: linear-gradient(135deg, #dc2626, #b91c1c);
        color: #fff;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.15s;
        box-shadow: 0 2px 8px rgba(220, 38, 38, 0.3);
      `;
      confirmButton.addEventListener('mouseenter', () => {
        confirmButton.style.background = 'linear-gradient(135deg, #ef4444, #dc2626)';
        confirmButton.style.boxShadow = '0 4px 16px rgba(220, 38, 38, 0.5)';
      });
      confirmButton.addEventListener('mouseleave', () => {
        confirmButton.style.background = 'linear-gradient(135deg, #dc2626, #b91c1c)';
        confirmButton.style.boxShadow = '0 2px 8px rgba(220, 38, 38, 0.3)';
      });
    } else {
      confirmButton.style.cssText = `
        padding: 8px 20px;
        border-radius: 8px;
        border: none;
        background: linear-gradient(135deg, #dc2626, #b91c1c);
        color: #fff;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.15s;
        box-shadow: 0 2px 8px rgba(220, 38, 38, 0.3);
      `;
    }
    confirmButton.addEventListener('click', async () => {
      if (onConfirm) {
        try {
          const result = await onConfirm();
          if (result === false) return; // prevent close
          closeModal({ confirmed: true, result });
        } catch (e) {
          closeModal({ confirmed: false });
        }
      } else {
        closeModal({ confirmed: true });
      }
    });

    footer.appendChild(cancelButton);
    footer.appendChild(confirmButton);
    modalWin.append(titlebar, body, footer);

    // Append to body
    document.body.appendChild(backdrop);
    document.body.appendChild(modalWin);

    // Store state
    _activeModal = { windowId: modalId, resolve, backdrop, modalWin };

    // Focus confirm button
    confirmButton.focus();

    function closeModal(result) {
      if (!_activeModal) return;
      _activeModal.backdrop.remove();
      _activeModal.modalWin.remove();
      _activeModal = null;
      resolve(result || { confirmed: false });
    }
  });
}

/**
 * Cierra el modal activo forzosamente (para uso interno).
 */
export function forceCloseModal() {
  if (_activeModal) {
    const r = _activeModal.resolve;
    _activeModal.backdrop.remove();
    _activeModal.modalWin.remove();
    _activeModal = null;
    r({ confirmed: false });
  }
}
