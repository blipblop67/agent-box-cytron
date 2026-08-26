"""
Built-in dynamic DNS via DuckDNS - the actual permanent fix for "Google's
OAuth setup rejects a .local name and a raw LAN IP," not a one-time
workaround. Instead of walking someone through creating a DuckDNS
account, pointing it at their LAN IP by hand, and remembering to update
it if that IP ever changes, the hub does the update itself - once
configured, a background job (see scheduler.py) keeps it current
automatically, the same pattern already used for Telegram trigger
polling.

DuckDNS specifically: free, no email verification needed (sign in via an
existing GitHub/Google/Reddit account), and its update API is about as
simple as dynamic DNS gets - one authenticated GET request, plain-text
"OK"/"KO" response, no SDK or client library involved.
"""
import socket

import httpx

UPDATE_URL = "https://www.duckdns.org/update"


class DuckDnsError(Exception):
    pass


def detect_lan_ip() -> str:
    """The hub's own LAN-facing address - not 127.0.0.1, the IP other
    devices on the network actually use to reach it. Opens a UDP "connection"
    to a public address without sending any real traffic (UDP is
    connectionless - this just asks the OS which local interface it would
    use), the standard, portable way to find this without parsing
    `ip addr`/`ifconfig`/`ipconfig` output, which differs by OS."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


def update(subdomain: str, token: str, ip: str | None = None) -> dict:
    """Points <subdomain>.duckdns.org at `ip` (the hub's own detected LAN
    IP, if not given explicitly). Safe to call repeatedly and often -
    DuckDNS treats this as an idempotent "here's my current IP" call,
    which is exactly what the periodic background refresh relies on to
    survive a DHCP lease renewal without anyone noticing."""
    target_ip = ip or detect_lan_ip()
    try:
        resp = httpx.get(UPDATE_URL, params={"domains": subdomain, "token": token, "ip": target_ip}, timeout=15)
    except httpx.HTTPError as exc:
        raise DuckDnsError(f"Couldn't reach DuckDNS: {exc}") from exc

    # DuckDNS's API replies with plain "OK"/"KO" text on success/failure,
    # not a JSON body or a meaningful non-200 status code either way
    body = resp.text.strip()
    if not body.startswith("OK"):
        raise DuckDnsError(
            "DuckDNS didn't accept that - double check the subdomain and token are exactly what's "
            "shown on your DuckDNS account page (duckdns.org), with no extra spaces"
        )
    return {"domain": f"{subdomain}.duckdns.org", "ip": target_ip}
