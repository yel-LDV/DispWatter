/**
 * Registro de usuarios sin verificación por email
 */

import { socket, on } from './ws.js';

export function initRegister() {
    const form = document.getElementById('registerForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const email = document.getElementById('registerEmail').value.trim();
        const password = document.getElementById('registerPassword').value;
        const confirmPassword = document.getElementById('registerConfirmPassword').value;
        const errorEl = document.getElementById('registerError');
        const successEl = document.getElementById('registerSuccess');

        errorEl.textContent = '';
        successEl.textContent = '';

        if (password !== confirmPassword) {
            errorEl.textContent = 'Las contraseñas no coinciden';
            return;
        }

        if (password.length < 6) {
            errorEl.textContent = 'La contraseña debe tener al menos 6 caracteres';
            return;
        }

        if (!email.includes('@')) {
            errorEl.textContent = 'Correo electrónico no válido';
            return;
        }

        try {
            const result = await register(email, password);
            if (result.ok) {
                successEl.textContent = result.message || 'Cuenta creada. Ya puedes iniciar sesión.';
                form.reset();
            } else {
                errorEl.textContent = result.message || 'Error al registrar';
            }
        } catch (err) {
            errorEl.textContent = 'Error de conexión';
        }
    });
}

async function register(email, password) {
    await socket.connect();
    return new Promise((resolve) => {
        const off = on('register_result', (data) => {
            off();
            resolve(data);
        });
        socket.send({ event: 'register', email, password });
    });
}
