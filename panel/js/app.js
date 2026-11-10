/**
 * DispWatter - Frontend Panel Logic
 * Gestión multi-dispositivo, vinculación criptográfica (claim) y monitoreo de tanques.
 */

// Estado global de la aplicación
const AppState = {
    devices: JSON.parse(localStorage.getItem('dispwatter_devices')) || [
        {
            id: 'WATTER-001',
            name: 'Bebedero Principal (Patio)',
            hash: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
            claimed: true,
            online: true,
            capacity: 50,
            bottomDist: 900,
            mirrorDist: 100,
            minLevel: 25,
            maxLevel: 90,
            autoRefill: true,
            currentDist: 380,
            relayState: false,
            lcdLine0: 'Nivel: 65%  32L',
            lcdLine1: 'Bomba: APAGADA'
        }
    ],
    selectedDeviceId: 'WATTER-001',
    ws: null,
    wsConnected: false
};

// Utilidad criptográfica en navegador (SHA-256)
async function sha256Hex(text) {
    const encoder = new TextEncoder();
    const data = encoder.encode(text);
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

// Inicialización al cargar el DOM
document.addEventListener('DOMContentLoaded', () => {
    initDeviceSelector();
    initEventListeners();
    updateUI();
    connectWebSocket();
    startSimulationLoop();
});

// Inicializar selector de dispositivos
function initDeviceSelector() {
    const select = document.getElementById('deviceSelect');
    select.innerHTML = '';
    
    AppState.devices.forEach(dev => {
        const option = document.createElement('option');
        option.value = dev.id;
        option.textContent = `${dev.name} [${dev.id}]`;
        if (dev.id === AppState.selectedDeviceId) {
            option.selected = true;
        }
        select.appendChild(option);
    });

    select.addEventListener('change', (e) => {
        AppState.selectedDeviceId = e.target.value;
        updateUI();
        showToast(`Cambiado a dispositivo: ${e.target.value}`, 'info');
    });
}

// Obtener dispositivo actualmente seleccionado
function getCurrentDevice() {
    return AppState.devices.find(d => d.id === AppState.selectedDeviceId) || AppState.devices[0];
}

// Guardar dispositivos en LocalStorage
function saveDevices() {
    localStorage.setItem('dispwatter_devices', JSON.stringify(AppState.devices));
}

// Actualizar toda la interfaz de usuario con los datos del dispositivo actual
function updateUI() {
    const dev = getCurrentDevice();
    if (!dev) return;

    // Calcular Porcentaje y Litros según la calibración geométrica
    const usableHeight = dev.bottomDist - dev.mirrorDist;
    const currentWaterHeight = dev.bottomDist - dev.currentDist;
    let percentage = 0;
    
    if (usableHeight > 0) {
        percentage = (currentWaterHeight / usableHeight) * 100;
        percentage = Math.max(0, Math.min(100, percentage));
    }

    const liters = ((dev.capacity * percentage) / 100).toFixed(1);

    // Métricas del tanque
    document.getElementById('waterPercentage').textContent = percentage.toFixed(1);
    document.getElementById('currentLiters').textContent = liters;
    document.getElementById('maxLiters').textContent = dev.capacity;
    document.getElementById('currentDistanceMm').textContent = `${dev.currentDist.toFixed(0)} mm`;
    document.getElementById('mirrorDistanceMm').textContent = `${dev.mirrorDist} mm`;
    document.getElementById('bottomDistanceMm').textContent = `${dev.bottomDist} mm`;

    // Animación de la altura del agua en el tanque
    document.getElementById('waterFill').style.height = `${percentage}%`;

    // Estado del Relé / Bomba
    const relayBadge = document.getElementById('relayStatusBadge');
    const pumpIcon = document.getElementById('pumpIcon');
    const relayModeText = document.getElementById('relayModeText');
    const relayActionDesc = document.getElementById('relayActionDesc');

    if (dev.relayState) {
        relayBadge.textContent = 'Bomba Activa';
        relayBadge.className = 'status-badge-lg on';
        pumpIcon.classList.add('active');
        relayActionDesc.textContent = 'Llenando tanque de bebedero...';
    } else {
        relayBadge.textContent = 'Bomba Inactiva';
        relayBadge.className = 'status-badge-lg off';
        pumpIcon.classList.remove('active');
        relayActionDesc.textContent = dev.autoRefill 
            ? `Se encenderá cuando el nivel baje de ${dev.minLevel}%.`
            : 'Modo manual activo (Llenado automático desactivado).';
    }

    relayModeText.textContent = dev.autoRefill ? 'Modo Automático' : 'Modo Manual';

    // Pantalla LCD
    document.getElementById('lcdLine0').textContent = dev.lcdLine0 || `Nivel: ${percentage.toFixed(0)}%  ${Math.round(liters)}L`;
    document.getElementById('lcdLine1').textContent = dev.lcdLine1 || (dev.relayState ? 'Bomba: ACTIVA' : 'Bomba: APAGADA');

    // Formulario de configuración
    document.getElementById('cfgCapacity').value = dev.capacity;
    document.getElementById('cfgBottomDist').value = dev.bottomDist;
    document.getElementById('cfgMirrorDist').value = dev.mirrorDist;
    document.getElementById('cfgMinLevel').value = dev.minLevel;
    document.getElementById('cfgMaxLevel').value = dev.maxLevel;
    document.getElementById('cfgAutoRefill').checked = dev.autoRefill;

    // Hardware Identity
    document.getElementById('infoDeviceId').value = dev.id;
    document.getElementById('infoDeviceHash').value = dev.hash || '---';
    document.getElementById('claimStatusText').textContent = dev.claimed ? '✓ Reclamado por ti' : '⚠ No Reclamado';
}

// Configuración de listeners
function initEventListeners() {
    // Modal Claim
    const modal = document.getElementById('claimModal');
    const btnOpen = document.getElementById('btnOpenClaimModal');
    const btnClose = document.getElementById('btnCloseClaimModal');
    const btnCancel = document.getElementById('btnCancelClaim');
    const claimForm = document.getElementById('claimDeviceForm');

    btnOpen.addEventListener('click', () => modal.style.display = 'flex');
    const closeModal = () => modal.style.display = 'none';
    btnClose.addEventListener('click', closeModal);
    btnCancel.addEventListener('click', closeModal);

    // Formulario de Claim (Tomar posesión)
    claimForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const id = document.getElementById('claimDeviceId').value.trim();
        const pass = document.getElementById('claimDevicePass').value;
        const name = document.getElementById('claimDeviceName').value.trim();

        if (!id || !pass) return;

        // Calcular hash SHA-256 del par ID + Pass
        const credHash = await sha256Hex(`${id}:${pass}`);

        // Verificar si ya existe o crearlo
        let existing = AppState.devices.find(d => d.id === id);
        if (existing) {
            existing.name = name;
            existing.hash = credHash;
            existing.claimed = true;
        } else {
            const newDevice = {
                id: id,
                name: name,
                hash: credHash,
                claimed: true,
                online: true,
                capacity: 50,
                bottomDist: 900,
                mirrorDist: 100,
                minLevel: 25,
                maxLevel: 90,
                autoRefill: true,
                currentDist: 500,
                relayState: false,
                lcdLine0: 'DispWatter OK',
                lcdLine1: 'Bebedero Listo'
            };
            AppState.devices.push(newDevice);
        }

        AppState.selectedDeviceId = id;
        saveDevices();
        initDeviceSelector();
        updateUI();
        closeModal();
        claimForm.reset();

        showToast(`¡Dispositivo ${id} vinculado exitosamente!`, 'success');

        // Notificar al backend si hay WebSocket
        sendWebSocketMessage({
            event: 'claim_device',
            device_id: id,
            device_hash: credHash
        });
    });

    // Guardar Configuración de Tanque
    document.getElementById('btnSaveConfig').addEventListener('click', (e) => {
        e.preventDefault();
        const dev = getCurrentDevice();
        if (!dev) return;

        dev.capacity = parseFloat(document.getElementById('cfgCapacity').value);
        dev.bottomDist = parseFloat(document.getElementById('cfgBottomDist').value);
        dev.mirrorDist = parseFloat(document.getElementById('cfgMirrorDist').value);
        dev.minLevel = parseFloat(document.getElementById('cfgMinLevel').value);
        dev.maxLevel = parseFloat(document.getElementById('cfgMaxLevel').value);
        dev.autoRefill = document.getElementById('cfgAutoRefill').checked;

        saveDevices();
        updateUI();
        showToast('Configuración del bebedero guardada correctamente', 'success');

        // Enviar parámetros al backend
        sendWebSocketMessage({
            event: 'update_config',
            device_id: dev.id,
            config: {
                capacity: dev.capacity,
                bottom_dist_mm: dev.bottomDist,
                mirror_dist_mm: dev.mirrorDist,
                min_level: dev.minLevel,
                max_level: dev.maxLevel,
                auto_refill: dev.autoRefill
            }
        });
    });

    // Control Manual de Relé
    document.getElementById('btnRelayOn').addEventListener('click', () => setRelay(true));
    document.getElementById('btnRelayOff').addEventListener('click', () => setRelay(false));

    // Envío de Texto a Pantalla LCD
    document.getElementById('btnSendLcd').addEventListener('click', () => {
        const line0 = document.getElementById('customLcd0').value;
        const line1 = document.getElementById('customLcd1').value;
        const dev = getCurrentDevice();
        if (dev) {
            dev.lcdLine0 = line0;
            dev.lcdLine1 = line1;
            updateUI();
            showToast('Mensaje enviado a pantalla LCD', 'info');

            sendWebSocketMessage({
                command: 'display',
                device_id: dev.id,
                line0: line0,
                line1: line1,
                clear: true
            });
        }
    });
}

