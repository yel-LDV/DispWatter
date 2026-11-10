#!/usr/bin/env bash
# ==============================================================================
# DispWatter - Script de Inicio Unificado (Backend WebSocket + Panel Frontend)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colores de salida
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
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

# 1. Comprobar entorno virtual de Python
PYTHON_BIN="$SCRIPT_DIR/backend/.venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
    echo -e "${RED}[ERROR]${NC} No se encontró el entorno virtual en backend/.venv"
    echo -e "Ejecuta: python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt"
    exit 1
fi

# 2. Verificar si el backend ya está corriendo
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

# 3. Verificar si el panel ya está corriendo
if [ -f "$PANEL_PID_FILE" ] && kill -0 "$(cat "$PANEL_PID_FILE")" 2>/dev/null; then
    echo -e "${YELLOW}[AVISO]${NC} El panel web ya está en ejecución (PID: $(cat "$PANEL_PID_FILE"))"
else
    echo -e "-> Arrancando Servidor de Panel Web en puerto 3000..."
    python3 -m http.server 3000 --directory "$SCRIPT_DIR/panel" > "$LOGS_DIR/panel.log" 2>&1 &
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

echo -e "\n------------------------------------------------------"
echo -e "${GREEN}✔ SERVICIOS DISPWATTER LISTOS Y ACTIVOS${NC}"
echo -e "------------------------------------------------------"
echo -e "  🌐 Panel de Control Web:   ${BLUE}http://localhost:3000${NC}"
echo -e "  🔌 WebSocket Hardware:     ${BLUE}ws://localhost:8765/ws/device${NC}"
echo -e "  🖥️  WebSocket Panel:        ${BLUE}ws://localhost:8765/ws/panel${NC}"
echo -e "  📋 Registro de Auditoría:  ${BLUE}$AUDIT_LOG_FILE${NC}"
echo -e "  📜 Logs del Sistema:       ${BLUE}$LOGS_DIR/${NC}"
echo -e "------------------------------------------------------\n"
echo -e "Para detener los servicios ejecuta:  ${YELLOW}./stop.sh${NC}\n"
