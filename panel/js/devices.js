import { selectedDevice, setSelectedDevice, state } from "./state.js";
import { socket, handleRequestError } from "./ws.js";
import {
  confirmAction, el, formatRssi, formatUptime, openModal, closeModal, setText, signalLevel, toast,
} from "./ui.js";

function deviceBadge(dev) {
  const badge = el("deviceClaimBadge");
  if (!badge) return;
  badge.className = "badge";
  const dot = badge.querySelector(".dot");
  const text = badge.querySelector("span:last-child");
  if (!dev) {
    badge.classList.add("offline");
    text.textContent = "Sin datos";
    return;
  }
  if (!dev.claimed) {
    badge.classList.add("pending");
    text.textContent = "Pendiente de vincular";
    return;
  }
  if (dev.online) {
    badge.classList.add("online");
    text.textContent = "Online";
  } else {
    badge.classList.add("offline");
    text.textContent = "Offline";
  }
  if (dot) dot.setAttribute("aria-hidden", "true");
}

export function renderDeviceSelect() {
  const select = el("deviceSelect");
  if (!select) return;
  select.textContent = "";

  if (!state.devices.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Sin dispositivos";
    select.appendChild(option);
    select.disabled = true;
    return;
  }

  select.disabled = false;
  for (const device of state.devices) {
    const option = document.createElement("option");
    option.value = device.id;
    option.textContent = `${device.name} · ${device.id}`;
    select.appendChild(option);
  }

  if (!state.devices.some((device) => device.id === state.selectedId)) {
    setSelectedDevice(state.devices[0].id);
  }
  select.value = state.selectedId;
}

export function renderDashboard(fillForm = false) {
  const dev = selectedDevice();
  deviceBadge(dev);

  if (!dev) {
    ["waterPercent", "waterLiters", "currentDist"].forEach((id) => setText(id, "—"));
    setText("relayValue", "—");
    setText("tankPercent", "—%");
    setText("infoOnline", "—");
    setText("infoRssi", "—");
    setText("infoIp", "—");
    setText("infoUptime", "—");
    setText("infoFirmware", "—");
    setText("infoWake", "—");
    setText("infoLocation", "—");
    const fill = el("tankFill");
    if (fill) fill.style.height = "0%";
    return;
  }

  const percent = Number(dev.waterPercent);
  const hasPercent = Number.isFinite(percent);
  setText("waterPercent", hasPercent ? percent.toFixed(0) : "—");
  setText("waterLiters", Number.isFinite(Number(dev.waterLiters)) ? Number(dev.waterLiters).toFixed(1) : "—");
  setText("currentDist", Number.isFinite(Number(dev.currentDist)) ? Number(dev.currentDist).toFixed(0) : "—");
  setText("relayValue", dev.relayState ? "ON" : "OFF");
  setText("tankPercent", hasPercent ? `${percent.toFixed(0)}%` : "—%");

  const fill = el("tankFill");
  if (fill) {
    const level = hasPercent ? Math.max(0, Math.min(100, percent)) : 0;
    fill.style.height = `${level}%`;
    if (level < 15) {
      fill.style.background = "linear-gradient(180deg, rgba(255,59,92,0.95), rgba(255,43,214,0.85))";
    } else if (level < 30) {
      fill.style.background = "linear-gradient(180deg, rgba(255,179,0,0.95), rgba(255,120,0,0.85))";
    } else {
      fill.style.background = "linear-gradient(180deg, rgba(0,229,255,0.92), rgba(45,123,255,0.92))";
    }
  }

  setText("infoOnline", dev.online ? "Online" : "Offline");
  setText("infoRssi", formatRssi(dev.rssi));
  setText("infoIp", dev.ip || "—");
  setText("infoUptime", dev.uptime_s ? formatUptime(dev.uptime_s) : "—");
  setText("infoFirmware", dev.firmware_version ? `v${dev.firmware_version}` : "—");
  setText("infoWake", dev.wake_reason || "—");
  setText("infoLocation", dev.location || "—");

  if (fillForm) fillTankForm(dev);
}

export function fillTankForm(dev) {
  if (!dev) return;
  el("cfgCapacity").value = dev.capacity ?? 50;
  el("cfgBottomDist").value = dev.bottomDist ?? 900;
  el("cfgMirrorDist").value = dev.mirrorDist ?? 100;
  el("cfgMinLevel").value = dev.minLevel ?? 25;
  el("cfgMaxLevel").value = dev.maxLevel ?? 90;
  el("cfgAutoRefill").checked = Boolean(dev.autoRefill);
}

export function updateTelemetry(message) {
  const dev = state.devices.find((item) => item.id === message.device_id);
  if (!dev) return;
  dev.currentDist = message.distance_mm;
  dev.waterPercent = message.water_percent;
  dev.waterLiters = message.water_liters;
  dev.relayState = message.relay_state;
  if (message.device_id === state.selectedId) renderDashboard(false);
}

export function updateDeviceStatus(message) {
  const dev = state.devices.find((item) => item.id === message.device_id);
  if (!dev) return;
  if (typeof message.is_online === "boolean") dev.online = message.is_online;
  if (message.claimed !== undefined) dev.claimed = message.claimed;
  if (message.rssi !== undefined) dev.rssi = message.rssi;
  if (message.ip !== undefined) dev.ip = message.ip;
  if (message.uptime_s !== undefined) dev.uptime_s = message.uptime_s;
  if (message.firmware !== undefined) dev.firmware_version = message.firmware;
  if (message.wake_reason !== undefined) dev.wake_reason = message.wake_reason;
  if (message.device_id === state.selectedId) renderDashboard(false);
}

