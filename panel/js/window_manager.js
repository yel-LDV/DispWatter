/* WindowManager — Gestor de ventanas flotantes */

import { state } from './state.js';
import { el } from './ui.js';

const APP_REGISTRY = {
  dashboard:      { icon: '◉', title: 'Dashboard',      width: 900, height: 600 },
  devices:        { icon: '⚙', title: 'Dispositivos',    width: 1000, height: 600 },
  device_detail:  { icon: '⚙', title: 'Detalle',         width: 500, height: 450 },
  history:        { icon: '📊', title: 'Historial',      width: 900, height: 500 },
  lcd:            { icon: '🖥', title: 'LCD',            width: 600, height: 400 },
  permissions:    { icon: '🔑', title: 'Permisos',       width: 600, height: 400 },
  audit:          { icon: '⌁', title: 'Auditoría',       width: 900, height: 500 },
  system:         { icon: '▤', title: 'Sistema',         width: 500, height: 400 },
  settings:       { icon: '⚙', title: 'Ajustes',         width: 600, height: 500 },
};

const MAX_WINDOWS = 10;
const MIN_WIDTH = 400;
const MIN_HEIGHT = 300;

/* Lazy-load app modules */
const appLoaders = {
  dashboard:      () => import('./apps/dashboard.js'),
  devices:        () => import('./apps/devices.js'),
  device_detail:  () => import('./apps/device_detail.js'),
  history:        () => import('./apps/history.js'),
  lcd:            () => import('./apps/lcd.js'),
  permissions:    () => import('./apps/permissions.js'),
  audit:          () => import('./apps/audit.js'),
  system:         () => import('./apps/system.js'),
  settings:       () => import('./apps/settings.js'),
};

class WindowManager {
  constructor() {
    this.windows = new Map();   // windowId → WindowState
    this.zCounter = 100;
    this.desktop = null;
    this._taskbar = null;       // set by app.js
  }

  /* ---- Public API ---- */

