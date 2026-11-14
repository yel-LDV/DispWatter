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
    setText("infoWaterHeight", "—");
    ["calibLive", "calibHeight", "calibPercent", "calibLiters"].forEach((id) => setText(id, "—"));
    const fill = el("tankFill");
    if (fill) fill.style.height = "0%";
    renderControls(null);
    return;
  }

  const percent = Number(dev.waterPercent);
  const hasPercent = Number.isFinite(percent);
  setText("waterPercent", hasPercent ? percent.toFixed(0) : "—");
  setText("waterLiters", Number.isFinite(Number(dev.waterLiters)) ? Number(dev.waterLiters).toFixed(1) : "—");
  setText("currentDist", Number.isFinite(Number(dev.currentDist)) ? Number(dev.currentDist).toFixed(0) : "—");
  setText("tankPercent", hasPercent ? `${percent.toFixed(0)}%` : "—%");

  const heightMm = Number(dev.waterHeightMm);
  const hasHeight = dev.waterHeightMm !== null && dev.waterHeightMm !== undefined && Number.isFinite(heightMm);
  setText("infoWaterHeight", hasHeight ? `${heightMm.toFixed(0)} mm` : "—");
  setText("calibLive", Number.isFinite(Number(dev.currentDist)) && dev.currentDist !== null ? Number(dev.currentDist).toFixed(1) : "—");
  setText("calibHeight", hasHeight ? heightMm.toFixed(0) : "—");
  setText("calibPercent", hasPercent ? percent.toFixed(0) : "—");
  setText("calibLiters", Number.isFinite(Number(dev.waterLiters)) ? Number(dev.waterLiters).toFixed(1) : "—");

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

  renderControls(dev);
  if (fillForm) fillTankForm(dev);
}

/* ---------------------------------------------------------------------------
 * Interruptores de bomba y llenado automático
 * ------------------------------------------------------------------------- */
const controlBusy = { relay: false, auto: false };

function renderControls(dev) {
  const relaySwitch = el("relaySwitch");
  const autoSwitch = el("autoSwitch");
  if (!relaySwitch || !autoSwitch) return;

  const usable = Boolean(dev && dev.claimed);
  const online = Boolean(dev && dev.online);
  const on = Boolean(dev && dev.relayState);

  // La etiqueta y el interruptor siempre reflejan el estado real que informa el dispositivo.
  setText("relayValue", dev ? (on ? "ENCENDIDA" : "APAGADA") : "—");
  el("relayValue")?.classList.toggle("is-on", on);

  if (!controlBusy.relay) relaySwitch.checked = on;
  relaySwitch.disabled = !(usable && online) || controlBusy.relay;
  setText(
    "relaySwitchState",
    !dev ? "—" : !usable ? "Dispositivo sin vincular" : !online ? "Dispositivo offline" : on ? "Encendida" : "Apagada",
  );

  const auto = Boolean(dev && dev.autoRefill);
  if (!controlBusy.auto) autoSwitch.checked = auto;
  autoSwitch.disabled = !usable || controlBusy.auto;
  setText("autoSwitchState", !dev ? "—" : auto ? "Activado" : "Desactivado");

  const hint = el("controlHint");
  if (hint) {
    if (!dev) {
      hint.textContent = "";
    } else if (auto && dev.autoPaused) {
      hint.textContent = "Llenado automático en pausa porque apagaste la bomba a mano. Se reanuda al llegar al nivel máximo, tras unos minutos o al guardar la configuración.";
    } else if (auto) {
      hint.textContent = `Enciende la bomba por debajo de ${dev.minLevel}% y la apaga al llegar a ${dev.maxLevel}%.`;
    } else {
      hint.textContent = "Llenado automático desactivado: la bomba solo se enciende y se apaga con el interruptor.";
    }
  }
}

