#ifndef MENU_DEFINITIONS_H
#define MENU_DEFINITIONS_H

#include "SettingsMenu.h"

// ===========================================================================
// IDs de menús
// ===========================================================================

enum MenuIds {
    MENU_ROOT = 0,
    MENU_WIFI,
    MENU_WIFI_SAVED,       // Lista de redes guardadas
    MENU_WIFI_NETWORK,     // Opciones por red individual
    MENU_DEVICE,
    MENU_PUMP,
    MENU_SENSORS,
    MENU_FIRMWARE,
    MENU_FIRMWARE_VERSION, // Detalle de una versión
    MENU_NETWORK,
    MENU_SECURITY
};

// ===========================================================================
// IDs de items por menú
// ===========================================================================

// MENU_ROOT
enum RootItems {
    ROOT_WIFI = 0,
    ROOT_DEVICE,
    ROOT_PUMP,
    ROOT_SENSORS,
    ROOT_FIRMWARE,
    ROOT_NETWORK,
    ROOT_SECURITY
};

// MENU_WIFI
enum WifiItems {
    WIFI_CURRENT = 0,
    WIFI_SCAN,
    WIFI_ADD,
    WIFI_SAVED,
    WIFI_PRIORITY,
    WIFI_AIRPLANE
};

// MENU_WIFI_NETWORK (por red individual)
enum WifiNetworkItems {
    WIFI_NET_CONNECT = 0,
    WIFI_NET_DELETE,
    WIFI_NET_PRIORITY_UP,
    WIFI_NET_PRIORITY_DOWN,
    WIFI_NET_SIGNAL,
    WIFI_NET_PASSWORD
};

// MENU_DEVICE
enum DeviceItems {
    DEVICE_NAME = 0,
    DEVICE_LOCATION,
    DEVICE_ID,
    DEVICE_SERIAL,
    DEVICE_REBOOT,
    DEVICE_SLEEP,
    DEVICE_UPTIME,
    DEVICE_HEAP
};

// MENU_PUMP
enum PumpItems {
    PUMP_STATUS = 0,
    PUMP_TURN_ON,
    PUMP_TURN_OFF,
    PUMP_TEST_10S,
    PUMP_OVERFLOW_PROTECT,
    PUMP_MAX_ON,
    PUMP_MIN_OFF,
    PUMP_MAX_OFFLINE,
    PUMP_LEVEL,
    PUMP_LITERS
};

// MENU_SENSORS
enum SensorItems {
    SENSOR_DISTANCE = 0,
    SENSOR_CAL_MIN,
    SENSOR_CAL_MAX,
    SENSOR_INTERVAL,
    SENSOR_AVERAGE,
    SENSOR_STATUS
};

// MENU_FIRMWARE
enum FirmwareItems {
    FIRMWARE_CURRENT = 0,
    FIRMWARE_UPDATE,
    FIRMWARE_HISTORY,
    FIRMWARE_AUTO_UPDATE
};

// MENU_FIRMWARE_VERSION (detalle de versión)
enum FirmwareVersionItems {
    FW_VER_VERSION = 0,
    FW_VER_DATE,
    FW_VER_TYPE,
    FW_VER_BRANCH,
    FW_VER_COMMIT,
    FW_VER_SIZE,
    FW_VER_CHANGES,
    FW_VER_INSTALL,
    FW_VER_CANCEL
};

// MENU_NETWORK
enum NetworkItems {
    NET_WIFI_STATUS = 0,
    NET_SSID,
    NET_SIGNAL,
    NET_IP,
    NET_BACKEND,
    NET_HOST,
    NET_PORT,
    NET_TLS,
    NET_LAST_PING,
    NET_RETRIES
};

// MENU_SECURITY
enum SecurityItems {
    SEC_CLAIM_STATUS = 0,
    SEC_CLAIM_CODE,
    SEC_UNLINK,
    SEC_FACTORY_RESET,
    SEC_LOCK_BUTTONS,
    SEC_LOCKED_LIST
};

// ===========================================================================
// Declaración de menús (definidos en menu_definitions.cpp)
// ===========================================================================

extern const Menu menu_wifi;
extern const Menu menu_wifi_saved;
extern const Menu menu_wifi_network;
extern const Menu menu_device;
extern const Menu menu_pump;
extern const Menu menu_sensors;
extern const Menu menu_firmware;
extern const Menu menu_firmware_version;
extern const Menu menu_network;
extern const Menu menu_security;

// Menú principal (raíz)
extern const Menu menu_root;

#endif // MENU_DEFINITIONS_H
