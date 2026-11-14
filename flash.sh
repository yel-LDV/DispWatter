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
  --version TAG       Flashea una versión específica desde GitHub (ej: v1.0.0).
  --list-versions     Muestra las versiones disponibles en GitHub y sale.
  --non-interactive   Usa device_config.json tal cual, sin preguntas
                      (conserva la config del ESP32 salvo --reset-config).
  --reset-config      Fuerza la subida de data/config.json al ESP32.
  --fresh             Ignora la configuración del host y la recrea.
  --host HOST:PORT    Notifica al backend que se compiló el firmware local.
                      Solo envía device_id y secreto para registro (ej: --host 192.168.1.100:8765).
  --username USER     Usuario del panel (con --host).
  --password PASS     Contraseña del panel (con --host).
  -h, --help          Muestra esta ayuda.

Por defecto:
  - La primera vez crea hardware/esp32/main/device_config.json.
  - Las siguientes veces pregunta si se conserva la config del ESP32.
  - Las redes WiFi se guardan en orden de prioridad (la primera manda).

Ejemplos:
  ./flash.sh                      Compila y flashea el código local por USB.
  ./flash.sh --version v1.0.0     Flashea la versión v1.0.0 desde GitHub.
  ./flash.sh --list-versions      Lista las versiones disponibles.
  ./flash.sh --host 192.168.1.100:8765 --username admin --password secret
                                  Compila y notifica al backend que el dispositivo existe.
EOF
}

BUILD_ONLY=0
NON_INTERACTIVE=0
RESET_CONFIG=0
FRESH=0
FLASH_VERSION=""
LIST_VERSIONS=0
REMOTE_HOST=""
REMOTE_USERNAME=""
REMOTE_PASSWORD=""

while [ $# -gt 0 ]; do
    case "$1" in
        --build-only) BUILD_ONLY=1 ;;
        --version) FLASH_VERSION="$2"; shift ;;
        --list-versions) LIST_VERSIONS=1 ;;
        --non-interactive) NON_INTERACTIVE=1 ;;
        --reset-config) RESET_CONFIG=1 ;;
        --fresh) FRESH=1 ;;
        --host) REMOTE_HOST="$2"; shift ;;
        --username) REMOTE_USERNAME="$2"; shift ;;
        --password) REMOTE_PASSWORD="$2"; shift ;;
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

# ------------------------------------------------------------------------------
# GitHub Releases — obtener versiones y descargar firmware
# ------------------------------------------------------------------------------
GITHUB_REPO="yel-LDV/DispWatter"

list_github_versions() {
    local json_data=""
    if command -v gh >/dev/null 2>&1; then
        json_data=$(gh release list --repo "$GITHUB_REPO" --limit 50 --json tagName,publishedAt,isPrerelease 2>/dev/null)
    else
        json_data=$(curl -s "https://api.github.com/repos/$GITHUB_REPO/releases?per_page=50" 2>/dev/null)
    fi
    [ -z "$json_data" ] && return
    echo "$json_data" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data:
    tag = r.get('tagName', r.get('tag_name', ''))
    date = ''
    pa = r.get('publishedAt', r.get('published_at', ''))
    if pa:
        date = pa[:10]
    pre = '1' if r.get('isPrerelease', r.get('prerelease', False)) else '0'
    print(f'{tag}|{date}|{pre}|github')
" 2>/dev/null
}

