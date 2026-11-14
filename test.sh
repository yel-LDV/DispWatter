#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

BACKEND=false
FIRMWARE=false
PANEL=false
SAVE=""

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "  --backend   Run backend WebSocket tests"
    echo "  --firmware  Compile firmware without flashing"
    echo "  --panel     Verify panel serves files"
    echo "  --all       Run all tests"
    echo "  --save NAME Save results to test_NAME.txt"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backend)  BACKEND=true; shift ;;
        --firmware) FIRMWARE=true; shift ;;
        --panel)    PANEL=true; shift ;;
        --all)      BACKEND=true; FIRMWARE=true; PANEL=true; shift ;;
        --save)     SAVE="$2"; shift 2 ;;
        -h|--help)  usage ;;
        *)          usage ;;
    esac
done

if ! $BACKEND && ! $FIRMWARE && ! $PANEL; then
    usage
fi

OUTPUT=""
PASS=0
FAIL=0

run_test() {
    local name="$1"
    local cmd="$2"
    echo -n "Testing $name... "
    if eval "$cmd" >> "$OUTPUT" 2>&1; then
        echo "PASS"
        echo "[PASS] $name" >> "$OUTPUT"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        echo "[FAIL] $name" >> "$OUTPUT"
        FAIL=$((FAIL + 1))
    fi
}

if [[ -n "$SAVE" ]]; then
    OUTPUT="test_${SAVE}.txt"
    echo "DispWatter Test Report" > "$OUTPUT"
    echo "Date: $(date)" >> "$OUTPUT"
    echo "---" >> "$OUTPUT"
fi

if $BACKEND; then
    echo "=== Backend Tests ==="
    if [[ -f test_backend_ws.sh ]]; then
        run_test "backend_websocket" "bash test_backend_ws.sh"
    else
        echo "SKIP (test_backend_ws.sh not found)"
    fi
    if [[ -f test_db.sh ]]; then
        run_test "backend_database" "bash test_db.sh"
    else
        echo "SKIP (test_db.sh not found)"
    fi
    run_test "backend_imports" "cd backend && source .venv/bin/activate && python -c 'from handlers.panel_handler import handle_panel_message; print(\"OK\")'"
fi

if $FIRMWARE; then
    echo "=== Firmware Tests ==="
    run_test "firmware_compile" "cd hardware/esp32/main && pio run -e esp32dev"
fi

if $PANEL; then
    echo "=== Panel Tests ==="
    run_test "panel_index" "test -f panel/index.html"
    run_test "panel_css" "test -f panel/css/styles.css"
    run_test "panel_js" "test -f panel/js/app.js"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
echo "" >> "$OUTPUT"
echo "Results: $PASS passed, $FAIL failed" >> "$OUTPUT"

if [[ -n "$SAVE" ]]; then
    echo "Results saved to $OUTPUT"
fi

if $FAIL; then
    exit 1
fi
