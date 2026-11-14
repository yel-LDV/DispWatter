#include "menu_definitions.h"

// ===========================================================================
// 1. 📡 WiFi
// ===========================================================================

static const MenuItem wifi_items[] = {
    {"Red actual", "SSID: --", ACTION_VALUE_VIEW, nullptr, MENU_WIFI, WIFI_CURRENT},
    {"Escanear redes", "Buscar redes WiFi...", ACTION_EXECUTE, nullptr, MENU_WIFI, WIFI_SCAN},
    {"Agregar red", "Conectar a nueva red", ACTION_EXECUTE, nullptr, MENU_WIFI, WIFI_ADD},
    {"Redes guardadas", "Ver redes configuradas", ACTION_SUBMENU, &menu_wifi_saved, MENU_WIFI, WIFI_SAVED},
    {"Prioridad", "Orden de conexion", ACTION_EXECUTE, nullptr, MENU_WIFI, WIFI_PRIORITY},
    {"Modo avion", "Desactivar WiFi", ACTION_TOGGLE, nullptr, MENU_WIFI, WIFI_AIRPLANE},
};

const Menu menu_wifi = {"WiFi", wifi_items, 6};

// ===========================================================================
// 1a. 📡 WiFi > Redes guardadas (lista dinámica, placeholder)
// ===========================================================================

static const MenuItem wifi_saved_items[] = {
    {"Red 1", "Conectar/Eliminar", ACTION_SUBMENU, &menu_wifi_network, MENU_WIFI_SAVED, 0},
    {"Red 2", "Conectar/Eliminar", ACTION_SUBMENU, &menu_wifi_network, MENU_WIFI_SAVED, 1},
};

const Menu menu_wifi_saved = {"WiFi guardadas", wifi_saved_items, 2};

// ===========================================================================
// 1b. 📡 WiFi > Red individual
// ===========================================================================

static const MenuItem wifi_network_items[] = {
    {"Conectar", "Forzar conexion", ACTION_CONFIRM_EXECUTE, nullptr, MENU_WIFI_NETWORK, WIFI_NET_CONNECT},
    {"Eliminar", "Quitar esta red", ACTION_CONFIRM_EXECUTE, nullptr, MENU_WIFI_NETWORK, WIFI_NET_DELETE},
    {"Subir prioridad", "Mover antes en lista", ACTION_EXECUTE, nullptr, MENU_WIFI_NETWORK, WIFI_NET_PRIORITY_UP},
    {"Bajar prioridad", "Mover despues en lista", ACTION_EXECUTE, nullptr, MENU_WIFI_NETWORK, WIFI_NET_PRIORITY_DOWN},
    {"Senal", "RSSI actual", ACTION_VALUE_VIEW, nullptr, MENU_WIFI_NETWORK, WIFI_NET_SIGNAL},
    {"Contraseña", "Oculta/visible", ACTION_TOGGLE, nullptr, MENU_WIFI_NETWORK, WIFI_NET_PASSWORD},
};

const Menu menu_wifi_network = {"Red WiFi", wifi_network_items, 6};

// ===========================================================================
// 2. 🔧 Dispositivo
// ===========================================================================

static const MenuItem device_items[] = {
    {"Nombre", "Nombre del dispositivo", ACTION_VALUE_VIEW, nullptr, MENU_DEVICE, DEVICE_NAME},
    {"Ubicacion", "Ubicacion fisica", ACTION_VALUE_VIEW, nullptr, MENU_DEVICE, DEVICE_LOCATION},
    {"ID", "ID unico del dispositivo", ACTION_VALUE_VIEW, nullptr, MENU_DEVICE, DEVICE_ID},
    {"Serial", "Numero de serie (MAC)", ACTION_VALUE_VIEW, nullptr, MENU_DEVICE, DEVICE_SERIAL},
    {"Reiniciar", "Reiniciar el ESP32", ACTION_CONFIRM_EXECUTE, nullptr, MENU_DEVICE, DEVICE_REBOOT},
    {"Dormir", "Enviar a deep sleep", ACTION_CONFIRM_EXECUTE, nullptr, MENU_DEVICE, DEVICE_SLEEP},
    {"Uptime", "Tiempo encendido", ACTION_VALUE_VIEW, nullptr, MENU_DEVICE, DEVICE_UPTIME},
    {"Heap libre", "Memoria disponible", ACTION_VALUE_VIEW, nullptr, MENU_DEVICE, DEVICE_HEAP},
};

const Menu menu_device = {"Dispositivo", device_items, 8};

// ===========================================================================
// 3. 💧 Bomba
// ===========================================================================