async function onRelaySwitchChange(event) {
  const dev = selectedDevice();
  const input = event.target;
  const desired = input.checked;
  if (!dev || !dev.claimed) {
    input.checked = !desired;
    return toast("El dispositivo debe vincularse primero", "warn");
  }

  controlBusy.relay = true;
  input.disabled = true;
  try {
    const result = await socket.request({
      command: "set_relay",
      device_id: dev.id,
      state: desired,
    });
    if (result.event === "ack" && result.ok) {
      // Se muestra lo que el firmware dejó realmente aplicado, no lo que se pidió.
      const actual = typeof result.relay_state === "boolean" ? result.relay_state : desired;
      dev.relayState = actual;
      if (actual !== desired) toast("El relé no quedó en el estado pedido", "warn");
    } else {
      handleRequestError(result, "No se pudo controlar la bomba");
    }
  } catch (error) {
    toast(error.message, "error");
  } finally {
    controlBusy.relay = false;
    renderControls(selectedDevice());
  }
}

async function onAutoSwitchChange(event) {
  const dev = selectedDevice();
  const input = event.target;
  const desired = input.checked;
  if (!dev || !dev.claimed) {
    input.checked = !desired;
    return;
  }

  controlBusy.auto = true;
  input.disabled = true;
  try {
    const result = await socket.request({
      event: "update_config",
      device_id: dev.id,
      config: {
        capacity: dev.capacity,
        bottom_dist_mm: dev.bottomDist,
        mirror_dist_mm: dev.mirrorDist,
        min_level: dev.minLevel,
        max_level: dev.maxLevel,
        auto_refill: desired,
      },
    });
    if (result.event === "ack" && result.ok) {
      dev.autoRefill = desired;
      dev.autoPaused = false;
      toast(desired ? "Llenado automático activado" : "Llenado automático desactivado", "success");
    } else {
      handleRequestError(result, "No se pudo cambiar el llenado automático");
    }
  } catch (error) {
    toast(error.message, "error");
  } finally {
    controlBusy.auto = false;
    renderControls(selectedDevice());
    if (selectedDevice()) el("cfgAutoRefill").checked = Boolean(selectedDevice().autoRefill);
  }
}

/* ---------------------------------------------------------------------------
 * Formulario de calibración y niveles
 * ------------------------------------------------------------------------- */
function round1(value) {
  return Math.round(Number(value) * 10) / 10;
}

function syncMirrorField() {
  const bottom = Number(el("cfgBottomDist").value);
  const maxHeight = Number(el("cfgMaxHeight").value);
  const mirror = el("cfgMirrorDist");
  if (Number.isFinite(bottom) && Number.isFinite(maxHeight) && el("cfgBottomDist").value !== "" && el("cfgMaxHeight").value !== "") {
    mirror.value = round1(bottom - maxHeight);
  } else {
    mirror.value = "";
  }
}

export function fillTankForm(dev) {
  if (!dev) return;
  const bottom = Number(dev.bottomDist ?? 900);
  const mirror = Number(dev.mirrorDist ?? 100);
  el("cfgCapacity").value = dev.capacity ?? 50;
  el("cfgBottomDist").value = round1(bottom);
  el("cfgMaxHeight").value = round1(bottom - mirror);
  el("cfgMirrorDist").value = round1(mirror);
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
  if (message.water_height_mm !== undefined) dev.waterHeightMm = message.water_height_mm;
  if (typeof message.relay_state === "boolean") dev.relayState = message.relay_state;
  if (message.auto_paused !== undefined) dev.autoPaused = Boolean(message.auto_paused);
  if (message.device_id === state.selectedId) renderDashboard(false);
}

