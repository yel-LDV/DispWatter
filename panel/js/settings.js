/* User settings: change password */

import { socket, on } from './ws.js';

export function initSettings() {
    const view = document.getElementById('view-settings');
    if (!view) return;

    const form = view.querySelector('#changePasswordForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const oldPass = form.querySelector('#oldPassword').value;
        const newPass = form.querySelector('#newPassword').value;
        const confirmPass = form.querySelector('#confirmNewPassword').value;
        const errorEl = view.querySelector('#passwordError');
        const successEl = view.querySelector('#passwordSuccess');

        errorEl.textContent = '';
        successEl.textContent = '';

        if (newPass !== confirmPass) {
            errorEl.textContent = 'Las contraseñas no coinciden';
            return;
        }
        if (newPass.length < 6) {
            errorEl.textContent = 'La contraseña debe tener al menos 6 caracteres';
            return;
        }

        await socket.connect();
        const result = await new Promise((resolve) => {
            const off = on('ack', (data) => { off(); resolve(data); });
            const offErr = on('error', (data) => { off(); offErr(); resolve(data); });
            socket.send({ event: 'change_password', old_password: oldPass, new_password: newPass });
            setTimeout(() => { off(); offErr(); resolve({ ok: false, error: 'timeout' }); }, 10000);
        });

        if (result.ok) {
            successEl.textContent = 'Contraseña cambiada correctamente';
            form.reset();
        } else {
            errorEl.textContent = result.message || result.error || 'Error al cambiar contraseña';
        }
    });
}
