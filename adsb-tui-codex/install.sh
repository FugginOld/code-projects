#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${HOME}/adsb-tui"
BIN_DIR="${HOME}/.local/bin"

mkdir -p "${APP_DIR}" "${BIN_DIR}"
cp adsb_tui.py "${APP_DIR}/adsb_tui.py"
chmod +x "${APP_DIR}/adsb_tui.py"

for extra in autotune.py config.json config.example.json adsb-tui.service README.md; do
  if [[ -f "${extra}" ]]; then
    cp "${extra}" "${APP_DIR}/${extra}"
  fi
done
if [[ -f "${APP_DIR}/autotune.py" ]]; then
  chmod +x "${APP_DIR}/autotune.py"
fi

cat > "${BIN_DIR}/adsb-tui" <<'EOF'
#!/usr/bin/env bash
exec python3 "${HOME}/adsb-tui/adsb_tui.py" "$@"
EOF

chmod +x "${BIN_DIR}/adsb-tui"

cat <<'EOF'
Installed:
  app: ~/adsb-tui/adsb_tui.py
  autotune: ~/adsb-tui/autotune.py
  config: ~/adsb-tui/config.json
  launcher: ~/.local/bin/adsb-tui

If ~/.local/bin is not in PATH yet, run:
  export PATH="$HOME/.local/bin:$PATH"

Start the dashboard with:
  adsb-tui
EOF
