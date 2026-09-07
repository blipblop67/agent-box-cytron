"""
Tailscale as an optional, admin-configurable way to reach this hub - a
stable, secure hostname on your own private network, the same category
of feature as DuckDNS (dynamic_dns.py), but through a mesh VPN instead of
public DNS. Purely about reachability, same as DuckDNS - has nothing to
do with how anyone logs into Agent Hub itself.

Genuinely different from DuckDNS underneath, worth understanding before
touching this file: DuckDNS is one HTTP call from anywhere. Tailscale
needs its own system binary installed on this machine (install.sh does
this) and a running `tailscaled` daemon (started by that same install,
as its own systemd service) - this module is a thin wrapper around the
`tailscale` CLI talking to that already-running daemon, not a
from-scratch client of Tailscale's own API.

Joining a tailnet (`tailscale up`) configures network interfaces and
routing, which needs root - this process does not run as root, so
install.sh also adds a narrowly-scoped sudoers rule letting the hub's
own service user run the `tailscale` binary specifically, and nothing
broader, via sudo with no password prompt. That rule's exact wording and
reasoning live in install.sh, not here.
"""
import json
import os
import shutil
import subprocess

TAILSCALE_BIN = "/usr/bin/tailscale"


class TailscaleError(Exception):
    pass


def is_installed() -> bool:
    """Whether the tailscale binary exists at all - install.sh puts it
    there, but a hub that predates this feature, or one running somewhere
    other than the standard install, might not have it yet."""
    return shutil.which("tailscale") is not None or os.path.exists(TAILSCALE_BIN)


def join(auth_key: str, hostname: str | None = None) -> dict:
    """Joins this hub to whichever tailnet the given auth key belongs to
    (generated in the Tailscale admin console - not something this app
    can create itself, same relationship DuckDNS has to a DuckDNS
    account). Safe to call again later with a fresh key if the hub is
    ever removed from a tailnet and needs to rejoin - `tailscale up` is
    idempotent, not a one-time action that breaks on a second call."""
    if not is_installed():
        raise TailscaleError(
            "Tailscale isn't installed on this device yet - it should have been set up by install.sh. "
            "If this hub predates that, see deploy/README.md for how to add it."
        )
    cmd = ["sudo", "-n", TAILSCALE_BIN, "up", f"--authkey={auth_key}", "--accept-dns=true"]
    if hostname:
        cmd.append(f"--hostname={hostname}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as exc:
        raise TailscaleError("Tailscale didn't respond within 30 seconds - check the device's network connection") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if "sudo" in detail.lower() and "password" in detail.lower():
            raise TailscaleError(
                "This hub's service account isn't allowed to run Tailscale without a password prompt - "
                "the sudoers rule from install.sh may be missing. See deploy/README.md."
            )
        raise TailscaleError(f"Tailscale rejected that key: {detail or 'no further detail from tailscale itself'}")
    return status()


def status() -> dict:
    """Current connection state, straight from the running daemon - not
    cached, not stored in the database, since Tailscale's own state is
    the actual source of truth and could change outside this app
    entirely (someone removing the device from the admin console, for
    instance)."""
    if not is_installed():
        return {"connected": False, "installed": False}
    try:
        result = subprocess.run([TAILSCALE_BIN, "status", "--json"], capture_output=True, text=True, timeout=10)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {"connected": False, "installed": True}
    if result.returncode != 0:
        return {"connected": False, "installed": True}
    try:
        data = json.loads(result.stdout)
    except ValueError:
        return {"connected": False, "installed": True}

    self_node = data.get("Self", {})
    dns_name = (self_node.get("DNSName") or "").rstrip(".")
    is_up = bool(self_node.get("Online")) and dns_name != ""
    return {
        "connected": is_up,
        "installed": True,
        "hostname": dns_name,
        "tailscale_ip": (self_node.get("TailscaleIPs") or [None])[0],
        "tailnet": (data.get("CurrentTailnet") or {}).get("Name"),
    }


def leave() -> None:
    """Removes this hub from whatever tailnet it's currently on - the
    reverse of join(), for an admin who wants to disconnect entirely
    rather than just leaving it configured but unused."""
    if not is_installed():
        return
    subprocess.run(["sudo", "-n", TAILSCALE_BIN, "logout"], capture_output=True, text=True, timeout=15)
