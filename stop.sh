#!/usr/bin/env bash
# ==============================================================================
# DispWatter - Script de Parada Unificado
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

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

log_audit() {
    local action="$1"
    local details="$2"
    local now_iso
    now_iso="$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')"
    echo "[$now_iso] [AUDIT] [$action] Actor=$(whoami) Details=$details" >> "$AUDIT_LOG_FILE"
}

echo -e "\n${BLUE}======================================================${NC}"
echo -e "${BLUE}        DETENIENDO SERVICIOS DISPWATTER               ${NC}"
echo -e "${BLUE}======================================================${NC}\n"

stop_process() {
    local name="$1"
    local pid_file="$2"

    if [ -f "$pid_file" ]; then
        local pid
        pid="$(cat "$pid_file")"
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "-> Deteniendo $name (PID: $pid)..."
            kill -15 "$pid" 2>/dev/null || true
            sleep 1
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
            echo -e "   [${GREEN}OK${NC}] $name detenido."
            log_audit "STOP_$name" "PID=$pid"
        else
            echo -e "   [${YELLOW}AVISO${NC}] El proceso de $name ya no estaba activo."
        fi
        rm -f "$pid_file"
    else
        echo -e "   [INFO] No hay archivo PID para $name."
    fi
}

# 1. Detener Backend
stop_process "BACKEND" "$BACKEND_PID_FILE"

# 2. Detener Panel
stop_process "PANEL" "$PANEL_PID_FILE"

# 3. Limpieza de procesos huérfanos residuales en los puertos si quedaran
if command -v fuser &>/dev/null; then
    fuser -k 8765/tcp 2>/dev/null || true
    fuser -k 3000/tcp 2>/dev/null || true
elif command -v lsof &>/dev/null; then
    lsof -ti:8765 2>/dev/null | xargs kill -9 2>/dev/null || true
    lsof -ti:3000 2>/dev/null | xargs kill -9 2>/dev/null || true
else
    echo -e "   [${YELLOW}AVISO${NC}] fuser/lsof no disponibles, saltando limpieza de puertos."
fi

echo -e "\n${GREEN}✔ Todos los servicios de DispWatter han sido apagados.${NC}\n"
