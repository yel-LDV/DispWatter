#!/usr/bin/env bash
# ==============================================================================
# DispWatter - instalación de servicios systemd, helper y sudoers
# ==============================================================================
# Uso:
#   sudo ./deploy/install.sh [--user USUARIO] [--dir RUTA_REPOSITORIO]
#
# No crea backend/.env ni el entorno virtual. Consulta deploy/README.md.
# ==============================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SERVICE_USER="${SUDO_USER:-$(id -un)}"
SERVICE_GROUP="$(id -gn "$SERVICE_USER")"

usage() {
    cat <<'EOF'
Uso: sudo ./deploy/install.sh [opciones]

Opciones:
  --user USUARIO   Usuario que ejecutará los servicios (por defecto: SUDO_USER)
  --dir RUTA       Ruta del repositorio (por defecto: directorio padre de deploy/)
  -h, --help       Muestra esta ayuda
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --user) SERVICE_USER="${2:?Falta el usuario}"; shift 2 ;;
        --dir) REPO_DIR="$(cd "${2:?Falta la ruta}" && pwd)"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Opción desconocida: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "Ejecuta este script con sudo." >&2
    exit 1
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    echo "El usuario $SERVICE_USER no existe." >&2
    exit 1
fi

SERVICE_GROUP="$(id -gn "$SERVICE_USER")"

if [ ! -x "$REPO_DIR/backend/.venv/bin/python" ]; then
    echo "AVISO: no existe $REPO_DIR/backend/.venv/bin/python" >&2
    echo "Crea el entorno antes de arrancar el backend (ver deploy/README.md)." >&2
fi

if [ ! -f "$REPO_DIR/backend/.env" ]; then
    echo "AVISO: no existe $REPO_DIR/backend/.env; el backend no arrancará." >&2
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

render() {
    local source="$1"
    local target="$2"
    sed \
        -e "s#/home/angedl_/Proyectos/DispWatter#$REPO_DIR#g" \
        -e "s#^User=angedl_\$#User=$SERVICE_USER#" \
        -e "s#^Group=angedl_\$#Group=$SERVICE_GROUP#" \
        -e "s#^angedl_ ALL=#${SERVICE_USER} ALL=#" \
        "$source" > "$target"
}

render "$SCRIPT_DIR/dispwatter-backend.service" "$tmp_dir/dispwatter-backend.service"
render "$SCRIPT_DIR/dispwatter-panel.service" "$tmp_dir/dispwatter-panel.service"
render "$SCRIPT_DIR/sudoers.d/dispwatter" "$tmp_dir/dispwatter.sudoers"

install -o root -g root -m 0755 "$SCRIPT_DIR/dispwatter-ctl" /usr/local/bin/dispwatter-ctl
install -o root -g root -m 0644 "$tmp_dir/dispwatter-backend.service" /etc/systemd/system/dispwatter-backend.service
install -o root -g root -m 0644 "$tmp_dir/dispwatter-panel.service" /etc/systemd/system/dispwatter-panel.service
install -o root -g root -m 0440 "$tmp_dir/dispwatter.sudoers" /etc/sudoers.d/dispwatter

if ! visudo -c >/dev/null; then
    echo "La configuración de sudoers no es válida. Revisa /etc/sudoers.d/dispwatter" >&2
    exit 1
fi

systemctl daemon-reload
systemctl enable dispwatter-backend.service dispwatter-panel.service >/dev/null

cat <<EOF
Instalación completada.

  Usuario:  $SERVICE_USER ($SERVICE_GROUP)
  Repositorio: $REPO_DIR

Siguientes pasos:
  1. Revisa $REPO_DIR/backend/.env
  2. sudo systemctl restart dispwatter-backend.service dispwatter-panel.service
  3. sudo -u $SERVICE_USER sudo -n /usr/local/bin/dispwatter-ctl status
  4. Abre http://localhost:3000
EOF
