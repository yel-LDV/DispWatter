/* LCD Config view — configure display lines */

import { state, selectedDevice } from './state.js';
import { socket } from './ws.js';
import { el, toast } from './ui.js';

export function initLcdConfig() {
    const view = document.getElementById('view-lcd');
    if (!view) return;

    loadLcdConfig();

    el('lcdForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        await saveLcdConfig();
    });

    el('btnRefreshLcd')?.addEventListener('click', loadLcdConfig);
}

async function loadLcdConfig() {
    const dev = selectedDevice();
    if (!dev) {
        toast('Selecciona un dispositivo primero', 'warning');
        return;
    }

    await socket.connect();

    const result = await new Promise((resolve) => {
        const handler = (data) => {
            socket.ws?.removeEventListener('message', messageHandler);
            resolve(data);
        };
        const messageHandler = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.event === 'lcd_config_result') handler(data);
            } catch {}
        };
        socket.ws?.addEventListener('message', messageHandler);
        socket.send({ event: 'get_lcd_config', device_id: dev.id });
        setTimeout(() => {
            socket.ws?.removeEventListener('message', messageHandler);
            resolve({ config: {} });
        }, 5000);
    });

    const config = result.config || {};
    populateLcdForm(config);
}

function populateLcdForm(config) {
    const line0Select = el('lcdLine0');
    const line1Select = el('lcdLine1');
    if (line0Select) line0Select.value = config.line0_format || 'percent';
    if (line1Select) line1Select.value = config.line1_format || 'liters';

    const scrollSpeed = el('lcdScrollSpeed');
    const scrollPause = el('lcdScrollPause');
    const distanceUnit = el('lcdDistanceUnit');
    const customText0 = el('lcdCustomText0');
    const customText1 = el('lcdCustomText1');
    if (scrollSpeed) scrollSpeed.value = config.scroll_speed ?? 150;
    if (scrollPause) scrollPause.value = config.scroll_pause ?? 3000;
    if (distanceUnit) distanceUnit.value = config.distance_unit || 'cm';
    if (customText0) customText0.value = config.custom_text0 || '';
    if (customText1) customText1.value = config.custom_text1 || '';
}

async function saveLcdConfig() {
    const dev = selectedDevice();
    if (!dev) {
        toast('Selecciona un dispositivo primero', 'warning');
        return;
    }

    const config = {
        line0_format: el('lcdLine0')?.value || 'percent',
        line1_format: el('lcdLine1')?.value || 'liters',
        scroll_speed: parseInt(el('lcdScrollSpeed')?.value) || 150,
        scroll_pause: parseInt(el('lcdScrollPause')?.value) || 3000,
        distance_unit: el('lcdDistanceUnit')?.value || 'cm',
        custom_text0: el('lcdCustomText0')?.value || '',
        custom_text1: el('lcdCustomText1')?.value || '',
    };

    await socket.connect();

    const result = await new Promise((resolve) => {
        const handler = (data) => {
            socket.ws?.removeEventListener('message', messageHandler);
            resolve(data);
        };
        const messageHandler = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.event === 'lcd_config_result') handler(data);
            } catch {}
        };
        socket.ws?.addEventListener('message', messageHandler);
        socket.send({ event: 'update_lcd_config', device_id: dev.id, config });
        setTimeout(() => {
            socket.ws?.removeEventListener('message', messageHandler);
            resolve({ ok: false, error: 'timeout' });
        }, 5000);
    });

    if (result.ok) {
        toast('Configuración LCD guardada', 'success');
    } else {
        toast(result.error || 'Error al guardar', 'error');
    }
}