static const MenuItem pump_items[] = {
    {"Estado", "ON / OFF actual", ACTION_VALUE_VIEW, nullptr, MENU_PUMP, PUMP_STATUS},
    {"Encender", "Activar bomba manual", ACTION_CONFIRM_EXECUTE, nullptr, MENU_PUMP, PUMP_TURN_ON},
    {"Apagar", "Desactivar bomba", ACTION_EXECUTE, nullptr, MENU_PUMP, PUMP_TURN_OFF},
    {"Prueba 10s", "Activar 10 seg prueba", ACTION_CONFIRM_EXECUTE, nullptr, MENU_PUMP, PUMP_TEST_10S},
    {"Prot. desborde", "ON/OFF proteccion", ACTION_TOGGLE, nullptr, MENU_PUMP, PUMP_OVERFLOW_PROTECT},
    {"Max encendido", "Tiempo max ON (min)", ACTION_VALUE_VIEW, nullptr, MENU_PUMP, PUMP_MAX_ON},
    {"Min apagado", "Tiempo min OFF (min)", ACTION_VALUE_VIEW, nullptr, MENU_PUMP, PUMP_MIN_OFF},
    {"Max offline", "Corte sin WiFi (min)", ACTION_VALUE_VIEW, nullptr, MENU_PUMP, PUMP_MAX_OFFLINE},
    {"Nivel actual", "Porcentaje del tanque", ACTION_VALUE_VIEW, nullptr, MENU_PUMP, PUMP_LEVEL},
    {"Litros", "Litros calculados", ACTION_VALUE_VIEW, nullptr, MENU_PUMP, PUMP_LITERS},
};

const Menu menu_pump = {"Bomba", pump_items, 10};

// ===========================================================================
// 4. 📊 Sensores
// ===========================================================================

static const MenuItem sensor_items[] = {
    {"Distancia", "Lectura HC-SR04 (cm)", ACTION_VALUE_VIEW, nullptr, MENU_SENSORS, SENSOR_DISTANCE},
    {"Calibrar min", "Dist min (tanque lleno)", ACTION_EXECUTE, nullptr, MENU_SENSORS, SENSOR_CAL_MIN},
    {"Calibrar max", "Dist max (tanque vacio)", ACTION_EXECUTE, nullptr, MENU_SENSORS, SENSOR_CAL_MAX},
    {"Intervalo", "Muestreo (ms)", ACTION_VALUE_VIEW, nullptr, MENU_SENSORS, SENSOR_INTERVAL},
    {"Promedio", "Lecturas promediadas", ACTION_VALUE_VIEW, nullptr, MENU_SENSORS, SENSOR_AVERAGE},
    {"Estado", "Sensor OK / Error", ACTION_VALUE_VIEW, nullptr, MENU_SENSORS, SENSOR_STATUS},
};

const Menu menu_sensors = {"Sensores", sensor_items, 6};

// ===========================================================================
// 5. 🔄 Firmware
// ===========================================================================

static const MenuItem firmware_items[] = {
    {"Version actual", "Firmware instalado", ACTION_VALUE_VIEW, nullptr, MENU_FIRMWARE, FIRMWARE_CURRENT},
    {"Actualizar", "Buscar actualizacion", ACTION_EXECUTE, nullptr, MENU_FIRMWARE, FIRMWARE_UPDATE},
    {"Historial", "Versiones anteriores", ACTION_VALUE_VIEW, nullptr, MENU_FIRMWARE, FIRMWARE_HISTORY},
    {"Auto-actualizar", "ON/OFF auto update", ACTION_TOGGLE, nullptr, MENU_FIRMWARE, FIRMWARE_AUTO_UPDATE},
};

const Menu menu_firmware = {"Firmware", firmware_items, 4};

// ===========================================================================
// 5a. 🔄 Firmware > Detalle de versión (plantilla)
// ===========================================================================

static const MenuItem firmware_version_items[] = {
    {"Version", "Numero de version", ACTION_VALUE_VIEW, nullptr, MENU_FIRMWARE_VERSION, FW_VER_VERSION},
    {"Fecha", "Fecha publicacion", ACTION_VALUE_VIEW, nullptr, MENU_FIRMWARE_VERSION, FW_VER_DATE},
    {"Tipo", "Estable/Experimental", ACTION_VALUE_VIEW, nullptr, MENU_FIRMWARE_VERSION, FW_VER_TYPE},
    {"Rama", "Rama de Git", ACTION_VALUE_VIEW, nullptr, MENU_FIRMWARE_VERSION, FW_VER_BRANCH},
    {"Commit", "Hash del commit", ACTION_VALUE_VIEW, nullptr, MENU_FIRMWARE_VERSION, FW_VER_COMMIT},
    {"Tamaño", "Tamaño binario", ACTION_VALUE_VIEW, nullptr, MENU_FIRMWARE_VERSION, FW_VER_SIZE},
    {"Cambios", "Notas de release", ACTION_VALUE_VIEW, nullptr, MENU_FIRMWARE_VERSION, FW_VER_CHANGES},
    {"Instalar", "Descargar e instalar", ACTION_CONFIRM_EXECUTE, nullptr, MENU_FIRMWARE_VERSION, FW_VER_INSTALL},
    {"Cancelar", "Volver sin instalar", ACTION_EXECUTE, nullptr, MENU_FIRMWARE_VERSION, FW_VER_CANCEL},
};