// Acción de Relé
function setRelay(state) {
    const dev = getCurrentDevice();
    if (!dev) return;

    dev.relayState = state;
    updateUI();
    showToast(`Bomba ${state ? 'ENCENDIDA' : 'APAGADA'}`, state ? 'success' : 'info');

    sendWebSocketMessage({
        command: 'set_relay',
        device_id: dev.id,
        state: state
    });
}

// Conexión WebSocket al Backend
function connectWebSocket() {
    const wsUrl = `ws://${window.location.hostname || 'localhost'}:8765/ws/panel`;
    try {
        AppState.ws = new WebSocket(wsUrl);

        AppState.ws.onopen = () => {
            AppState.wsConnected = true;
            document.getElementById('connStatusBadge').textContent = 'Online';
            document.getElementById('connStatusBadge').className = 'status-badge online';
            showToast('Conectado al servidor WebSocket Backend', 'success');
        };

        AppState.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleServerMessage(data);
            } catch (e) {
                console.error('Error parseando JSON del servidor:', e);
            }
        };

        AppState.ws.onclose = () => {
            AppState.wsConnected = false;
            document.getElementById('connStatusBadge').textContent = 'Offline';
            document.getElementById('connStatusBadge').className = 'status-badge offline';
            // Reintento en 5s
            setTimeout(connectWebSocket, 5000);
        };
    } catch (e) {
        console.warn('Backend WebSocket no disponible aún, usando modo interactivo local.');
    }
}

