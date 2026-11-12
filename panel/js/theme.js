/**
 * Theme toggle: claro / oscuro
 * La preferencia se guarda en localStorage.
 */

const STORAGE_KEY = 'dispwatter-theme';

export function initTheme() {
    // Apply saved theme or default to dark
    const saved = localStorage.getItem(STORAGE_KEY);
    const theme = saved || 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    
    // Find and setup toggle button
    const toggle = document.getElementById('themeToggle');
    if (toggle) {
        toggle.addEventListener('click', () => {
            const current = document.documentElement.getAttribute('data-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem(STORAGE_KEY, next);
        });
    }
}
