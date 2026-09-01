#!/bin/bash
# Prepares this Pi's SSD to be safely cloned for mass production.
#
# WHY THIS EXISTS: a disk clone copies everything bit-for-bit, including
# things that must be unique per physical unit. Skipping this before
# cloning would ship every customer:
#   - the same encryption key protecting every secret Agent Hub stores
#     (API keys, service account keys, SMTP passwords) - if that key is
#     ever extracted from ANY one unit, every unit ever cloned from this
#     image becomes decryptable, not just that one
#   - whatever test/dev accounts, flows, and settings exist on this Pi
#     right now - including any real credentials that were ever typed
#     into Settings while testing
#   - identical SSH host keys, machine IDs, and hostnames across every
#     unit, which causes host-key warnings, network identification
#     collisions, and (for the hostname specifically) every unit trying
#     to publish the exact same mDNS name the moment two are ever on the
#     same network
#
# This script wipes all of that. Each cloned copy regenerates its own -
# a blank Agent Hub database, its own unique encryption key, its own SSH
# host keys, its own machine ID, its own unique hostname - automatically,
# the first time THAT specific unit boots. Nothing to run again after
# cloning, and nothing that depends on the cloning tool having any
# per-target customization step (a hardware duplicator doing raw
# block-level copies has none - the uniqueness has to come from the
# software's own first-boot behavior, not from anything done during the
# copy itself).
#
# RUN THIS LAST, right before the SSD is removed to be cloned. Do NOT
# power this specific Pi back on afterward until cloning is done - a
# normal boot would immediately regenerate a fresh identity for THIS Pi
# specifically, which then gets baked into every clone taken after that,
# defeating the entire point.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${AGENT_HUB_DATA_DIR:-$HOME/.agent-hub}"

echo "=== Agent Hub: prepare golden image for cloning ==="
echo
echo "This will permanently delete, on THIS Pi:"
echo "  - $DATA_DIR (every account, flow, document, and stored credential)"
echo "  - $ROOT_DIR/backend/.env (if it exists - may hold real secrets)"
echo "  - this Pi's SSH host keys, machine ID, and unique-hostname marker"
echo "  - shell history and system logs"
echo
echo "There is no undo. Make sure this is really the source Pi you intend"
echo "to clone from, not a unit that's already gone to a customer."
echo
read -r -p "Type 'yes' to continue: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted - nothing was changed."
    exit 1
fi

echo
echo "==> Stopping the hub"
sudo systemctl stop agent-hub 2>/dev/null || true

echo "==> Wiping Agent Hub's data (database, encryption key, vector store, uploads)"
rm -rf "$DATA_DIR"

echo "==> Removing backend/.env, if present"
rm -f "$ROOT_DIR/backend/.env"

echo "==> Clearing SSH host keys (Raspberry Pi OS regenerates these on first boot)"
sudo rm -f /etc/ssh/ssh_host_*

echo "==> Clearing the machine ID (systemd regenerates this on first boot)"
sudo truncate -s 0 /etc/machine-id
sudo rm -f /var/lib/dbus/machine-id

echo
echo "What hostname should every unit cloned from this image be based on?"
echo "Each cloned unit gets a unique random suffix added automatically on"
echo "its own first boot (e.g. 'agenthub-a3f9c1e2') - this is just the"
echo "shared, recognizable part every unit's name will start with."
read -r -p "Base hostname [agenthub]: " BASE_HOSTNAME
BASE_HOSTNAME="${BASE_HOSTNAME:-agenthub}"
echo "==> Setting this Pi's own hostname to '$BASE_HOSTNAME' (the clone base)"
sudo hostnamectl set-hostname "$BASE_HOSTNAME"

echo "==> Clearing the unique-hostname marker, so it's genuinely unset on this golden image"
echo "    (if this Pi has been used for testing, this first-boot step may already have"
echo "    fired on it once - clearing it here guarantees every clone gets its own fresh"
echo "    run, instead of silently inheriting an already-used marker from this Pi)"
sudo rm -f /etc/agent-hub-hostname-set

echo "==> Clearing shell history"
history -c 2>/dev/null || true
rm -f "$HOME/.bash_history"

echo "==> Rotating and clearing system logs"
sudo journalctl --rotate 2>/dev/null || true
sudo journalctl --vacuum-time=1s 2>/dev/null || true

echo
echo "Done. This SSD is ready to clone."
echo
echo "Next steps:"
echo "  1. Power this Pi off now - don't boot it again before cloning."
echo "  2. Clone the SSD with your usual tool - a hardware duplicator, dd,"
echo "     Raspberry Pi Imager, whatever you're using. No per-target"
echo "     customization step is needed, including for the hostname."
echo "  3. Nothing else to do. Each unit's own first boot generates its own"
echo "     database, encryption key, SSH identity, AND a unique hostname"
echo "     (base '$BASE_HOSTNAME' plus a random suffix) automatically -"
echo "     including on hardware that clones via raw block-level copying"
echo "     with no customization step at all."
