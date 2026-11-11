#!/usr/bin/env bash
# ==============================================================================
# DispWatter - Configuración y flasheo de ESP32
# ==============================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PIO_PROJECT="$SCRIPT_DIR/hardware/esp32/main"
HOST_CONFIG="$PIO_PROJECT/device_config.json"
DEVICE_CONFIG="$PIO_PROJECT/data/config.json"
CONFIG_HELPER="$SCRIPT_DIR/scripts/device_config.py"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

LOGS_DIR="$SCRIPT_DIR/logs"
AUDIT_LOG_FILE="$LOGS_DIR/audit.log"
mkdir -p "$LOGS_DIR" "$PIO_PROJECT/data"

log_audit() {
    local action="$1"
    local details="$2"
    local now_iso
    now_iso="$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')"
    echo "[$now_iso] [AUDIT] [$action] Actor=$(whoami) Details=$details" >> "$AUDIT_LOG_FILE"
}

die() {
    echo -e "\n${RED}[ERROR]${NC} $*" >&2
    exit 1
}

info() { echo -e "${CYAN}$*${NC}"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[AVISO]${NC} $*"; }

usage() {
    cat <<'EOF'
Uso: ./flash.sh [opciones]

Opciones:
  --build-only        Compila el firmware sin subirlo.
  --non-interactive   Usa device_config.json tal cual, sin preguntas
                      (conserva la config del ESP32 salvo --reset-config).
  --reset-config      Fuerza la subida de data/config.json al ESP32.
  --fresh             Ignora la configuración del host y la recrea.
  -h, --help          Muestra esta ayuda.

Por defecto:
  - La primera vez crea hardware/esp32/main/device_config.json.
  - Las siguientes veces pregunta si se conserva la config del ESP32.
  - Las redes WiFi se guardan en orden de prioridad (la primera manda).
EOF
}

BUILD_ONLY=0
NON_INTERACTIVE=0
RESET_CONFIG=0
FRESH=0

while [ $# -gt 0 ]; do
    case "$1" in
        --build-only) BUILD_ONLY=1 ;;
        --non-interactive) NON_INTERACTIVE=1 ;;
        --reset-config) RESET_CONFIG=1 ;;
        --fresh) FRESH=1 ;;
        -h|--help) usage; exit 0 ;;
        *) die "Opción desconocida: $1 (usa --help)" ;;
    esac
    shift
done

# ------------------------------------------------------------------------------
# Detección de entorno
# ------------------------------------------------------------------------------
detect_ip() {
    local ip=""
    if command -v ip >/dev/null 2>&1; then
        ip="$(ip route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')"
    fi
    if [ -z "$ip" ]; then
        ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    fi
    printf '%s' "${ip:-192.168.1.100}"
}

check_dependencies() {
    command -v python3 >/dev/null 2>&1 || die "Falta python3."
    command -v pio >/dev/null 2>&1 || die "Falta PlatformIO (pio). Instálalo antes de flashear."
    [ -f "$CONFIG_HELPER" ] || die "No se encuentra $CONFIG_HELPER"
}

