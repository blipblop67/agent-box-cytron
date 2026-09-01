#!/bin/bash
# Runs once, automatically, on this unit's first boot - see the accompanying
# systemd unit (agent-hub-hostname.service). Gives this specific unit a
# genuinely unique hostname, derived from its own freshly-generated
# machine-id, so a fleet of identical bit-for-bit clones - produced by a
# hardware duplicator, or any other block-level copying tool with no
# per-target customization step at all, unlike Raspberry Pi Imager - never
# end up trying to publish the same mDNS name on the same network.
#
# Deliberately not a one-off manual step during imaging: a duplicator makes
# byte-for-byte identical copies with no opportunity to customize any one
# target during the copy itself, so uniqueness has to be introduced by the
# software, on each unit's own first boot, or it doesn't happen at all.
set -euo pipefail

MARKER=/etc/agent-hub-hostname-set
if [ -f "$MARKER" ]; then
    exit 0  # already run once on this unit - never touch the hostname again after that
fi

CURRENT_HOSTNAME="$(hostname)"
# machine-id is guaranteed unique per unit - systemd regenerates it fresh,
# very early at boot, whenever it's missing, which is exactly why
# deploy/prepare-golden-image.sh clears it before a golden image gets
# cloned. 8 hex characters (32 bits) keeps hostname collisions implausible
# even across a large production run.
SUFFIX="$(cut -c1-8 /etc/machine-id)"
NEW_HOSTNAME="${CURRENT_HOSTNAME}-${SUFFIX}"

hostnamectl set-hostname "$NEW_HOSTNAME"
touch "$MARKER"

# Belt-and-suspenders: make sure avahi actually publishes the new name
# immediately, regardless of whether systemd's own service ordering ran
# this early enough relative to avahi-daemon starting up.
systemctl restart avahi-daemon 2>/dev/null || true
