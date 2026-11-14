import { state } from "./state.js";
import { toast } from "./ui.js";

const listeners = new Map();
const pending = new Map();

const TERMINAL_EVENTS = new Set([
  "ack", "error", "claim_result", "wifi_list_result",
  "system_result", "audit_result",
  "claim_code_sent", "claim_verified",
  "update_device_config_result",
]);

export function backendEndpoint() {
  const params = new URLSearchParams(window.location.search);
  const override = params.get("backend");
  if (override) {
    localStorage.setItem("dispwatter_backend", override);
    return override;
  }
  return localStorage.getItem("dispwatter_backend")
    || `${window.location.hostname || "localhost"}:8765`;
}

export function wsUrl() {
  const endpoint = backendEndpoint();
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${endpoint}/ws/panel`;
}

export function on(event, handler) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(handler);
  return () => off(event, handler);
}

export function off(event, handler) {
  listeners.get(event)?.delete(handler);
}

function emit(event, data) {
  const handlers = listeners.get(event);
  if (!handlers) return;
  for (const handler of [...handlers]) {
    try {
      handler(data);
    } catch (error) {
      console.error(`Error en handler ${event}`, error);
    }
  }
}

function settleRequest(data) {
  if (!data || !data.request_id) return;
  const entry = pending.get(data.request_id);
  if (!entry) return;
  const isTerminal = TERMINAL_EVENTS.has(data.event) || data.event.endsWith("_result");
  if (!isTerminal) return;
  pending.delete(data.request_id);
  window.clearTimeout(entry.timer);
  entry.resolve(data);
}

function newRequestId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  if (window.crypto && typeof window.crypto.getRandomValues === "function") {
    window.crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i += 1) {
      bytes[i] = Math.floor(Math.random() * 256);
    }
  }
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export class PanelSocket {
  constructor() {
    this.ws = null;
    this.opening = null;
    this.closedByUser = false;
    this.reconnectTimer = null;
    this.retryDelay = 3000;
  }

  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }
    if (this.opening) return this.opening;

    this.opening = new Promise((resolve, reject) => {
      let settled = false;
      const socket = new WebSocket(wsUrl());
      this.ws = socket;

      socket.addEventListener("open", () => {
        settled = true;
        state.connected = true;
        this.opening = null;
        this.retryDelay = 3000;
        emit("open");
        resolve();
      });

      socket.addEventListener("message", (event) => {
        let data;
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
        if (!data || typeof data !== "object") return;
        emit(data.event || "message", data);
        settleRequest(data);
      });

      socket.addEventListener("close", () => {
        state.connected = false;
        this.ws = null;
        if (!settled) {
          this.opening = null;
          reject(new Error("No se pudo conectar con el backend"));
        }
        for (const [id, entry] of pending) {
          window.clearTimeout(entry.timer);
          entry.reject(new Error("Conexión cerrada"));
          pending.delete(id);
        }
        emit("close");
        if (!this.closedByUser) this.scheduleReconnect();
      });

      socket.addEventListener("error", () => {
        if (!settled) {
          this.opening = null;
          reject(new Error("Error de conexión WebSocket"));
        }
      });
    });

    return this.opening;
  }

  scheduleReconnect() {
    if (this.reconnectTimer) return;
    this.reconnectTimer = window.setTimeout(async () => {
      this.reconnectTimer = null;
      try {
        await this.connect();
      } catch {
        this.retryDelay = Math.min(this.retryDelay * 1.5, 15000);
        this.scheduleReconnect();
      }
    }, this.retryDelay);
  }

  disconnect() {
    this.closedByUser = true;
    if (this.reconnectTimer) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) this.ws.close(1000, "logout");
    this.ws = null;
    state.connected = false;
  }

  send(payload) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error("Sin conexión con el backend");
    }
    this.ws.send(JSON.stringify(payload));
  }

  request(payload, timeout = 12000) {
    const requestId = payload.request_id || newRequestId();
    const message = { ...payload, request_id: requestId };
    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => {
        pending.delete(requestId);
        reject(new Error("Tiempo de espera agotado"));
      }, timeout);
      pending.set(requestId, { resolve, reject, timer });
      try {
        this.send(message);
      } catch (error) {
        window.clearTimeout(timer);
        pending.delete(requestId);
        reject(error);
      }
    });
  }

  async login(username, password) {
    await this.connect();
    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => {
        off();
        reject(new Error("Tiempo de espera agotado al iniciar sesión"));
      }, 10000);
      const off = on("login_result", (data) => {
        window.clearTimeout(timer);
        off();
        resolve(data);
      });
      this.send({ event: "login", username, password });
    });
  }

  async resume(token) {
    await this.connect();
    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => {
        off();
        reject(new Error("Tiempo de espera agotado al recuperar sesión"));
      }, 10000);
      const off = on("resume_result", (data) => {
        window.clearTimeout(timer);
        off();
        resolve(data);
      });
      this.send({ event: "resume", token });
    });
  }
}

export const socket = new PanelSocket();

export function handleRequestError(response, fallback = "Operación fallida") {
  if (!response) {
    toast(fallback, "error");
    return;
  }
  toast(response.message || response.error || fallback, "error");
}
