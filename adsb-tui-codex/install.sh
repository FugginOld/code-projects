#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${HOME}/adsb-tui"
BIN_DIR="${HOME}/.local/bin"

mkdir -p "${APP_DIR}" "${BIN_DIR}"
cp adsb_tui.py "${APP_DIR}/adsb_tui.py"
chmod +x "${APP_DIR}/adsb_tui.py"

cat > "${BIN_DIR}/adsb-tui" <<'EOF'
#!/usr/bin/env bash
exec python3 "${HOME}/adsb-tui/adsb_tui.py" "$@"
EOF

chmod +x "${BIN_DIR}/adsb-tui"

cat <<'EOF'
Installed:
  app: ~/adsb-tui/adsb_tui.py
  launcher: ~/.local/bin/adsb-tui

If ~/.local/bin is not in PATH yet, run:
  export PATH="$HOME/.local/bin:$PATH"

Start the dashboard with:
  adsb-tui
EOF
