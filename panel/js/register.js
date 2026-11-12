/**
 * Registro de usuarios
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
                successEl.textContent = result.message || 'Cuenta creada. Revisa tu correo para verificar.';
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

// Handle verification result (from URL params)
export function checkVerificationResult() {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');

    if (!token) return;

    // Remove token from URL
    window.history.replaceState({}, '', window.location.pathname);

    (async () => {
        try {
            await socket.connect();
            const result = await new Promise((resolve) => {
                const off = on('verify_result', (data) => {
                    off();
                    resolve(data);
                });
                socket.send({ event: 'verify_email', token });
            });

            const msgEl = document.getElementById('verifyMessage');
            if (msgEl) {
                msgEl.textContent = result.message || (result.ok ? 'Verificado' : 'Error');
                msgEl.className = result.ok ? 'success-msg' : 'error-msg';
            }
        } catch (err) {
            console.error('Verification error:', err);
        }
    })();
}
