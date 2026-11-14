#!/usr/bin/env bash
# release_ota.sh — Compilar firmware y crear release en GitHub para OTA
# Uso: ./scripts/release_ota.sh <version> [stable|experimental]
#
# Ejemplo:
#   ./scripts/release_ota.sh 1.1.1 experimental
#   ./scripts/release_ota.sh 2.0.0 stable

set -euo pipefail

VERSION="${1:?Uso: $0 <version> [stable|experimental]}"
TYPE="${2:-experimental}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIRMWARE_DIR="$REPO_ROOT/hardware/esp32/main"
BUILD_DIR="$FIRMWARE_DIR/.pio/build/esp32dev"
GITHUB_REPO="yel-LDV/DispWatter"

echo "=== OTA Release: v${VERSION} (${TYPE}) ==="

# 1. Compilar firmware
echo "[1/4] Compilando firmware..."
cd "$FIRMWARE_DIR"
pio run --environment esp32dev

# 2. Obtener commit actual
cd "$REPO_ROOT"
COMMIT="$(git log --oneline -1 --format='%h')"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "[2/4] Commit: ${COMMIT}, Rama: ${BRANCH}"

# 3. Crear metadata.json
echo "[3/4] Generando metadata.json..."
cat > "$BUILD_DIR/metadata.json" <<EOF
{
  "version": "${VERSION}",
  "branch": "${BRANCH}",
  "commit": "${COMMIT}",
  "type": "${TYPE}",
  "is_fork": false,
  "release_notes": "Firmware v${VERSION} (${TYPE}) desde rama ${BRANCH}."
}
EOF

# 4. Crear release en GitHub
echo "[4/4] Creando release en GitHub..."
PRERELEASE_FLAG=""
if [ "$TYPE" = "experimental" ]; then
    PRERELEASE_FLAG="--prerelease"
fi

gh release create "v${VERSION}" \
  "$BUILD_DIR/firmware.bin" \
  "$BUILD_DIR/metadata.json" \
  --title "v${VERSION}" \
  $PRERELEASE_FLAG \
  --notes "## v${VERSION} (${TYPE^})

**Rama:** ${BRANCH}
**Commit:** ${COMMIT}

**Tipo:** ${TYPE^}" \
  2>&1

echo ""
echo "✅ Release v${VERSION} creado: https://github.com/${GITHUB_REPO}/releases/tag/v${VERSION}"
