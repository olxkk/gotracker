#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/anime-manga-tracker"
SERVICE_NAME="anime-tracker"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo bash deploy/setup_ubuntu.sh"
  exit 1
fi
if [[ ! -f "$APP_DIR/bot.py" || ! -f "$APP_DIR/requirements.txt" ]]; then
  echo "Project files must be placed in $APP_DIR first. Copy the project there, then rerun this script."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip python3-dev build-essential ca-certificates git sqlite3 ufw

PYTHON_BIN="$(command -v python3)"
PYTHON_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Python 3.11+ is required; found $PYTHON_VERSION. Use Ubuntu 24.04 LTS or install a supported Python release."
  exit 1
fi

if ! id animebot >/dev/null 2>&1; then
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin animebot
fi
mkdir -p "$APP_DIR/data"
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip wheel
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

if [[ -f "$APP_DIR/.env" ]]; then
  :
else
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo "Created $APP_DIR/.env from the example. Edit it and set DISCORD_TOKEN before starting the service."
fi

# Keep application code and the virtual environment immutable to the service account.
# The service only needs write access to its data directory; dotenv also reads .env,
# so grant the service group read access without making the secret world-readable.
chown -R root:root "$APP_DIR"
chown -R animebot:animebot "$APP_DIR/data"
chmod 750 "$APP_DIR/data"
chown root:animebot "$APP_DIR/.env"
chmod 640 "$APP_DIR/.env"

install -m 0644 "$APP_DIR/deploy/anime-tracker.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo
echo "Installed and enabled ${SERVICE_NAME}.service. It has NOT been started yet."
echo "Next: sudo nano $APP_DIR/.env, set DISCORD_TOKEN, then run:"
echo "  sudo systemctl start $SERVICE_NAME"
echo "  sudo systemctl status $SERVICE_NAME --no-pager"
echo "  sudo journalctl -u $SERVICE_NAME -f"
