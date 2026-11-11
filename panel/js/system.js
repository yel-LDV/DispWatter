import { selectedDevice } from "./state.js";
import { socket, handleRequestError } from "./ws.js";
import { confirmAction, el, toast } from "./ui.js";

async function deviceAction(action, extra = {}) {
  const dev = selectedDevice();
  if (!dev) return toast("Selecciona un dispositivo", "warn");
  if (!dev.claimed) return toast("El dispositivo debe estar vinculado", "warn");
  if (!dev.online) return toast("El dispositivo está offline", "warn");

  try {
    const result = await socket.request({
      event: "device_action",
      device_id: dev.id,
      action,
      ...extra,
    }, 20000);

    if (result.event === "ack" && result.ok) {
      toast("Acción enviada al dispositivo", "success");
    } else {
      handleRequestError(result, "No se pudo ejecutar la acción");
    }
  } catch (error) {
    toast(error.message, "error");
  }
}

async function rebootDevice() {
  const ok = await confirmAction(
    "Reiniciar dispositivo",
    "Se apagará el relé y el ESP32 se reiniciará. Volverá a conectarse automáticamente.",
    "Reiniciar",
  );
  if (ok) await deviceAction("reboot");
}

async function sleepDevice() {
  const minutes = Number(el("sleepMinutes").value || 60);
  const ok = await confirmAction(
    "Dormir dispositivo",
    `El relé se apagará y el ESP32 entrará en deep sleep durante ${minutes} minutos. También puede despertar con el botón físico.`,
    "Dormir",
  );
  if (ok) await deviceAction("sleep", { minutes });
}

async function factoryResetDevice() {
  const ok = await confirmAction(
    "Reset de fábrica",
    "Se borrará /config.json del ESP32, incluida la identidad y las redes. El dispositivo dejará de estar vinculado hasta reconfigurarlo.",
    "Borrar configuración",
  );
  if (ok) await deviceAction("factory_reset");
}

async function deleteDevice() {
  const dev = selectedDevice();
  if (!dev) return toast("Selecciona un dispositivo", "warn");
  const ok = await confirmAction(
    "Eliminar dispositivo del panel",
    `Se borrará «${dev.name}» (${dev.id}) de la base de datos. El ESP32 seguirá funcionando hasta que se le haga un reset de fábrica.`,
    "Eliminar",
  );
  if (!ok) return;

  try {
    const result = await socket.request({ event: "delete_device", device_id: dev.id });
    if (result.event === "ack" && result.ok) {
      toast("Dispositivo eliminado", "success");
    } else {
      handleRequestError(result, "No se pudo eliminar");
    }
  } catch (error) {
    toast(error.message, "error");
  }
}

async function systemAction(target, action, confirmation = null) {
  if (confirmation) {
    const ok = await confirmAction(confirmation.title, confirmation.message, confirmation.label);
    if (!ok) return;
  }

  const output = el("systemOutput");
  output.textContent = "Ejecutando…";

  try {
    const result = await socket.request({
      event: "system_action",
      target,
      action,
    }, 30000);

    if (result.event === "system_result") {
      output.textContent = result.output || (result.ok ? "Operación completada." : "Operación fallida.");
      toast(result.ok ? "Operación completada" : "La operación falló", result.ok ? "success" : "error");
    } else if (result.event === "error") {
      output.textContent = result.message || result.code || "Error";
      handleRequestError(result, "No se pudo ejecutar la acción");
    } else {
      output.textContent = JSON.stringify(result, null, 2);
    }
  } catch (error) {
    output.textContent = error.message;
    toast(error.message, "error");
  }
}

export function initSystem() {
  el("btnReboot")?.addEventListener("click", rebootDevice);
  el("btnSleep")?.addEventListener("click", sleepDevice);
  el("btnFactoryReset")?.addEventListener("click", factoryResetDevice);
  el("btnDeleteDevice")?.addEventListener("click", deleteDevice);

  el("btnSystemStatus")?.addEventListener("click", () => systemAction("all", "status"));
  el("btnBackendRestart")?.addEventListener("click", () => systemAction("backend", "restart", {
    title: "Reiniciar backend",
    message: "El backend se reiniciará en un segundo. La conexión del panel se perderá y se reconectará sola.",
    label: "Reiniciar",
  }));
  el("btnPanelRestart")?.addEventListener("click", () => systemAction("panel", "restart", {
    title: "Reiniciar panel",
    message: "Se reiniciará el servidor HTTP del panel. La página seguirá abierta pero dejará de actualizarse unos segundos.",
    label: "Reiniciar",
  }));
  el("btnPanelStop")?.addEventListener("click", () => systemAction("panel", "stop", {
    title: "Detener panel",
    message: "Se detendrá el servidor HTTP del panel. Podrás volver a arrancarlo desde systemd o dispwatter-ctl.",
    label: "Detener panel",
  }));
  el("btnAllStop")?.addEventListener("click", () => systemAction("all", "stop", {
    title: "Apagar todo",
    message: "Se detendrá el panel y se enviará deep sleep a todos los dispositivos online. El backend seguirá vivo para permitir la recuperación.",
    label: "Apagar todo",
  }));
  el("btnAllStart")?.addEventListener("click", () => systemAction("all", "start", {
    title: "Encender todo",
    message: "Se arrancará el panel. Los dispositivos dormidos no pueden despertarse por red; usarán su temporizador o el botón físico.",
    label: "Encender",
  }));
  el("btnAllRestart")?.addEventListener("click", () => systemAction("all", "restart", {
    title: "Reiniciar todo",
    message: "Se reiniciará el panel y se enviará reboot a todos los dispositivos online. El backend no se reinicia.",
    label: "Reiniciar todo",
  }));
}