detect_ports() {
    local -a ports=()
    while IFS= read -r port; do
        [ -n "$port" ] && ports+=("$port")
    done < <(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true)
    if [ ${#ports[@]} -gt 0 ]; then
        printf '%s\n' "${ports[@]}"
    fi
}

validate_serial_port() {
    local port="$1"
    [ -e "$port" ] || die "El puerto $port no existe."
    [ -w "$port" ] || die "Sin permisos de escritura en $port. Añade tu usuario al grupo dialout/uucp o ejecuta: sudo chmod a+rw $port"
}

# ------------------------------------------------------------------------------
# Inicio
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}================================================================${NC}"
echo -e "${BLUE}${BOLD}      DISPWATTER - CONFIGURACIÓN Y FLASHEO DEL ESP32             ${NC}"
echo -e "${BLUE}================================================================${NC}\n"

check_dependencies

DETECTED_IP="$(detect_ip)"
HAD_CONFIG=0
[ -f "$HOST_CONFIG" ] && HAD_CONFIG=1

if [ "$BUILD_ONLY" -eq 1 ] && [ ! -f "$HOST_CONFIG" ]; then
    die "Modo --build-only requiere una configuración existente en $HOST_CONFIG"
fi

# ------------------------------------------------------------------------------
# Configuración (device_config.json)
# ------------------------------------------------------------------------------
CONFIGURE_ARGS=(configure --file "$HOST_CONFIG" --default-host "$DETECTED_IP")
[ "$NON_INTERACTIVE" -eq 1 ] && CONFIGURE_ARGS+=(--non-interactive)
[ "$FRESH" -eq 1 ] && CONFIGURE_ARGS+=(--reset)

if [ "$BUILD_ONLY" -eq 0 ] || [ "$HAD_CONFIG" -eq 0 ]; then
    python3 "$CONFIG_HELPER" "${CONFIGURE_ARGS[@]}"
else
    python3 "$CONFIG_HELPER" validate --file "$HOST_CONFIG"
fi

# ------------------------------------------------------------------------------
# Decisión de sembrar la configuración del dispositivo
# ------------------------------------------------------------------------------
SEED_DEVICE=0
if [ "$HAD_CONFIG" -eq 0 ] || [ "$FRESH" -eq 1 ]; then
    SEED_DEVICE=1
elif [ "$RESET_CONFIG" -eq 1 ]; then
    SEED_DEVICE=1
elif [ "$BUILD_ONLY" -eq 0 ] && [ "$NON_INTERACTIVE" -eq 0 ]; then
    if ! command -v python3 >/dev/null 2>&1; then
        die "python3 es necesario para leer la configuración."
    fi
    echo ""
    echo -e "${YELLOW}La configuración del ESP32 puede contener redes añadidas desde el panel.${NC}"
    read -rp "¿Sobrescribirla con la configuración de este PC? (s/N): " SEED_ANSWER
    if [[ "$SEED_ANSWER" =~ ^[sSyY]$ ]]; then
        SEED_DEVICE=1
    fi
fi

if [ "$SEED_DEVICE" -eq 1 ]; then
    python3 "$CONFIG_HELPER" to-device --input "$HOST_CONFIG" --output "$DEVICE_CONFIG"
    ok "Configuración del dispositivo generada: $DEVICE_CONFIG"
else
    info "Se conservará la configuración actual del ESP32 (no se sube LittleFS)."
fi

# ------------------------------------------------------------------------------
# Compilación
# ------------------------------------------------------------------------------
echo ""
info "-> Compilando firmware con PlatformIO..."
log_audit "FLASH_ESP32_START" "Config=$HOST_CONFIG SeedDevice=$SEED_DEVICE"

if ! pio run -d "$PIO_PROJECT"; then
    log_audit "BUILD_ESP32_FAILED" "Config=$HOST_CONFIG"
    die "La compilación falló. Revisa la salida anterior."
fi
ok "Compilación completada."
log_audit "BUILD_ESP32_SUCCESS" "Config=$HOST_CONFIG"

if [ "$BUILD_ONLY" -eq 1 ]; then
    echo -e "\n${GREEN}Modo --build-only completado.${NC}\n"
    exit 0
fi

# ------------------------------------------------------------------------------
# Puerto serie
# ------------------------------------------------------------------------------
mapfile -t DETECTED_PORTS < <(detect_ports)
DEFAULT_PORT="/dev/ttyUSB0"
if [ ${#DETECTED_PORTS[@]} -gt 0 ]; then
    DEFAULT_PORT="${DETECTED_PORTS[0]}"
    echo -e "  Puertos detectados: ${GREEN}${DETECTED_PORTS[*]}${NC}"
fi
read -rp "  Puerto para flashear [$DEFAULT_PORT]: " INPUT_PORT
SERIAL_PORT="${INPUT_PORT:-$DEFAULT_PORT}"
validate_serial_port "$SERIAL_PORT"

# ------------------------------------------------------------------------------
# Subida
# ------------------------------------------------------------------------------
echo ""
info "-> Subiendo firmware a $SERIAL_PORT..."
if ! pio run -d "$PIO_PROJECT" --target upload --upload-port "$SERIAL_PORT"; then
    log_audit "FLASH_ESP32_FAILED" "Port=$SERIAL_PORT Config=$HOST_CONFIG"
    die "Falló la subida del firmware. Verifica el cable USB y los permisos."
fi

if [ "$SEED_DEVICE" -eq 1 ]; then
    echo ""
    info "-> Subiendo configuración (LittleFS)..."
    if ! pio run -d "$PIO_PROJECT" --target uploadfs --upload-port "$SERIAL_PORT"; then
        log_audit "FLASH_ESP32_FAILED" "Port=$SERIAL_PORT Stage=uploadfs"
        die "Falló la subida de LittleFS. El firmware está flasheado, pero sin configuración."
    fi
    ok "Configuración subida al ESP32."
fi

log_audit "FLASH_ESP32_SUCCESS" "Port=$SERIAL_PORT Config=$HOST_CONFIG SeedDevice=$SEED_DEVICE"

echo -e "\n${GREEN}================================================================${NC}"
echo -e "${GREEN}${BOLD}       ESP32 FLASHEADO Y LISTO PARA OPERAR                       ${NC}"
echo -e "${GREEN}================================================================${NC}"
if [ "$SEED_DEVICE" -eq 1 ]; then
    echo -e "  Configuración: ${GREEN}subida (LittleFS)${NC}"
else
    echo -e "  Configuración: ${GREEN}conservada del dispositivo${NC}"
fi
echo -e "  Backend:       ${BLUE}ws://<host>:8765/ws/device${NC}"
echo -e "  Panel:         ${BLUE}http://localhost:3000${NC}"
echo -e "\n  Para vincular el dispositivo necesitas el secreto guardado en:"
echo -e "  ${CYAN}$HOST_CONFIG${NC} (campo device.claim_secret)\n"
