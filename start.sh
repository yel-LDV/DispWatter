#!/usr/bin/env bash
# ==============================================================================
# DispWatter - Script de Inicio Unificado (Backend WebSocket + Panel Frontend)
# Auto-crea entorno virtual e instala dependencias si no existen.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colores de salida
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

PID_DIR="$SCRIPT_DIR/.pids"
LOGS_DIR="$SCRIPT_DIR/logs"
BACKEND_PID_FILE="$PID_DIR/backend.pid"
PANEL_PID_FILE="$PID_DIR/panel.pid"
AUDIT_LOG_FILE="$LOGS_DIR/audit.log"

mkdir -p "$PID_DIR" "$LOGS_DIR"

log_audit() {
    local action="$1"
    local details="$2"
    local now_iso
    now_iso="$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')"
    echo "[$now_iso] [AUDIT] [$action] Actor=$(whoami) Details=$details" >> "$AUDIT_LOG_FILE"
}

echo -e "\n${BLUE}======================================================${NC}"
echo -e "${BLUE}        INICIANDO SISTEMA DISPWATTER                  ${NC}"
echo -e "${BLUE}======================================================${NC}\n"

# 1. Verificar que Python 3 esté instalado
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[ERROR]${NC} Python 3 no está instalado."
    echo -e "Ejecuta: ${CYAN}sudo apt update && sudo apt install -y python3 python3-venv python3-pip${NC}"
    exit 1
fi

# 2. Verificar python3-venv
if ! python3 -m venv --help &>/dev/null 2>&1; then
    echo -e "${RED}[ERROR]${NC} python3-venv no está disponible."
    echo -e "Ejecuta: ${CYAN}sudo apt install -y python3.12-venv${NC}"
    exit 1
fi

# 3. Crear entorno virtual si no existe
PYTHON_BIN="$SCRIPT_DIR/backend/.venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
    echo -e "${YELLOW}[SETUP]${NC} Creando entorno virtual en backend/.venv..."
    python3 -m venv "$SCRIPT_DIR/backend/.venv"
    echo -e "   [${GREEN}OK${NC}] Entorno virtual creado."

    # Instalar dependencias
    echo -e "${YELLOW}[SETUP]${NC} Instalando dependencias de Python..."
    "$SCRIPT_DIR/backend/.venv/bin/pip" install --upgrade pip -q
    "$SCRIPT_DIR/backend/.venv/bin/pip" install -r "$SCRIPT_DIR/backend/requirements.txt" -q
    echo -e "   [${GREEN}OK${NC}] Dependencias instaladas."
else
    echo -e "${GREEN}[OK]${NC} Entorno virtual encontrado."
fi

# 4. Verificar si el backend ya está corriendo
if [ -f "$BACKEND_PID_FILE" ] && kill -0 "$(cat "$BACKEND_PID_FILE")" 2>/dev/null; then
    echo -e "${YELLOW}[AVISO]${NC} El backend ya está en ejecución (PID: $(cat "$BACKEND_PID_FILE"))"
else
    echo -e "-> Arrancando Backend WebSockets en puerto 8765..."
    "$PYTHON_BIN" -m backend.main > "$LOGS_DIR/backend.log" 2>&1 &
    BACKEND_PID=$!
    echo "$BACKEND_PID" > "$BACKEND_PID_FILE"
    sleep 1
    if kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo -e "   [${GREEN}OK${NC}] Backend iniciado con PID: $BACKEND_PID"
        log_audit "START_BACKEND" "PID=$BACKEND_PID Port=8765"
    else
        echo -e "   [${RED}ERROR${NC}] El backend falló al iniciar. Revisa $LOGS_DIR/backend.log"
        exit 1
    fi
fi

# 5. Verificar si el panel ya está corriendo
if [ -f "$PANEL_PID_FILE" ] && kill -0 "$(cat "$PANEL_PID_FILE")" 2>/dev/null; then
    echo -e "${YELLOW}[AVISO]${NC} El panel web ya está en ejecución (PID: $(cat "$PANEL_PID_FILE"))"
else
    echo -e "-> Arrancando Servidor de Panel Web en puerto 3000..."
    python3 "$SCRIPT_DIR/panel_server.py" > "$LOGS_DIR/panel.log" 2>&1 &
    PANEL_PID=$!
    echo "$PANEL_PID" > "$PANEL_PID_FILE"
    sleep 1
    if kill -0 "$PANEL_PID" 2>/dev/null; then
        echo -e "   [${GREEN}OK${NC}] Panel iniciado con PID: $PANEL_PID"
        log_audit "START_PANEL" "PID=$PANEL_PID Port=3000"
    else
        echo -e "   [${RED}ERROR${NC}] El panel falló al iniciar. Revisa $LOGS_DIR/panel.log"
        exit 1
    fi
fi

# 6. Obtener IP pública
PUBLIC_IP=""
for cmd in curl wget;
do
    if command -v "$cmd" &>/dev/null; then
        if [ "$cmd" = "curl" ]; then
            PUBLIC_IP=$(curl -s --max-time 3 https://api.ipify.org 2>/dev/null || true)
        else
            PUBLIC_IP=$(wget -qO- --timeout=3 https://api.ipify.org 2>/dev/null || true)
        fi
        break
    fi
done

echo -e "\n------------------------------------------------------"
echo -e "${GREEN}✔ SERVICIOS DISPWATTER LISTOS Y ACTIVOS${NC}"
echo -e "------------------------------------------------------"

if [ -n "$PUBLIC_IP" ]; then
    echo -e "  🌍 IP Pública:              ${CYAN}$PUBLIC_IP${NC}"
    echo -e "  🌐 Panel (remoto):          ${BLUE}http://$PUBLIC_IP:3000${NC}"
    echo -e "  🔌 WebSocket (remoto):      ${BLUE}ws://$PUBLIC_IP:8765${NC}"
fi

echo -e "  🌐 Panel (local):           ${BLUE}http://localhost:3000${NC}"
echo -e "  🔌 WebSocket Hardware:      ${BLUE}ws://localhost:8765/ws/device${NC}"
echo -e "  🖥️  WebSocket Panel:         ${BLUE}ws://localhost:8765/ws/panel${NC}"
echo -e "  📋 Registro de Auditoría:   ${BLUE}$AUDIT_LOG_FILE${NC}"
echo -e "  📜 Logs del Sistema:        ${BLUE}$LOGS_DIR/${NC}"
echo -e "------------------------------------------------------\n"
echo -e "Para detener los servicios ejecuta:  ${YELLOW}./stop.sh${NC}\n"
