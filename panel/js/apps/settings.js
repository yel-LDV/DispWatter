/* Settings app — Ajustes del panel */

import { state } from '../state.js';
import { socket } from '../ws.js';
import { toast, confirmAction } from '../ui.js';

export function render(container) {
  container.innerHTML = `
    <div class="section-title">
      <h2>Ajustes</h2>
      <span class="section-sub">Configuración del panel y cuenta.</span>
    </div>

    <div class="card">
      <div class="card-head"><h2>Cuenta</h2></div>
      <div class="status-list">
        <div class="status-row"><span class="status-label">Usuario</span><span class="status-value">${state.user?.username || '—'}</span></div>
        <div class="status-row"><span class="status-label">Rol</span><span class="status-value">${state.user?.role || '—'}</span></div>
        <div class="status-row"><span class="status-label">Correo</span><span class="status-value">${state.user?.email || '—'}</span></div>
      </div>
    </div>

    <div class="card" style="margin-top:16px;">
      <div class="card-head"><h2>Cambiar contraseña</h2></div>
      <form class="password-form">
        <div class="form-grid">
          <div class="field">
            <label>Contraseña actual</label>
            <input type="password" name="current" required>
          </div>
          <div class="field">
            <label>Nueva contraseña</label>
            <input type="password" name="new" minlength="6" required>
          </div>
          <div class="field">
            <label>Confirmar nueva</label>
            <input type="password" name="confirm" minlength="6" required>
          </div>
        </div>
        <div class="btn-row" style="margin-top:16px;">
          <button class="btn btn-primary" type="submit">Cambiar contraseña</button>
        </div>
      </form>
    </div>

    <div class="card" style="margin-top:16px;">
      <div class="card-head"><h2>Panel</h2></div>
      <div class="status-list">
        <div class="status-row"><span class="status-label">Tema</span><span class="status-value" id="settings-theme-label">Oscuro</span></div>
        <div class="status-row"><span class="status-label">Ventanas abiertas</span><span class="status-value" id="settings-window-count">0</span></div>
      </div>
      <div class="btn-row" style="margin-top:16px;">
        <button class="btn btn-ghost settings-theme-toggle" type="button">Cambiar tema</button>
        <button class="btn btn-danger settings-logout" type="button">Cerrar sesión</button>
      </div>
    </div>
  `;

  // Update window count
  const countEl = container.querySelector('#settings-window-count');
  if (countEl) {
    import('../window_manager.js').then(m => {
      countEl.textContent = m.windowManager.windows.size;
    });
  }

  // Password change
  container.querySelector('.password-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const current = fd.get('current');
    const newPwd = fd.get('new');
    const confirm = fd.get('confirm');

    if (newPwd !== confirm) {
      toast('Las contraseñas no coinciden', 'error');
      return;
    }

    socket.send({ event: 'change_password', current, new_password: newPwd });
    toast('Contraseña cambiada', 'success');
    e.target.reset();
  });

  // Theme toggle
  container.querySelector('.settings-theme-toggle')?.addEventListener('click', () => {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'light' ? 'dark' : 'light';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    const label = container.querySelector('#settings-theme-label');
    if (label) label.textContent = next === 'light' ? 'Claro' : 'Oscuro';
  });

  // Logout
  container.querySelector('.settings-logout')?.addEventListener('click', () => {
    confirmAction('¿Cerrar sesión?').then(ok => {
      if (ok) {
        socket.send({ event: 'logout' });
        import('../auth.js').then(m => m.logout());
      }
    });
  });
}
