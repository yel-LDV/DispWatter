#!/usr/bin/env bash
# ==============================================================================
# DispWatter - Script Interactivo de Configuración y Flasheo para ESP32
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colores de interfaz
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

LOGS_DIR="$SCRIPT_DIR/logs"
AUDIT_LOG_FILE="$LOGS_DIR/audit.log"
CONFIG_FILE="$SCRIPT_DIR/hardware/esp32/main/src/config.h"

mkdir -p "$LOGS_DIR"

log_audit() {
    local action="$1"
    local details="$2"
    local now_iso
    now_iso="$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')"
    echo "[$now_iso] [AUDIT] [$action] Actor=$(whoami) Details=$details" >> "$AUDIT_LOG_FILE"
}

echo -e "\n${BLUE}================================================================${NC}"
echo -e "${BLUE}${BOLD}      💧 DISPWATTER - ASISTENTE DE FLASHEO PARA ESP32           ${NC}"
echo -e "${BLUE}================================================================${NC}"
echo -e "Este script configurará las credenciales en el firmware, compilará"
echo -e "el proyecto y lo subirá por USB a tu placa ESP32.\n"

# 1. Detección automática de IP local
DETECTED_IP="$(ip -4 addr show 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '127.0.0.1' | head -n 1 || true)"
[ -z "$DETECTED_IP" ] && DETECTED_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -z "$DETECTED_IP" ] && DETECTED_IP="192.168.1.100"