function sendWebSocketMessage(msg) {
    if (AppState.ws && AppState.ws.readyState === WebSocket.OPEN) {
        AppState.ws.send(JSON.stringify(msg));
    }
}

// Procesar mensajes que vienen del Backend
function handleServerMessage(data) {
    if (data.event === 'telemetry') {
        const dev = AppState.devices.find(d => d.id === data.device_id);
        if (dev) {
            dev.currentDist = data.distance_mm;
            dev.relayState = data.relay_state;
            if (dev.id === AppState.selectedDeviceId) {
                updateUI();
            }
        }
    }
}

// Simulación interactiva local (para probar la interfaz y animaciones cuando el hardware no está transmitiendo)
function startSimulationLoop() {
    setInterval(() => {
        const dev = getCurrentDevice();
        if (!dev) return;

        // Si la bomba está encendida, el nivel sube (distancia al sensor se reduce)
        if (dev.relayState) {
            dev.currentDist = Math.max(dev.mirrorDist, dev.currentDist - 4);
            // Regla automática: corte al llegar a maxLevel
            const usableHeight = dev.bottomDist - dev.mirrorDist;
            const currentWaterHeight = dev.bottomDist - dev.currentDist;
            const pct = (currentWaterHeight / usableHeight) * 100;
            if (dev.autoRefill && pct >= dev.maxLevel) {
                dev.relayState = false;
                showToast(`Tanque lleno (${pct.toFixed(0)}%). Bomba apagada automáticamente.`, 'info');
            }
        } else {
            // El agua se consume gradualmente en el bebedero
            dev.currentDist = Math.min(dev.bottomDist, dev.currentDist + 0.3);
            const usableHeight = dev.bottomDist - dev.mirrorDist;
            const currentWaterHeight = dev.bottomDist - dev.currentDist;
            const pct = (currentWaterHeight / usableHeight) * 100;
            if (dev.autoRefill && pct <= dev.minLevel) {
                dev.relayState = true;
                showToast(`Nivel bajo (${pct.toFixed(0)}%). Bomba encendida automáticamente.`, 'info');
            }
        }
        updateUI();
    }, 1500);
}

// Utilidad para notificaciones Toast
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'error') icon = '❌';

    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(50px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}