/** Cambio del relé informado por el backend (manual desde otro panel, automático o desconexión). */
export function updateRelayState(message) {
  const dev = state.devices.find((item) => item.id === message.device_id);
  if (!dev || typeof message.relay_state !== "boolean") return;
  const changed = dev.relayState !== message.relay_state;
  dev.relayState = message.relay_state;
  if (message.device_id === state.selectedId) {
    renderDashboard(false);
    if (changed && message.source === "auto") {
      toast(
        message.relay_state
          ? "Bomba encendida automáticamente: nivel bajo"
          : "Bomba apagada automáticamente: nivel máximo alcanzado",
        "info",
      );
    }
  }
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

async function calibrate(point) {
  const dev = selectedDevice();
  if (!dev) return toast("Selecciona un dispositivo", "warn");
  if (!dev.claimed) return toast("El dispositivo debe vincularse primero", "warn");
  if (!dev.online) return toast("El dispositivo debe estar online para calibrar", "warn");

  const isBottom = point === "bottom";
  const ok = await confirmAction(
    isBottom ? "Medir fondo" : "Medir máximo",
    isBottom
      ? "El tanque debe estar VACÍO. Se tomará la lectura actual del sensor como distancia al fondo."
      : "El agua debe estar en su nivel MÁXIMO y en calma. Se tomará la lectura actual como distancia al espejo de agua al 100 %.",
    "Medir",
    false,
  );
  if (!ok) return;

  const button = el(isBottom ? "btnCalibBottom" : "btnCalibMax");
  if (button) button.disabled = true;
  try {
    const result = await socket.request({ event: "calibrate", device_id: dev.id, point }, 20000);
    if (result.event === "calibrate_result" && result.ok) {
      toast(
        isBottom
          ? `Fondo calibrado: sensor a ${result.sensor_height_mm} mm del fondo`
          : `Máximo calibrado: ${result.max_water_height_mm} mm de agua sobre el fondo`,
        "success",
      );
    } else {
      handleRequestError(result, "No se pudo calibrar");
    }
  } catch (error) {
    toast(error.message, "error");
  } finally {
    if (button) button.disabled = false;
  }
}

export function openClaimModal() {
  const dev = selectedDevice();

  const form = document.createElement("form");
  form.className = "form-grid";
  form.id = "claimDeviceForm";

  const fields = [
    { id: "claimToken", label: "Token del dispositivo", value: "", type: "text", required: true },
  ];

  for (const field of fields) {
    const wrapper = document.createElement("div");
    wrapper.className = "field";
    const label = document.createElement("label");
    label.htmlFor = field.id;
    label.textContent = field.label;
    const input = document.createElement("input");
    input.id = field.id;
    input.type = field.type;
    input.value = field.value;
    input.required = field.required;
    input.placeholder = "Ingresa el token del config.json";
    wrapper.append(label, input);
    form.appendChild(wrapper);
  }

  const hint = document.createElement("p");
  hint.className = "field-hint";
  hint.style.gridColumn = "1 / -1";
  hint.textContent = "El dispositivo debe estar online y pendiente de vinculación. Solo necesitas el token.";
  form.appendChild(hint);

  // Step 2: code input (hidden initially)
  const codeSection = document.createElement("div");
  codeSection.id = "claimCodeSection";
  codeSection.style.gridColumn = "1 / -1";
  codeSection.style.display = "none";

  const codeLabel = document.createElement("label");
  codeLabel.textContent = "Código de 6 dígitos del LCD:";
  codeLabel.style.display = "block";
  codeLabel.style.marginBottom = "0.5rem";

  const codeInput = document.createElement("input");
  codeInput.id = "claimCode";
  codeInput.type = "text";
  codeInput.maxLength = 6;
  codeInput.pattern = "[0-9]{6}";
  codeInput.placeholder = "123456";
  codeInput.style.fontSize = "1.5rem";
  codeInput.style.textAlign = "center";
  codeInput.style.letterSpacing = "0.3em";

  const countdownEl = document.createElement("p");
  countdownEl.id = "claimCountdown";
  countdownEl.style.textAlign = "center";
  countdownEl.style.marginTop = "0.5rem";

  codeSection.append(codeLabel, codeInput, countdownEl);
  form.appendChild(codeSection);

  const submit = document.createElement("button");
  submit.type = "submit";
  submit.className = "btn btn-primary";
  submit.textContent = "Enviar código al dispositivo";
  submit.style.gridColumn = "1 / -1";
  form.appendChild(submit);

  // Enable submit button only when code input has exactly 6 digits
  const updateSubmitState = () => {
    if (codeSection.style.display !== "none" && claimDeviceId) {
      const val = codeInput.value.trim();
      submit.disabled = val.length !== 6;
    }
  };
  codeInput.addEventListener("input", updateSubmitState);

  let claimDeviceId = null;
  let countdownInterval = null;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (codeSection.style.display === "none") {
      // Step 1: send token
      submit.disabled = true;
      submit.textContent = "Enviando…";
      const token = el("claimToken").value.trim();
      try {
        const result = await socket.request({
          event: "start_claim_by_token",
          token: token,
        }, 15000);

        if (result.event === "claim_code_sent") {
          claimDeviceId = result.device_id;
          toast(result.message || "Código enviado al dispositivo", "success");
          codeSection.style.display = "block";
          submit.textContent = "Verificar código";
          codeInput.value = "";
          updateSubmitState();  // will disable submit since input is empty
          codeInput.focus();

          // Start countdown
          let remaining = 15;
          countdownEl.textContent = remaining + "s restantes";
          countdownInterval = setInterval(() => {
            remaining--;
            if (remaining <= 0) {
              clearInterval(countdownInterval);
              countdownEl.textContent = "Expirado. Solicita un nuevo código.";
              submit.textContent = "Enviar código al dispositivo";
              codeSection.style.display = "none";
              codeInput.value = "";
              claimDeviceId = null;
            } else {
              countdownEl.textContent = remaining + "s restantes";
            }
          }, 1000);
        } else {
          handleRequestError(result, "No se pudo enviar el código");
        }
      } catch (error) {
        toast(error.message, "error");
      } finally {
        if (!claimDeviceId) {
          submit.disabled = false;
          submit.textContent = "Enviar código al dispositivo";
        }
      }
    } else if (claimDeviceId) {
      // Step 2: verify code
      submit.disabled = true;
      submit.textContent = "Verificando…";
      const code = el("claimCode").value.trim();
      console.log("[CLAIM] Verifying code:", code, "for device:", claimDeviceId);
      try {
        const result = await socket.request({
          event: "verify_claim",
          device_id: claimDeviceId,
          code: code,
        }, 10000);

        console.log("[CLAIM] Response:", result);
        if (result.event === "claim_verified") {
          clearInterval(countdownInterval);
          toast(result.message || "Dispositivo vinculado", "success");
          closeModal();
        } else {
          handleRequestError(result, "Código incorrecto");
        }
      } catch (error) {
        console.error("[CLAIM] Error:", error);
        toast(error.message, "error");
      } finally {
        submit.textContent = "Verificar código";
        updateSubmitState();  // re-enable only if 6 digits entered
      }
    }
  });

  openModal("Vincular dispositivo", form, [
    { label: "Cancelar", className: "btn-ghost", onClick: () => {
      if (countdownInterval) clearInterval(countdownInterval);
      closeModal();
    }},
  ]);
}

