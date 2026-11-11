import { selectedDevice, state } from "./state.js";
import { socket, handleRequestError } from "./ws.js";
import {
  closeModal, confirmAction, el, openModal, signalLevel, toast,
} from "./ui.js";

function emptyNetworkList(message) {
  const list = el("networkList");
  if (!list) return;
  list.textContent = "";
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.textContent = message;
  list.appendChild(empty);
}

function networkItem(network, index, total, connected) {
  const item = document.createElement("div");
  item.className = `network-item${connected ? " connected" : ""}`;

  const rank = document.createElement("div");
  rank.className = "network-rank";
  rank.textContent = network.stored === false ? "·" : String(index);

  const main = document.createElement("div");
  main.className = "network-main";

  const ssid = document.createElement("div");
  ssid.className = "network-ssid";
  ssid.textContent = network.ssid;
  if (connected) {
    const badge = document.createElement("span");
    badge.className = "badge online";
    badge.style.marginLeft = "8px";
    badge.innerHTML = '<span class="dot"></span><span>Conectada</span>';
    ssid.appendChild(badge);
  }

  const meta = document.createElement("div");
  meta.className = "network-meta";

  const signal = document.createElement("span");
  signal.className = `signal s${signalLevel(network.rssi)}`;
  signal.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 4; i += 1) signal.appendChild(document.createElement("span"));

  const rssiText = document.createElement("span");
  rssiText.textContent = Number(network.rssi) ? `${network.rssi} dBm` : "sin señal";

  const passText = document.createElement("span");
  passText.textContent = network.has_password ? " · con contraseña" : " · red abierta";

  const visibleText = document.createElement("span");
  visibleText.textContent = network.stored === false ? " · visible, no guardada" : ` · prioridad ${index}`;

  meta.append(signal, rssiText, passText, visibleText);
  main.append(ssid, meta);

  const actions = document.createElement("div");
  actions.className = "network-actions";

  if (network.stored !== false) {
    const up = document.createElement("button");
    up.className = "icon-btn";
    up.type = "button";
    up.title = "Subir prioridad";
    up.setAttribute("aria-label", `Subir ${network.ssid}`);
    up.textContent = "↑";
    up.disabled = index <= 0;
    up.addEventListener("click", () => moveNetwork(network.ssid, index - 1));
    actions.appendChild(up);

    const down = document.createElement("button");
    down.className = "icon-btn";
    down.type = "button";
    down.title = "Bajar prioridad";
    down.setAttribute("aria-label", `Bajar ${network.ssid}`);
    down.textContent = "↓";
    down.disabled = index >= total - 1;
    down.addEventListener("click", () => moveNetwork(network.ssid, index + 1));
    actions.appendChild(down);

    const remove = document.createElement("button");
    remove.className = "icon-btn danger";
    remove.type = "button";
    remove.title = "Borrar red";
    remove.setAttribute("aria-label", `Borrar ${network.ssid}`);
    remove.textContent = "✕";
    remove.addEventListener("click", () => removeNetwork(network.ssid));
    actions.appendChild(remove);
  } else {
    const add = document.createElement("button");
    add.className = "btn btn-ghost btn-sm";
    add.type = "button";
    add.textContent = "Añadir";
    add.addEventListener("click", () => {
      el("wifiSsid").value = network.ssid;
      el("wifiPassword").focus();
      el("wifiAddForm").scrollIntoView({ behavior: "smooth", block: "center" });
    });
    actions.appendChild(add);
  }

  item.append(rank, main, actions);
  return item;
}

export function renderWifi() {
  const dev = selectedDevice();
  const list = el("networkList");
  if (!list) return;

  if (!dev) {
    emptyNetworkList("Selecciona un dispositivo para consultar sus redes.");
    return;
  }

  const networks = Array.isArray(dev.networks) ? dev.networks : [];
  if (!networks.length) {
    emptyNetworkList(
      dev.online
        ? "Sin redes guardadas en el dispositivo."
        : "El dispositivo está offline. Pulsa «Escanear / refrescar» cuando vuelva a estar online.",
    );
    return;
  }

  list.textContent = "";
  const stored = networks.filter((network) => network.stored !== false);
  for (const network of networks) {
    const index = network.stored === false
      ? -1
      : Math.max(0, Number(network.priority ?? stored.findIndex((item) => item.ssid === network.ssid)));
    list.appendChild(networkItem(network, index, stored.length, Boolean(network.connected)));
  }
}

export async function refreshWifi() {
  const dev = selectedDevice();
  if (!dev) return toast("Selecciona un dispositivo", "warn");
  if (!dev.online) return toast("El dispositivo está offline", "warn");

  try {
    const result = await socket.request({ event: "wifi_list", device_id: dev.id }, 15000);
    if (result.event === "wifi_list_result" && Array.isArray(result.networks)) {
      dev.networks = result.networks;
      renderWifi();
      toast(`Redes actualizadas (${result.networks.length})`, "success");
    } else {
      handleRequestError(result, "No se pudieron consultar las redes");
    }
  } catch (error) {
    toast(error.message, "error");
  }
}

async function moveNetwork(ssid, index) {
  const dev = selectedDevice();
  if (!dev) return;
  try {
    const result = await socket.request({
      event: "wifi_reorder",
      device_id: dev.id,
      ssid,
      index,
    });
    if (result.event === "ack" && result.ok) {
      toast(`Prioridad de ${ssid} actualizada`, "success");
      await refreshWifi();
    } else {
      handleRequestError(result, "No se pudo reordenar");
    }
  } catch (error) {
    toast(error.message, "error");
  }
}

async function removeNetwork(ssid) {
  const dev = selectedDevice();
  if (!dev) return;
  const ok = await confirmAction(
    "Borrar red WiFi",
    `Se eliminará «${ssid}» del dispositivo. Si es la red conectada, pasará a la siguiente.`,
    "Borrar red",
  );
  if (!ok) return;

  try {
    const result = await socket.request({
      event: "wifi_remove",
      device_id: dev.id,
      ssid,
    });
    if (result.event === "ack" && result.ok) {
      toast(`Red ${ssid} eliminada`, "success");
      await refreshWifi();
    } else {
      handleRequestError(result, "No se pudo borrar la red");
    }
  } catch (error) {
    toast(error.message, "error");
  }
}

async function addNetwork(event) {
  event.preventDefault();
  const dev = selectedDevice();
  if (!dev) return toast("Selecciona un dispositivo", "warn");

  const ssid = el("wifiSsid").value.trim();
  const password = el("wifiPassword").value;
  if (!ssid) return toast("El SSID es obligatorio", "warn");
  if (password && (password.length < 8 || password.length > 63)) {
    return toast("La contraseña debe tener entre 8 y 63 caracteres, o estar vacía", "warn");
  }
  if (!password) {
    const open = await confirmAction(
      "Red abierta",
      `«${ssid}» no tiene contraseña. ¿Confirmas que es una red abierta?`,
      "Sí, guardar",
      false,
    );
    if (!open) return;
  }

  try {
    const result = await socket.request({
      event: "wifi_add",
      device_id: dev.id,
      ssid,
      password,
    }, 15000);
    if (result.event === "ack" && result.ok) {
      toast(`Red ${ssid} añadida`, "success");
      el("wifiAddForm").reset();
      await refreshWifi();
    } else {
      handleRequestError(result, "No se pudo añadir la red");
    }
  } catch (error) {
    toast(error.message, "error");
  }
}

export function initWifi() {
  el("btnScanWifi")?.addEventListener("click", refreshWifi);
  el("wifiAddForm")?.addEventListener("submit", addNetwork);
}
