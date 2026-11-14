/* NotificationCenter — Campana de notificaciones y sidebar derecho */

import { state } from './state.js';
import { socket, on, off } from './ws.js';
import { el, toast } from './ui.js';
import { showModal } from './modal_dialog.js';

let _sidebarOpen = false;
let _notifications = []; // { id, type, title, message, device_id, read, timestamp }
let _onClose = null;

// Max age for notifications: 24 hours (86400000 ms)
const MAX_NOTIF_AGE_MS = 24 * 60 * 60 * 1000;

// Types: 'new_device' (dispositivo pendiente de vinculación)

function generateId() {
  return `notif-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

function getUnreadCount() {
  return _notifications.filter(n => !n.read).length;
}

function addNotification(type, title, message, device_id) {
  const notif = {
    id: generateId(),
    type,
    title,
    message,
    device_id: device_id || null,
    read: false,
    timestamp: Date.now(),
  };
  _notifications.unshift(notif);
  updateBellBadge();
  if (_sidebarOpen) renderSidebar();
  return notif;
}

function markAsRead(id) {
  const notif = _notifications.find(n => n.id === id);
  if (notif) {
    notif.read = true;
    updateBellBadge();
  }
}

function updateBellBadge() {
  const badge = document.querySelector('.notif-bell-badge');
  const count = getUnreadCount();
  if (badge) {
    badge.textContent = count;
    badge.style.display = count > 0 ? 'flex' : 'none';
  }
}

function clearOldNotifications() {
  const now = Date.now();
  _notifications = _notifications.filter(n => (now - n.timestamp) < MAX_NOTIF_AGE_MS);
  updateBellBadge();
}

function markAllAsRead() {
  _notifications.forEach(n => n.read = true);
  updateBellBadge();
}

function createSidebar() {
  // Create overlay
  const overlay = document.createElement('div');
  overlay.id = 'notifOverlay';
  overlay.className = 'notif-overlay';
  overlay.innerHTML = `
    <div class="notif-sidebar">
      <div class="notif-header">
        <h3>🔔 Notificaciones</h3>
        <button class="notif-close-btn" id="notifCloseBtn" title="Cerrar">✕</button>
      </div>
      <div class="notif-list" id="notifList"></div>
    </div>
  `;
  document.getElementById('desktop')?.appendChild(overlay);

  // Close button
  el('notifCloseBtn')?.addEventListener('click', closeSidebar);

  // Click outside to close
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeSidebar();
  });
}

function formatNotifDateTime(timestamp) {
  const d = new Date(timestamp);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  const time = d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
  if (isToday) {
    return `Hoy ${time}`;
  }
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) {
    return `Ayer ${time}`;
  }
  const date = d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' });
  return `${date} ${time}`;
}

function renderSidebar() {
  const list = el('notifList');
  if (!list) return;

  if (_notifications.length === 0) {
    list.innerHTML = `
      <div class="notif-empty">
        <span class="notif-empty-icon">🔔</span>
        <p>No hay notificaciones</p>
      </div>
    `;
    return;
  }

  list.innerHTML = _notifications.map(n => {
    const isUnread = !n.read;
    const dateTime = formatNotifDateTime(n.timestamp);
    if (n.type === 'new_device') {
      return `
        <div class="notif-item ${isUnread ? 'notif-unread' : ''}" data-id="${n.id}">
          <div class="notif-item-header">
            <span class="notif-item-icon">📡</span>
            <span class="notif-item-title">${n.title}</span>
            <span class="notif-item-time">${dateTime}</span>
            ${isUnread ? '<span class="notif-dot"></span>' : ''}
          </div>
          <div class="notif-item-body">
            <p>${n.message}</p>
            <p class="notif-device-id">ID: <strong>${n.device_id || '—'}</strong></p>
          </div>
          <div class="notif-item-actions">
            <button class="btn btn-sm btn-primary notif-claim-btn" data-device-id="${n.device_id}">Vincular dispositivo</button>
          </div>
        </div>
      `;
    }
    return `
      <div class="notif-item ${isUnread ? 'notif-unread' : ''}" data-id="${n.id}">
        <div class="notif-item-header">
          <span class="notif-item-title">${n.title}</span>
          <span class="notif-item-time">${dateTime}</span>
          ${isUnread ? '<span class="notif-dot"></span>' : ''}
        </div>
        <div class="notif-item-body">
          <p>${n.message}</p>
        </div>
      </div>
    `;
  }).join('');

  // Bind claim buttons
  list.querySelectorAll('.notif-claim-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const deviceId = btn.dataset.deviceId;
      markAsRead(btn.closest('.notif-item').dataset.id);
      openClaimDialog(deviceId);
    });
  });

  // Click to mark as read
  list.querySelectorAll('.notif-item').forEach(item => {
    item.addEventListener('click', (e) => {
      if (e.target.closest('.notif-claim-btn')) return;
      markAsRead(item.dataset.id);
    });
  });
}

async function openClaimDialog(deviceId) {
  // Step 1: Ask for token
  const tokenResult = await showModal(
    '📡 Vincular dispositivo',
    `<p>El dispositivo <strong>${deviceId}</strong> solicita vinculación.</p>
     <p>Introduce el <strong>token</strong> del dispositivo (claim_secret del config.json):</p>
     <div class="modal-input-wrap">
       <input type="text" id="claimTokenInput" class="modal-input" placeholder="Token del dispositivo" autocomplete="off">
     </div>`,
    {
      confirmText: 'Siguiente',
      cancelText: 'Cancelar',
      async onConfirm() {
        const token = document.getElementById('claimTokenInput')?.value?.trim();
        if (!token) {
          toast('El token es requerido', 'error');
          return false; // prevent close
        }
        return token;
      }
    }
  );

  if (!tokenResult?.confirmed || !tokenResult?.result) return;
  const token = tokenResult.result;

  // Step 2: Send token to backend to generate claim code
  try {
    const claimResp = await socket.request({
      event: 'start_claim_by_token',
      token: token,
    }, 10000);

    if (!claimResp?.ok && claimResp?.event !== 'claim_code_sent') {
      toast(claimResp?.message || 'Error al enviar el token', 'error');
      return;
    }

    const actualDeviceId = claimResp.device_id || deviceId;

    // Step 3: Ask for the 6-digit code shown on the LCD
    const codeResult = await showModal(
      '📡 Código de vinculación',
      `<p>El dispositivo <strong>${actualDeviceId}</strong> muestra un código de 6 dígitos en la pantalla LCD.</p>
       <p>Introduce el código:</p>
       <div class="modal-input-wrap">
         <input type="text" id="claimCodeInput" class="modal-input" placeholder="Código de 6 dígitos" maxlength="6" autocomplete="off" inputmode="numeric">
       </div>`,
      {
        confirmText: 'Vincular',
        cancelText: 'Cancelar',
        async onConfirm() {
          const code = document.getElementById('claimCodeInput')?.value?.trim();
          if (!code || code.length < 4) {
            toast('El código debe tener al menos 4 dígitos', 'error');
            return false;
          }
          return code;
        }
      }
    );

    if (!codeResult?.confirmed || !codeResult?.result) return;
    const code = codeResult.result;

    // Step 4: Verify claim code
    const verifyResp = await socket.request({
      event: 'verify_claim',
      device_id: actualDeviceId,
      code: code,
    }, 10000);

    if (verifyResp?.ok || verifyResp?.event === 'claim_verified') {
      toast('Dispositivo vinculado correctamente', 'success');
      closeSidebar();
    } else {
      toast(verifyResp?.message || 'Código incorrecto', 'error');
    }
  } catch (err) {
    toast('Error de conexión al intentar vincular', 'error');
  }
}

function openSidebar() {
  // Clear old notifications and mark all as read
  clearOldNotifications();
  markAllAsRead();
  
  let overlay = el('notifOverlay');
  if (!overlay) {
    createSidebar();
    overlay = el('notifOverlay');
  }
  overlay.classList.add('notif-open');
  _sidebarOpen = true;
  renderSidebar();
}

function closeSidebar() {
  const overlay = el('notifOverlay');
  if (overlay) {
    overlay.classList.remove('notif-open');
  }
  _sidebarOpen = false;
}

function toggleSidebar() {
  if (_sidebarOpen) {
    closeSidebar();
  } else {
    openSidebar();
  }
}

// Listen for new device notifications from backend
function initListeners() {
  on('device_status', (data) => {
    // A new device connected with pending_claim
    if (data.pending_claim && !data.claimed) {
      const deviceId = data.device_id;
      // Check if we already have a notification for this device
      const existing = _notifications.find(n => n.device_id === deviceId && n.type === 'new_device' && !n.read);
      if (!existing) {
        addNotification(
          'new_device',
          'Nuevo dispositivo detectado',
          'Un dispositivo solicita vinculación al sistema.',
          deviceId
        );
      }
    }
  });

  // When a device is claimed, mark the notification as read
  on('device_status', (data) => {
    if (data.claimed && data.device_id) {
      const notif = _notifications.find(n => n.device_id === data.device_id && n.type === 'new_device');
      if (notif) {
        notif.read = true;
        notif.message = 'Dispositivo vinculado correctamente.';
        updateBellBadge();
        if (_sidebarOpen) renderSidebar();
      }
    }
  });

  // On sync_all, check for PENDING_CLAIM devices
  on('sync_all', (data) => {
    const devices = data.all_devices || data.devices || [];
    devices.forEach(dev => {
      if (dev.status === 'PENDING_CLAIM') {
        const existing = _notifications.find(n => n.device_id === dev.id && n.type === 'new_device');
        if (!existing) {
          addNotification(
            'new_device',
            'Dispositivo pendiente de vinculación',
            'Este dispositivo espera ser vinculado al sistema.',
            dev.id
          );
        }
      }
    });
  });
}

// Create the fixed bell button in the desktop (absolute, top-right)
function createBellButton() {
  const bell = document.createElement('button');
  bell.id = 'notifBellBtn';
  bell.className = 'notif-bell-btn';
  bell.title = 'Notificaciones';
  bell.innerHTML = `
    🔔
    <span class="notif-bell-badge" style="display:none;">0</span>
  `;
  bell.addEventListener('click', toggleSidebar);
  document.getElementById('desktop')?.appendChild(bell);
}

export {
  addNotification,
  openSidebar,
  closeSidebar,
  toggleSidebar,
  getUnreadCount,
  updateBellBadge,
  createBellButton,
  initListeners,
};
