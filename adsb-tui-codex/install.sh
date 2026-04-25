#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${HOME}/adsb-tui-codex"
BIN_DIR="${HOME}/.local/bin"
RAW_BASE="${ADSB_TUI_CODEX_RAW_BASE:-https://raw.githubusercontent.com/FugginOld/code-projects/main/adsb-tui-codex}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Error: required command not found: $1" >&2
    exit 1
  }
}

install_file() {
  local name="$1"
  local dest="${APP_DIR}/${name}"
  if [[ -f "${name}" ]]; then
    cp "${name}" "${dest}"
    return 0
  fi
  curl -fsSL "${RAW_BASE}/${name}" -o "${dest}"
}

mkdir -p "${APP_DIR}" "${BIN_DIR}"
require_cmd curl

install_file "adsb_tui.py"
install_file "autotune.py"
install_file "config.json"
install_file "config.example.json"
install_file "adsb-tui.service"
install_file "README.md"

chmod +x "${APP_DIR}/adsb_tui.py" "${APP_DIR}/autotune.py"

cat > "${BIN_DIR}/adsb-tui-codex" <<'EOF'
#!/usr/bin/env bash
exec python3 "${HOME}/adsb-tui-codex/adsb_tui.py" "$@"
EOF

chmod +x "${BIN_DIR}/adsb-tui-codex"

cat <<'EOF'
Installed:
  app: ~/adsb-tui-codex/adsb_tui.py
  autotune: ~/adsb-tui-codex/autotune.py
  config: ~/adsb-tui-codex/config.json
  launcher: ~/.local/bin/adsb-tui-codex

If ~/.local/bin is not in PATH yet, run:
  export PATH="$HOME/.local/bin:$PATH"

Start the dashboard with:
  adsb-tui-codex
EOF
