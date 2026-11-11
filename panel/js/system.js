import { selectedDevice } from "./state.js";
import { socket, handleRequestError } from "./ws.js";
import { confirmAction, el, toast } from "./ui.js";

async function deviceAction(action, extra = {}) {
  const dev = selectedDevice();
  if (!dev) return toast("Selecciona un dispositivo", "warn");
  if (!dev.claimed) return toast("El dispositivo debe estar vinculado", "warn");
  if (!dev.online) return toast("El dispositivo está offline", "warn");
  try {
    const result = await socket.request({ event: "device_action", device_id: dev.id, action, ...extra }, 20000);
    if (result.event === "ack" && result.ok) toast("Acción enviada al dispositivo", "success");
    else handleRequestError(result, "No se pudo ejecutar la acción");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function rebootDevice() {
  const ok = await confirmAction("Reiniciar dispositivo", "Se apagará el relé y el ESP32 se reiniciará. Volverá a conectarse automáticamente.", "Reiniciar");
  if (ok) await deviceAction("reboot");
}

async function sleepDevice() {
  const minutes = Number(el("sleepMinutes").value || 60);
  const ok = await confirmAction("Dormir dispositivo", `El relé se apagará y el ESP32 entrará en deep sleep durante ${minutes} minutos. También puede despertar con el botón físico.`, "Dormir");
  if (ok) await deviceAction("sleep", { minutes });
}

async function factoryResetDevice() {
  const ok = await confirmAction("Reset de fábrica", "Se borrará /config.json del ESP32, incluida la identidad y las redes. El dispositivo dejará de estar vinculado hasta reconfigurarlo.", "Borrar configuración");
  if (ok) await deviceAction("factory_reset");
}

async function deleteDevice() {
  const dev = selectedDevice();
  if (!dev) return toast("Selecciona un dispositivo", "warn");
  const ok = await confirmAction("Eliminar dispositivo del panel", `Se borrará «${dev.name}» (${dev.id}) de la base de datos. El ESP32 seguirá funcionando hasta que se le haga un reset de fábrica.`, "Eliminar");
  if (!ok) return;
  try {
    const result = await socket.request({ event: "delete_device", device_id: dev.id });
    if (result.event === "ack" && result.ok) toast("Dispositivo eliminado", "success");
    else handleRequestError(result, "No se pudo eliminar");
  } catch (error) {
    toast(error.message, "error");
  }
}

// Se mantienen únicamente las acciones del dispositivo; no se inicializan
// botones para reiniciar/detener servicios del servidor.
export function initSystem() {
  el("btnReboot")?.addEventListener("click", rebootDevice);
  el("btnSleep")?.addEventListener("click", sleepDevice);
  el("btnFactoryReset")?.addEventListener("click", factoryResetDevice);
  el("btnDeleteDevice")?.addEventListener("click", deleteDevice);
}
