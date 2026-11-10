#!/usr/bin/env bash
# ==============================================================================
# DispWatter - Script de Reinicialización y Borrado Seguro de Base de Datos
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="$SCRIPT_DIR/backend/.venv/bin/python"
LOGS_DIR="$SCRIPT_DIR/logs"
AUDIT_LOG_FILE="$LOGS_DIR/audit.log"

mkdir -p "$LOGS_DIR"

log_audit() {
    local action="$1"
    local details="$2"
    local now_iso
    now_iso="$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')"
    echo "[$now_iso] [AUDIT] [$action] Actor=$(whoami) Details=$details" >> "$AUDIT_LOG_FILE"
}

log_audit "RESET_DB_CLI_START" "Invocación de reseteo con argumentos: $*"

"$PYTHON_BIN" -m backend.reset_db "$@"
STATUS=$?

if [ $STATUS -eq 0 ]; then
    log_audit "RESET_DB_CLI_SUCCESS" "Base de datos reiniciada correctamente"
else
    log_audit "RESET_DB_CLI_ABORTED" "Operación de reseteo abortada o fallida"
fi

exit $STATUS