async function saveTankConfig(event) {
  event.preventDefault();
  const dev = selectedDevice();
  if (!dev) return toast("Selecciona un dispositivo", "warn");

  const bottom = Number(el("cfgBottomDist").value);
  const maxHeight = Number(el("cfgMaxHeight").value);
  if (!(maxHeight > 0) || !(maxHeight < bottom)) {
    return toast("La altura máxima del agua debe ser mayor que 0 y menor que la altura del sensor", "warn");
  }

  const payload = {
    event: "update_config",
    device_id: dev.id,
    config: {
      capacity: Number(el("cfgCapacity").value),
      bottom_dist_mm: bottom,
      mirror_dist_mm: round1(bottom - maxHeight),
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

  el("relaySwitch")?.addEventListener("change", onRelaySwitchChange);
  el("autoSwitch")?.addEventListener("change", onAutoSwitchChange);
  el("btnCalibBottom")?.addEventListener("click", () => calibrate("bottom"));
  el("btnCalibMax")?.addEventListener("click", () => calibrate("max"));
  el("cfgBottomDist")?.addEventListener("input", syncMirrorField);
  el("cfgMaxHeight")?.addEventListener("input", syncMirrorField);
  el("btnOpenClaimModal")?.addEventListener("click", openClaimModal);
  el("tankConfigForm")?.addEventListener("submit", saveTankConfig);
}