  /** Open a new window or bring existing one to front */
  open(appId, options = {}) {
    const info = APP_REGISTRY[appId];
    if (!info) {
      console.warn(`[WM] Unknown app: ${appId}`);
      return null;
    }

    // Single instance check
    if (options.singleInstance !== false) {
      for (const [id, w] of this.windows) {
        if (w.appId === appId) {
          this.restore(id);
          this.bringToFront(id);
          return w;
        }
      }
    }

    // Limit max windows
    if (this.windows.size >= MAX_WINDOWS) {
      // Close oldest minimized window
      for (const [id, w] of this.windows) {
        if (w.minimized) {
          this.close(id);
          break;
        }
      }
      if (this.windows.size >= MAX_WINDOWS) {
        // Close oldest
        const oldest = this.windows.keys().next().value;
        this.close(oldest);
      }
    }

    const windowId = `win-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const offset = this.windows.size * 30;
    const w = {
      id: windowId,
      appId,
      title: info.title,
      icon: info.icon,
      x: options.x ?? Math.max(50, (window.innerWidth - info.width) / 2 + offset),
      y: options.y ?? Math.max(50, (window.innerHeight - 48 - info.height) / 2 + offset),
      width: options.width ?? info.width,
      height: options.height ?? info.height,
      minimized: false,
      maximized: false,
      zIndex: ++this.zCounter,
      _preMax: null,
      _loaded: false,
    };

    this.windows.set(windowId, w);
    this._renderWindow(w);
    this._notifyTaskbar();
    return w;
  }

  /** Close window and discard its state */
  close(windowId) {
    const w = this.windows.get(windowId);
    if (!w) return;

    // Remove DOM
    const dom = document.getElementById(windowId);
    if (dom) dom.remove();

    this.windows.delete(windowId);
    this._notifyTaskbar();
  }

  /** Minimize window */
  minimize(windowId) {
    const w = this.windows.get(windowId);
    if (!w) return;
    w.minimized = true;
    const dom = document.getElementById(windowId);
    if (dom) dom.classList.add('window-minimized');
    this._notifyTaskbar();
  }

  /** Restore minimized window */
  restore(windowId) {
    const w = this.windows.get(windowId);
    if (!w) return;
    w.minimized = false;
    const dom = document.getElementById(windowId);
    if (dom) dom.classList.remove('window-minimized');
    this.bringToFront(windowId);
    this._notifyTaskbar();
  }

  /** Maximize / restore window */
  maximize(windowId) {
    const w = this.windows.get(windowId);
    if (!w) return;

    if (!w.maximized) {
      w._preMax = { x: w.x, y: w.y, width: w.width, height: w.height };
      w.x = 0;
      w.y = 0;
      w.width = window.innerWidth;
      w.height = window.innerHeight - 48; // taskbar
      w.maximized = true;
    } else {
      Object.assign(w, w._preMax);
      w.maximized = false;
    }

    const dom = document.getElementById(windowId);
    if (dom) {
      dom.classList.toggle('window-maximized', w.maximized);
      this._applyPosition(windowId);
    }
  }

  /** Bring window to front */
  bringToFront(windowId) {
    const w = this.windows.get(windowId);
    if (!w) return;
    w.zIndex = ++this.zCounter;
    const dom = document.getElementById(windowId);
    if (dom) {
      dom.style.zIndex = w.zIndex;
      dom.classList.add('active');
    }
    // Deactivate others
    for (const [, other] of this.windows) {
      if (other.id !== windowId) {
        const d = document.getElementById(other.id);
        if (d) d.classList.remove('active');
      }
    }
  }

  /** Get window state by ID */
  get(windowId) {
    return this.windows.get(windowId);
  }

  /** Get all window IDs */
  getIds() {
    return Array.from(this.windows.keys());
  }

  /** Get window by appId */
  getByApp(appId) {
    for (const w of this.windows.values()) {
      if (w.appId === appId) return w;
    }
    return null;
  }

  /* ---- Internal ---- */

  _renderWindow(w) {
    const desktop = el('desktopArea');
    if (!desktop) return;

    const win = document.createElement('div');
    win.id = w.id;
    win.className = 'window';
    win.style.width = w.width + 'px';
    win.style.height = w.height + 'px';
    win.style.left = w.x + 'px';
    win.style.top = w.y + 'px';
    win.style.zIndex = w.zIndex;

    win.innerHTML = `
      <div class="window-titlebar">
        <span class="window-titlebar-icon">${w.icon}</span>
        <span class="window-titlebar-title">${w.title}</span>
        <div class="window-controls">
          <button class="window-control-btn minimize" title="Minimizar">—</button>
          <button class="window-control-btn maximize" title="Maximizar">□</button>
          <button class="window-control-btn close" title="Cerrar">✕</button>
        </div>
      </div>
      <div class="window-content" id="content-${w.id}"></div>
      <div class="window-resize-handle"></div>
    `;

    desktop.appendChild(win);

    // Controls
    win.querySelector('.minimize').addEventListener('click', (e) => {
      e.stopPropagation();
      this.minimize(w.id);
    });
    win.querySelector('.maximize').addEventListener('click', (e) => {
      e.stopPropagation();
      this.maximize(w.id);
    });
    win.querySelector('.close').addEventListener('click', (e) => {
      e.stopPropagation();
      this.close(w.id);
    });

    // Double-click titlebar to maximize
    win.querySelector('.window-titlebar').addEventListener('dblclick', () => {
      this.maximize(w.id);
    });

    // Click to bring to front
    win.addEventListener('mousedown', () => {
      this.bringToFront(w.id);
    });

    // Drag
    this._setupDrag(w.id);

    // Resize
    this._setupResize(w.id);

    // Load app content
    this._loadApp(w);

    this.bringToFront(w.id);
  }

  async _loadApp(w) {
    const contentEl = el(`content-${w.id}`);
    if (!contentEl) return;

    try {
      const loader = appLoaders[w.appId];
      if (!loader) return;
      const mod = await loader();
      if (mod.render) {
        // Pass additional data from window state to the app's render function
        // e.g., _deviceId for device_detail windows
        const appData = w._deviceId ?? state.selectedId;
        mod.render(contentEl, appData);
      }
      w._loaded = true;
    } catch (err) {
      console.error(`[WM] Failed to load app ${w.appId}:`, err);
      contentEl.innerHTML = `<p class="empty-state">Error cargando ${w.title}</p>`;
    }
  }

  _applyPosition(windowId) {
    const w = this.windows.get(windowId);
    if (!w) return;
    const dom = document.getElementById(windowId);
    if (!dom) return;
    dom.style.left = w.x + 'px';
    dom.style.top = w.y + 'px';
    dom.style.width = w.width + 'px';
    dom.style.height = w.height + 'px';
  }

  _setupDrag(windowId) {
    const dom = document.getElementById(windowId);
    if (!dom) return;
    const titlebar = dom.querySelector('.window-titlebar');

    let startX, startY, origX, origY;

    titlebar.addEventListener('mousedown', (e) => {
      const w = this.windows.get(windowId);
      if (!w || w.maximized) return;
      if (e.target.closest('.window-controls')) return;

      startX = e.clientX;
      startY = e.clientY;
      origX = w.x;
      origY = w.y;

      const onMove = (ev) => {
        w.x = origX + (ev.clientX - startX);
        w.y = Math.max(0, origY + (ev.clientY - startY));
        dom.style.left = w.x + 'px';
        dom.style.top = w.y + 'px';
      };

      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  }

  _setupResize(windowId) {
    const dom = document.getElementById(windowId);
    if (!dom) return;
    const handle = dom.querySelector('.window-resize-handle');

    handle.addEventListener('mousedown', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const w = this.windows.get(windowId);
      if (!w || w.maximized) return;

      const startX = e.clientX;
      const startY = e.clientY;
      const origW = w.width;
      const origH = w.height;

      const onMove = (ev) => {
        const newW = Math.max(MIN_WIDTH, origW + (ev.clientX - startX));
        const newH = Math.max(MIN_HEIGHT, origH + (ev.clientY - startY));
        w.width = newW;
        w.height = newH;
        dom.style.width = newW + 'px';
        dom.style.height = newH + 'px';
      };

      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  }

  _notifyTaskbar() {
    if (this._taskbar && this._taskbar.update) {
      this._taskbar.update();
    }
  }
}

export const windowManager = new WindowManager();