async function relayCommand(stateValue) {
  const dev = selectedDevice();
  if (!dev) return toast("Selecciona un dispositivo", "warn");
  if (!dev.claimed) return toast("El dispositivo debe vincularse primero", "warn");

  const ok = await confirmAction(
    stateValue ? "Encender bomba" : "Apagar bomba",
    stateValue
      ? "Se enviará la orden de encender el relé. El fail-safe lo apagará si se supera el tiempo máximo."
      : "Se enviará la orden de apagar el relé.",
    stateValue ? "Encender" : "Apagar",
    !stateValue,
  );
  if (!ok) return;

  try {
    const result = await socket.request({
      command: "set_relay",
      device_id: dev.id,
      state: stateValue,
    });
    if (result.event === "ack" && result.ok) {
      toast(stateValue ? "Bomba encendida" : "Bomba apagada", "success");
      dev.relayState = stateValue;
      renderDashboard(false);
    } else {
      handleRequestError(result, "No se pudo controlar el relé");
    }
  } catch (error) {
    toast(error.message, "error");
  }
}

export function openClaimModal() {
  const dev = selectedDevice();

  const form = document.createElement("form");
  form.className = "form-grid";
  form.id = "claimDeviceForm";

  const fields = [
    { id: "claimDeviceId", label: "ID del dispositivo", value: dev?.id || "", type: "text", required: true },
    { id: "claimDeviceName", label: "Nombre visible", value: dev?.name || "", type: "text", required: false },
    { id: "claimDevicePass", label: "Secreto del dispositivo", value: "", type: "password", required: true },
  ];

  for (const field of fields) {
    const wrapper = document.createElement("div");
    wrapper.className = "field";
    if (field.id === "claimDevicePass") wrapper.style.gridColumn = "1 / -1";
    const label = document.createElement("label");
    label.htmlFor = field.id;
    label.textContent = field.label;
    const input = document.createElement("input");
    input.id = field.id;
    input.type = field.type;
    input.value = field.value;
    input.required = field.required;
    input.autocomplete = field.type === "password" ? "new-password" : "off";
    if (field.type === "password") input.minLength = 16;
    wrapper.append(label, input);
    form.appendChild(wrapper);
  }

  const hint = document.createElement("p");
  hint.className = "field-hint";
  hint.style.gridColumn = "1 / -1";
  hint.textContent = "El dispositivo debe estar online. El backend le enviará un challenge y verificará el secreto sin guardarlo en el navegador.";
  form.appendChild(hint);

  const submit = document.createElement("button");
  submit.type = "submit";
  submit.className = "btn btn-primary";
  submit.textContent = "Verificar y vincular";
  submit.style.gridColumn = "1 / -1";
  form.appendChild(submit);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    submit.textContent = "Verificando…";
    try {
      const result = await socket.request({
        event: "claim_device",
        device_id: el("claimDeviceId").value.trim(),
        name: el("claimDeviceName").value.trim(),
        password: el("claimDevicePass").value,
      }, 20000);

      if (result.event === "claim_result" && result.status === "success") {
        toast("Dispositivo vinculado correctamente", "success");
        closeModal();
      } else {
        handleRequestError(result, "No se pudo vincular el dispositivo");
      }
    } catch (error) {
      toast(error.message, "error");
    } finally {
      submit.disabled = false;
      submit.textContent = "Verificar y vincular";
    }
  });

  openModal("Vincular dispositivo", form, [
    { label: "Cancelar", className: "btn-ghost", onClick: closeModal },
  ]);
}

async function saveTankConfig(event) {
  event.preventDefault();
  const dev = selectedDevice();
  if (!dev) return toast("Selecciona un dispositivo", "warn");

  const payload = {
    event: "update_config",
    device_id: dev.id,
    config: {
      capacity: Number(el("cfgCapacity").value),
      bottom_dist_mm: Number(el("cfgBottomDist").value),
      mirror_dist_mm: Number(el("cfgMirrorDist").value),
      min_level: Number(el("cfgMinLevel").value),
      max_level: Number(el("cfgMaxLevel").value),
      auto_refill: el("cfgAutoRefill").checked,
    },
  };

  try {
    const result = await socket.request(payload);
    if (result.event === "ack" && result.ok) {
      toast("Configuración guardada", "success");
    } else {
      handleRequestError(result, "No se pudo guardar");
    }
  } catch (error) {
    toast(error.message, "error");
  }
}

export function initDevices() {
  el("deviceSelect")?.addEventListener("change", (event) => {
    setSelectedDevice(event.target.value);
    renderDashboard(true);
    window.dispatchEvent(new CustomEvent("device-changed"));
  });

  el("btnRelayOn")?.addEventListener("click", () => relayCommand(true));
  el("btnRelayOff")?.addEventListener("click", () => relayCommand(false));
  el("btnOpenClaimModal")?.addEventListener("click", openClaimModal);
  el("tankConfigForm")?.addEventListener("submit", saveTankConfig);
}
