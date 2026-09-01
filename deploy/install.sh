#!/usr/bin/env bash
# Agent Hub - Raspberry Pi 5 install script.
#
# Run this ON THE PI, from inside the top-level agent-hub/ folder:
#   chmod +x deploy/install.sh
#   ./deploy/install.sh
#
# Does everything needed to go from "freshly cloned/copied folder" to
# "running now, and again automatically every time the Pi boots":
#   1. installs Node (if missing) and builds the frontend
#   2. creates a Python venv and installs the backend's dependencies
#   3. installs a systemd service and enables + starts it
#
# Safe to re-run any time (after pulling new code, for example) - it
# reinstalls dependencies, rebuilds the frontend, and restarts the service.
#
# Flags:
#   --skip-frontend   don't touch Node/npm or rebuild the frontend - use this
#                     if you already built it elsewhere and copied the result
#                     into backend/app/static yourself.
set -euo pipefail

SKIP_FRONTEND=0
for arg in "$@"; do
  case "$arg" in
    --skip-frontend) SKIP_FRONTEND=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
HUB_USER="${SUDO_USER:-${USER:-$(whoami)}}"
HUB_HOME="$(getent passwd "$HUB_USER" | cut -d: -f6)"

echo "==> Installing system dependencies (python3-venv, avahi for .local discovery)"
sudo apt-get update -qq
sudo apt-get install -y python3-venv python3-pip avahi-daemon curl >/dev/null

# ---------------------------------------------------------------------------
# 1. Frontend
# ---------------------------------------------------------------------------
if [ "$SKIP_FRONTEND" -eq 1 ]; then
  echo "==> --skip-frontend set, leaving backend/app/static as-is"
elif [ ! -d "$FRONTEND_DIR/src" ]; then
  echo "==> No frontend source found at $FRONTEND_DIR, skipping build"
else
  if ! command -v npm >/dev/null 2>&1; then
    echo "==> Node.js not found - installing Node 20.x LTS"
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - >/dev/null
    sudo apt-get install -y nodejs >/dev/null
  fi

  echo "==> Building the frontend (this can take a few minutes on a Pi)"
  if (cd "$FRONTEND_DIR" && npm install --silent && npm run build --silent); then
    rm -rf "$BACKEND_DIR/app/static"
    cp -r "$FRONTEND_DIR/dist" "$BACKEND_DIR/app/static"
    echo "==> Frontend built and copied into backend/app/static"
  else
    echo "!!  Frontend build failed - continuing with the backend anyway."
    echo "!!  The API will work, but there'll be no UI until this is fixed."
    echo "!!  Re-run with the build output above visible: cd frontend && npm install && npm run build"
  fi
fi

# ---------------------------------------------------------------------------
# 2. Backend
# ---------------------------------------------------------------------------
echo "==> Creating virtual environment at backend/.venv"
cd "$BACKEND_DIR"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip -q
if ! pip install -r requirements.txt -q; then
  echo "!!  A dependency failed to build from source (common for chromadb/fastembed on ARM)."
  echo "!!  Retrying with piwheels, Raspberry Pi's own prebuilt-wheel index..."
  pip install --extra-index-url https://www.piwheels.org/simple -r requirements.txt -q
fi
deactivate

echo "==> Creating data directory at $HUB_HOME/.agent-hub"
mkdir -p "$HUB_HOME/.agent-hub"

if [ ! -f "$BACKEND_DIR/.env" ]; then
  cp "$ROOT_DIR/deploy/.env.example" "$BACKEND_DIR/.env"
  echo "==> Created backend/.env from the example template - edit it to add Google"
  echo "    OAuth credentials or an Ollama URL, then re-run this script."
fi

# ---------------------------------------------------------------------------
# 3. systemd - start now, and on every future boot
# ---------------------------------------------------------------------------
echo "==> Installing systemd service"
sed \
  -e "s|__BACKEND_DIR__|$BACKEND_DIR|g" \
  -e "s|__USER__|$HUB_USER|g" \
  -e "s|__HOME__|$HUB_HOME|g" \
  "$ROOT_DIR/deploy/agent-hub.service" | sudo tee /etc/systemd/system/agent-hub.service >/dev/null

echo "==> Installing the first-boot unique-hostname service"
chmod +x "$ROOT_DIR/deploy/set-unique-hostname.sh"
sed \
  -e "s|__ROOT_DIR__|$ROOT_DIR|g" \
  "$ROOT_DIR/deploy/agent-hub-hostname.service" | sudo tee /etc/systemd/system/agent-hub-hostname.service >/dev/null
sudo systemctl enable agent-hub-hostname >/dev/null 2>&1

sudo systemctl daemon-reload
sudo systemctl enable agent-hub >/dev/null 2>&1
sudo systemctl restart agent-hub

# ---------------------------------------------------------------------------
# 4. Verify - don't just assume it worked
# ---------------------------------------------------------------------------
echo "==> Verifying"
sleep 2
ENABLED="$(systemctl is-enabled agent-hub 2>/dev/null || echo 'not enabled')"
ACTIVE="$(systemctl is-active agent-hub 2>/dev/null || echo 'not running')"
echo "    starts on boot : $ENABLED"
echo "    running now    : $ACTIVE"

if curl -fsS "http://127.0.0.1:8811/healthz" >/dev/null 2>&1; then
  echo "    responding     : yes"
else
  echo "    responding     : NO - check 'journalctl -u agent-hub -n 50'"
fi

echo ""
echo "==> Open, from any device on the same network:"
echo "      http://$(hostname).local:8811"
echo ""
echo "Logs:  journalctl -u agent-hub -f"