const Menu menu_firmware_version = {"Version firmware", firmware_version_items, 9};

// ===========================================================================
// 6. 🌐 Red
// ===========================================================================

static const MenuItem network_items[] = {
    {"WiFi", "Estado conexion", ACTION_VALUE_VIEW, nullptr, MENU_NETWORK, NET_WIFI_STATUS},
    {"SSID actual", "Red conectada", ACTION_VALUE_VIEW, nullptr, MENU_NETWORK, NET_SSID},
    {"Senal", "RSSI actual", ACTION_VALUE_VIEW, nullptr, MENU_NETWORK, NET_SIGNAL},
    {"IP", "Direccion IP", ACTION_VALUE_VIEW, nullptr, MENU_NETWORK, NET_IP},
    {"Backend", "WebSocket estado", ACTION_VALUE_VIEW, nullptr, MENU_NETWORK, NET_BACKEND},
    {"Host backend", "Host del backend", ACTION_VALUE_VIEW, nullptr, MENU_NETWORK, NET_HOST},
    {"Puerto", "Puerto backend", ACTION_VALUE_VIEW, nullptr, MENU_NETWORK, NET_PORT},
    {"TLS", "Conexion segura", ACTION_VALUE_VIEW, nullptr, MENU_NETWORK, NET_TLS},
    {"Ultimo ping", "Tiempo ultimo ping", ACTION_VALUE_VIEW, nullptr, MENU_NETWORK, NET_LAST_PING},
    {"Reintentos", "Contador reintentos", ACTION_VALUE_VIEW, nullptr, MENU_NETWORK, NET_RETRIES},
};

const Menu menu_network = {"Red", network_items, 10};

// ===========================================================================
// 7. 🔒 Seguridad
// ===========================================================================

static const MenuItem security_items[] = {
    {"Estado vinc.", "Vinculado/Pendiente", ACTION_VALUE_VIEW, nullptr, MENU_SECURITY, SEC_CLAIM_STATUS},
    {"Codigo claim", "Solicitar codigo", ACTION_EXECUTE, nullptr, MENU_SECURITY, SEC_CLAIM_CODE},
    {"Desvincular", "Desvincular del panel", ACTION_CONFIRM_EXECUTE, nullptr, MENU_SECURITY, SEC_UNLINK},
    {"Factory reset", "Resetear configuracion", ACTION_CONFIRM_EXECUTE, nullptr, MENU_SECURITY, SEC_FACTORY_RESET},
    {"Bloq. botones", "Bloquear todos", ACTION_TOGGLE, nullptr, MENU_SECURITY, SEC_LOCK_BUTTONS},
    {"Botones bloq.", "Lista IDs bloqueados", ACTION_VALUE_VIEW, nullptr, MENU_SECURITY, SEC_LOCKED_LIST},
};

const Menu menu_security = {"Seguridad", security_items, 6};

// ===========================================================================
// Menú principal (raíz) — 7 opciones
// ===========================================================================

static const MenuItem root_items[] = {
    {"WiFi", "Gestionar redes WiFi", ACTION_SUBMENU, &menu_wifi, MENU_ROOT, ROOT_WIFI},
    {"Dispositivo", "Nombre, ubicacion, reinicio", ACTION_SUBMENU, &menu_device, MENU_ROOT, ROOT_DEVICE},
    {"Bomba", "Control manual y protecciones", ACTION_SUBMENU, &menu_pump, MENU_ROOT, ROOT_PUMP},
    {"Sensores", "Calibracion y estado", ACTION_SUBMENU, &menu_sensors, MENU_ROOT, ROOT_SENSORS},
    {"Firmware", "Versiones y actualizacion", ACTION_SUBMENU, &menu_firmware, MENU_ROOT, ROOT_FIRMWARE},
    {"Red", "Estado conexion y backend", ACTION_SUBMENU, &menu_network, MENU_ROOT, ROOT_NETWORK},
    {"Seguridad", "Vinculacion y factory reset", ACTION_SUBMENU, &menu_security, MENU_ROOT, ROOT_SECURITY},
};

const Menu menu_root = {"Menu principal", root_items, 7};