# 2. Detección automática de puerto serie
DETECTED_PORTS=( $(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true) )
DEFAULT_PORT="/dev/ttyUSB0"
if [ ${#DETECTED_PORTS[@]} -gt 0 ]; then
    DEFAULT_PORT="${DETECTED_PORTS[0]}"
fi

# ==========================================
# RECOPILACIÓN DE DATOS (INTERACTIVA)
# ==========================================
echo -e "${CYAN}${BOLD}[1/4] Red WiFi${NC}"
read -rp "  Nombre de red (SSID) [MiWiFi]: " INPUT_SSID
WIFI_SSID="${INPUT_SSID:-MiWiFi}"

read -rsp "  Contraseña de WiFi [dejar vacio si es abierta]: " INPUT_PASS
echo ""
WIFI_PASS="${INPUT_PASS:-}"

echo -e "\n${CYAN}${BOLD}[2/4] Servidor Backend${NC}"
read -rp "  Dirección IP del Backend [$DETECTED_IP]: " INPUT_HOST
BACKEND_HOST="${INPUT_HOST:-$DETECTED_IP}"

read -rp "  Puerto WebSocket del Backend [8765]: " INPUT_PORT
BACKEND_PORT="${INPUT_PORT:-8765}"

echo -e "\n${CYAN}${BOLD}[3/4] Identidad y Metadatos del Dispositivo${NC}"
read -rp "  ID Único del Bebedero [WATTER-001]: " INPUT_DEV_ID
DEVICE_ID="${INPUT_DEV_ID:-WATTER-001}"

read -rp "  Nombre del Bebedero [Bebedero Huerto]: " INPUT_DEV_NAME
DEVICE_NAME="${INPUT_DEV_NAME:-Bebedero Huerto}"

read -rp "  Ubicación o Zona [Patio Principal]: " INPUT_DEV_LOC
DEVICE_LOCATION="${INPUT_DEV_LOC:-Patio Principal}"

read -rp "  Versión de Firmware [1.0.0]: " INPUT_DEV_VER
FIRMWARE_VERSION="${INPUT_DEV_VER:-1.0.0}"

read -rp "  Contraseña Secreta del Dispositivo [clave_secreta_99]: " INPUT_DEV_PASS
DEVICE_PASS="${INPUT_DEV_PASS:-clave_secreta_99}"

echo -e "\n${CYAN}${BOLD}[4/4] Puerto USB / Serie${NC}"
if [ ${#DETECTED_PORTS[@]} -gt 0 ]; then
    echo -e "  Puertos detectados: ${GREEN}${DETECTED_PORTS[*]}${NC}"
fi
read -rp "  Puerto para flashear [$DEFAULT_PORT]: " INPUT_SERIAL
SERIAL_PORT="${INPUT_SERIAL:-$DEFAULT_PORT}"

# ==========================================
# CONFIRMACIÓN Y GENERACIÓN DE CONFIG.H
# ==========================================
echo -e "\n${YELLOW}----------------------------------------------------------------${NC}"
echo -e "${BOLD}Resumen de configuración a flashear:${NC}"
echo -e "  • SSID WiFi:             ${GREEN}$WIFI_SSID${NC}"
echo -e "  • Backend WebSocket:     ${GREEN}ws://$BACKEND_HOST:$BACKEND_PORT/ws/device${NC}"
echo -e "  • Dispositivo ID:        ${GREEN}$DEVICE_ID${NC}"
echo -e "  • Nombre:                ${GREEN}$DEVICE_NAME${NC}"
echo -e "  • Ubicación:             ${GREEN}$DEVICE_LOCATION${NC}"
echo -e "  • Firmware:              ${GREEN}v$FIRMWARE_VERSION${NC}"
echo -e "  • Clave Secreta:         ${GREEN}********${NC}"
echo -e "  • Puerto de subida:      ${GREEN}$SERIAL_PORT${NC}"
echo -e "${YELLOW}----------------------------------------------------------------${NC}"

read -rp "¿Deseas compilar y flashear ahora al ESP32? (S/n): " CONFIRM
if [[ "$CONFIRM" =~ ^[nN] ]]; then
    echo -e "\nOperación cancelada. No se modificó el hardware."
    exit 0
fi

echo -e "\n-> Escribiendo configuración en $CONFIG_FILE..."
cat <<EOF > "$CONFIG_FILE"
#ifndef DEVICE_CONFIG_H
#define DEVICE_CONFIG_H

// ==========================================
// CONFIGURACIÓN GENERADA AUTOMÁTICAMENTE
// ==========================================
#define WIFI_SSID          "$WIFI_SSID"
#define WIFI_PASS          "$WIFI_PASS"

#define BACKEND_HOST       "$BACKEND_HOST"
#define BACKEND_PORT       $BACKEND_PORT
#define BACKEND_PATH       "/ws/device"

#define DEVICE_ID          "$DEVICE_ID"
#define DEVICE_PASS        "$DEVICE_PASS"
#define DEVICE_NAME        "$DEVICE_NAME"
#define DEVICE_LOCATION    "$DEVICE_LOCATION"
#define FIRMWARE_VERSION   "$FIRMWARE_VERSION"

#define PIN_TRIG           5
#define PIN_ECHO           18
#define PIN_RELE           4
#define LCD_I2C_ADDR       0x27

#define RELE_ON            LOW
#define RELE_OFF           HIGH

#define INTERVALO_MUESTREO_MS  2000
#define INTERVALO_REINTENTO_MS 5000

#endif // DEVICE_CONFIG_H
EOF

echo -e "   [${GREEN}OK${NC}] Configuración inyectada con éxito."

# ==========================================
# COMPILACIÓN Y SUBIDA
# ==========================================
echo -e "\n-> Compilando firmware con PlatformIO..."
log_audit "FLASH_ESP32_START" "DeviceID=$DEVICE_ID Host=$BACKEND_HOST:$BACKEND_PORT Port=$SERIAL_PORT"

pio run -d hardware/esp32/main

if [ "$1" == "--build-only" ]; then
    echo -e "\n[${GREEN}OK${NC}] Modo build-only completado. Binario listo."
    log_audit "BUILD_ESP32_SUCCESS" "DeviceID=$DEVICE_ID (Solo compilación)"
    exit 0
fi

echo -e "\n-> Subiendo firmware a $SERIAL_PORT..."
if pio run -d hardware/esp32/main --target upload --upload-port "$SERIAL_PORT"; then
    echo -e "\n${GREEN}================================================================${NC}"
    echo -e "${GREEN}${BOLD}       ✔ ¡ESP32 FLASHEADO Y LISTO PARA OPERAR!                  ${NC}"
    echo -e "${GREEN}================================================================${NC}"
    log_audit "FLASH_ESP32_SUCCESS" "DeviceID=$DEVICE_ID Port=$SERIAL_PORT"

    echo -e "\n${BOLD}Comportamiento de la pantalla LCD en tu ESP32:${NC}"
    echo -e "  1. Al arrancar:            ${BLUE}\"DispWatter / Iniciando...\"${NC}"
    echo -e "  2. Conectando a red:       ${BLUE}\"Conectando WiFi / $WIFI_SSID\"${NC}"
    echo -e "  3. Antes de vincular:      ${YELLOW}\"Servidor no conn / ID: $DEVICE_ID\"${NC}"
    echo -e "  4. Cada 5 segundos:        Reintentará conectar automáticamente al backend."
    echo -e "  5. Al conectar al backend: ${GREEN}\"Servidor Conect. / ID: $DEVICE_ID\"${NC}"
    echo -e "\n${BOLD}👉 Pasos para tomar posesión en el Panel Web:${NC}"
    echo -e "  1. Inicia el sistema con:  ${YELLOW}./start.sh${NC}"
    echo -e "  2. Entra en tu navegador a: ${CYAN}http://localhost:3000${NC}"
    echo -e "  3. Haz clic en el botón:   ${BOLD}\"Vincular Dispositivo\"${NC}"
    echo -e "  4. Introduce tu ID:        ${GREEN}$DEVICE_ID${NC}"
    echo -e "  5. Introduce tu Clave:     ${GREEN}$DEVICE_PASS${NC}"
    echo -e "================================================================\n"
else
    echo -e "\n${RED}[ERROR]${NC} Falló la subida por USB a $SERIAL_PORT."
    echo -e "Verifica que el cable USB esté bien conectado y que tu usuario tenga permisos (dialout/uucp)."
    echo -e "Comando para dar permisos de puerto:  sudo chmod a+rw $SERIAL_PORT"
    log_audit "FLASH_ESP32_FAILED" "DeviceID=$DEVICE_ID Port=$SERIAL_PORT"
    exit 1
fi