download_firmware_for_version() {
    local version="$1"
    local output_dir="$2"
    local firmware_file=""

    echo "" >&2
    info "-> Descargando firmware $version desde GitHub..." >&2

    # Buscar el archivo .bin en el release
    if command -v gh >/dev/null 2>&1; then
        gh release download "$version" --repo "$GITHUB_REPO" --pattern '*.bin' --dir "$output_dir" >/dev/null 2>&1
        firmware_file=$(find "$output_dir" -name '*.bin' -type f 2>/dev/null | head -1)
        if [ -z "$firmware_file" ]; then
            # Intentar descargar todos los assets
            gh release download "$version" --repo "$GITHUB_REPO" --dir "$output_dir" >/dev/null 2>&1
            firmware_file=$(find "$output_dir" -name '*.bin' -type f 2>/dev/null | head -1)
        fi
    else
        # Usar curl para descargar
        local assets
        assets=$(curl -s "https://api.github.com/repos/$GITHUB_REPO/releases/tags/$version" 2>/dev/null)
        local bin_url
        bin_url=$(echo "$assets" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for a in data.get('assets', []):
    if a['name'].endswith('.bin'):
        print(a['browser_download_url'])
        break
" 2>/dev/null)
        if [ -n "$bin_url" ]; then
            local bin_name
            bin_name=$(basename "$bin_url")
            curl -sL -o "$output_dir/$bin_name" "$bin_url"
            firmware_file="$output_dir/$bin_name"
        fi
    fi

    # Si no encontró .bin, buscar cualquier archivo del release
    if [ -z "$firmware_file" ] || [ ! -f "$firmware_file" ]; then
        die "No se encontró archivo .bin en el release $version"
    fi

    echo "$firmware_file"
}

# ------------------------------------------------------------------------------
# Flash desde binario (sin compilar)
# ------------------------------------------------------------------------------
flash_from_binary() {
    local firmware_file="$1"
    local serial_port="$2"

    echo ""
    info "-> Flasheando firmware desde binario..."
    info "  Archivo: $firmware_file"
    info "  Puerto: $serial_port"

    # Detectar el offset del firmware (por defecto 0x10000 para ESP32)
    local offset="0x10000"

    # Usar esptool.py para flashear
    if command -v esptool >/dev/null 2>&1; then
        esptool.py --port "$serial_port" write_flash "$offset" "$firmware_file"
    elif command -v pio >/dev/null 2>&1; then
        # Usar PlatformIO para flashear el binario
        pio run -d "$PIO_PROJECT" --target upload --upload-port "$serial_port" --upload-file "$firmware_file"
    else
        die "Se requiere esptool.py o PlatformIO para flashear desde binario"
    fi

    ok "Firmware flasheado exitosamente."
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

# Detección de IP temprana para modo remoto
DETECTED_IP="$(detect_ip)"

# ------------------------------------------------------------------------------
# Modo: flash remoto (--host)
# ------------------------------------------------------------------------------
if [ -n "$REMOTE_HOST" ]; then
    echo -e "${BOLD}Modo remoto: notificar compilación al backend${NC}\n"
    echo -e "  Backend:     ${GREEN}${REMOTE_HOST}${NC}"
    
    # Validar credenciales
    if [ -z "$REMOTE_USERNAME" ] || [ -z "$REMOTE_PASSWORD" ]; then
        die "Modo --host requiere --username y --password."
    fi

    # Verificar que el script de remote flash exista
    REMOTE_FLASH_SCRIPT="$SCRIPT_DIR/scripts/remote_flash.py"
    [ -f "$REMOTE_FLASH_SCRIPT" ] || die "No se encuentra $REMOTE_FLASH_SCRIPT"

    # Verificar python3
    command -v python3 >/dev/null 2>&1 || die "Falta python3."

    # Configurar device_config.json (silencioso, non-interactive)
    echo ""
    info "-> Configurando device_config.json..."
    CONFIGURE_ARGS=(configure --file "$HOST_CONFIG" --default-host "$DETECTED_IP" --non-interactive)
    [ "$FRESH" -eq 1 ] && CONFIGURE_ARGS+=(--reset)
    python3 "$CONFIG_HELPER" "${CONFIGURE_ARGS[@]}"

    # Compilar firmware
    echo ""
    info "-> Compilando firmware con PlatformIO..."
    log_audit "FLASH_REMOTE_START" "Host=$REMOTE_HOST"

    if ! pio run -d "$PIO_PROJECT"; then
        log_audit "BUILD_ESP32_FAILED" "Config=$HOST_CONFIG"
        die "La compilación falló. Revisa la salida anterior."
    fi
    ok "Compilación completada."

    # Leer device_config.json para obtener device_id, key_hash, nombre, ubicación y versión
    if [ ! -f "$HOST_CONFIG" ]; then
        die "No se encuentra $HOST_CONFIG después de configurar."
    fi

    DEVICE_ID=$(python3 -c "import json; d=json.load(open('$HOST_CONFIG')); print(d['device']['id'])")
    DEVICE_NAME=$(python3 -c "import json; d=json.load(open('$HOST_CONFIG')); print(d['device'].get('name',''))")
    DEVICE_LOCATION=$(python3 -c "import json; d=json.load(open('$HOST_CONFIG')); print(d['device'].get('location',''))")
    FIRMWARE_VERSION=$(python3 -c "import json; d=json.load(open('$HOST_CONFIG')); print(d['device'].get('firmware','1.0.0'))")
    KEY_HASH=$(python3 -c "import json; d=json.load(open('$HOST_CONFIG')); print(d['device'].get('key_hash',''))")

    if [ -z "$DEVICE_ID" ] || [ -z "$KEY_HASH" ]; then
        die "device_id o key_hash no encontrados en $HOST_CONFIG."
    fi

    echo ""
    info "-> Notificando compilación al backend..."
    info "  Dispositivo: $DEVICE_ID"
    info "  Versión:     $FIRMWARE_VERSION"

    # Construir argumentos para remote_flash.py
    REMOTE_ARGS=(
        --host "$REMOTE_HOST"
        --username "$REMOTE_USERNAME"
        --password "$REMOTE_PASSWORD"
        --device-id "$DEVICE_ID"
        --key-hash "$KEY_HASH"
        --firmware-version "$FIRMWARE_VERSION"
    )

    if [ -n "$DEVICE_NAME" ]; then
        REMOTE_ARGS+=(--device-name "$DEVICE_NAME")
    fi

    if [ -n "$DEVICE_LOCATION" ]; then
        REMOTE_ARGS+=(--device-location "$DEVICE_LOCATION")
    fi

    # Ejecutar script de notificación
    if ! python3 "$REMOTE_FLASH_SCRIPT" "${REMOTE_ARGS[@]}"; then
        log_audit "FLASH_REMOTE_FAILED" "Host=$REMOTE_HOST"
        die "Falló la notificación de compilación al backend remoto."
    fi

    log_audit "FLASH_REMOTE_SUCCESS" "Host=$REMOTE_HOST Device=$DEVICE_ID"

    echo -e "\n${GREEN}================================================================${NC}"
    echo -e "${GREEN}${BOLD}       COMPILACIÓN NOTIFICADA AL BACKEND                         ${NC}"
    echo -e "${GREEN}================================================================${NC}"
    echo -e "  Backend:     ${GREEN}${REMOTE_HOST}${NC}"
    echo -e "  Dispositivo: ${GREEN}${DEVICE_ID}${NC}"
    echo -e "  Versión:     ${GREEN}${FIRMWARE_VERSION}${NC}"
    echo ""
    echo -e "  El backend ahora conoce este dispositivo y su secreto."
    echo -e "  Cuando el ESP32 se conecte, podrá autenticarse."
    echo ""
    exit 0
fi

# ------------------------------------------------------------------------------
# Modo: listar versiones
# ------------------------------------------------------------------------------
if [ "$LIST_VERSIONS" -eq 1 ]; then
    echo -e "${BOLD}Versiones disponibles en GitHub:${NC}\n"
    local_versions=$(list_github_versions)
    if [ -z "$local_versions" ]; then
        warn "No se pudieron obtener las versiones (verifica conexión a Internet)."
        exit 1
    fi
    echo "$local_versions" | while IFS='|' read -r tag date prerelease author; do
        [ -z "$tag" ] && continue
        type_mark=""
        if [ "$prerelease" = "1" ]; then
            type_mark=" ${YELLOW}(experimental)${NC}"
        fi
        echo -e "  ${GREEN}${tag}${NC}  ${CYAN}${date}${NC}  ${author}${type_mark}"
    done
    echo ""
    exit 0
fi

# ------------------------------------------------------------------------------
# Modo: flashear versión desde GitHub
# ------------------------------------------------------------------------------
if [ -n "$FLASH_VERSION" ]; then
    echo -e "${BOLD}Flasheando versión: ${GREEN}${FLASH_VERSION}${NC}${BOLD} desde GitHub${NC}\n"

    # Descargar el firmware
    TMP_DIR=$(mktemp -d)
    trap "rm -rf '$TMP_DIR'" EXIT
    FIRMWARE_FILE=$(download_firmware_for_version "$FLASH_VERSION" "$TMP_DIR")

    # Puerto serie
    mapfile -t DETECTED_PORTS < <(detect_ports)
    DEFAULT_PORT="/dev/ttyUSB0"
    if [ ${#DETECTED_PORTS[@]} -gt 0 ]; then
        DEFAULT_PORT="${DETECTED_PORTS[0]}"
        echo -e "  Puertos detectados: ${GREEN}${DETECTED_PORTS[*]}${NC}"
    fi
    read -rp "  Puerto para flashear [$DEFAULT_PORT]: " INPUT_PORT
    SERIAL_PORT="${INPUT_PORT:-$DEFAULT_PORT}"
    validate_serial_port "$SERIAL_PORT"

    # Flashear
    flash_from_binary "$FIRMWARE_FILE" "$SERIAL_PORT"
    log_audit "FLASH_GITHUB_VERSION" "Version=$FLASH_VERSION Port=$SERIAL_PORT File=$FIRMWARE_FILE"

    echo -e "\n${GREEN}================================================================${NC}"
    echo -e "${GREEN}${BOLD}       FIRMWARE ${FLASH_VERSION} FLASHEADO EXITOSAMENTE              ${NC}"
    echo -e "${GREEN}================================================================${NC}"
    echo -e "  Versión:     ${GREEN}${FLASH_VERSION}${NC}"
    echo -e "  Puerto:      ${GREEN}${SERIAL_PORT}${NC}\n"
    exit 0
fi

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
