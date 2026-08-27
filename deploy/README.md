# Deploying to a Raspberry Pi 5

This assumes an 8GB Pi 5, booting off an NVMe SSD or a good USB SSD rather
than a bare SD card - the vector index, logs, and uploaded documents will
punish an SD card over time, and this is meant to run unattended, starting
itself back up every time the Pi boots.

## 1. Flash the OS

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to write
**Raspberry Pi OS Lite (64-bit)** - the 64-bit part matters, several backend
dependencies (`chromadb`, `fastembed`) need `aarch64` wheels that don't exist
for 32-bit. "Lite" is fine - there's no desktop UI here, everything is
reached through a browser from another device.

In the Imager's advanced options (the gear icon), before writing:
- Set a hostname (e.g. `agenthub` → reachable at `agenthub.local`)
- Enable SSH
- Set a username/password
- Configure Wi-Fi, if not using Ethernet

Boot it, then SSH in: `ssh <username>@agenthub.local`

## 2. Get this whole folder onto the Pi

Copy the entire `agent-hub/` folder over - `git clone` if you've pushed it to
a repo, `scp -r agent-hub <username>@agenthub.local:~/` from your laptop, or
a USB drive. You need all three subfolders (`backend/`, `frontend/`,
`deploy/`) present together, exactly as they came.

## 3. Run the install script

```bash
cd agent-hub
chmod +x deploy/install.sh
./deploy/install.sh
```

This one script does everything:

1. Installs Node.js (if it isn't already on the Pi) and builds the frontend
2. Creates a Python virtual environment in `backend/.venv` and installs
   `backend/requirements.txt`
3. Creates `~/.agent-hub` for the database, uploads, and vector index
4. Installs a `systemd` service and starts it - **and enables it, so it
   comes back up automatically on every future boot**, not just right now
5. Verifies all of the above actually worked (checks the service is enabled,
   running, and responding) before printing a URL

It's safe to re-run any time - after a `git pull`, for example - it
rebuilds the frontend, reinstalls dependencies, and restarts the service.
If you've already built the frontend elsewhere and don't want this script
touching Node at all, run `./deploy/install.sh --skip-frontend` instead.

Building the frontend directly on the Pi (which is what this script does by
default) is slower than on a laptop, but it means the whole setup - frontend
and backend both - happens with one command, on the device itself. If you'd
rather build on a faster machine and skip Node entirely:

```bash
# on your laptop, inside agent-hub/frontend/
npm install && npm run build
scp -r dist <username>@agenthub.local:~/agent-hub/backend/app/static
# then, on the Pi:
cd agent-hub && ./deploy/install.sh --skip-frontend
```

If `chromadb` or `fastembed` fail to install with a long build log instead of
downloading a wheel, the script automatically retries against
[piwheels](https://www.piwheels.org) - Raspberry Pi's own prebuilt-wheel
index - which almost always fixes it.

## 4. Open it

From any device on the same network:

```
http://agenthub.local:8811
```

(swap `agenthub` for whatever hostname you chose). First person to open it
becomes the hub's admin.

For everything past this point - first login, configuring an LLM
provider, building a first flow, connecting Google/Telegram, inviting a
team - see [`../GETTING_STARTED.md`](../GETTING_STARTED.md), which picks
up exactly here. Steps 5 and 6 below cover the two pieces specific to a
Pi deployment (Google and Telegram setup happen the same way regardless
of platform, but are repeated here for anyone reading this file on its
own).

## 5. Set up Google integration (optional)

Only needed if you want Email/Drive/Calendar/Sheets nodes to work. This
happens entirely on the **Settings page in the app** - no file to edit on
the Pi, and no browser consent screen for anyone to click through, since
it's one hub-wide service account rather than a per-person login.

In [Google Cloud Console](https://console.cloud.google.com):

1. Create a project.
2. **APIs & Services → Library** → enable whichever of **Gmail API**,
   **Google Drive API**, **Google Calendar API**, and **Google Sheets
   API** you actually need.
3. **IAM & Admin → Service Accounts → Create Service Account.** No roles
   need to be granted here.
4. Open it → **Keys → Add Key → Create new key → JSON**. This downloads
   the only copy of the private key.

Now, on the hub's **Settings** page (admin only): find the **Google
(Gmail / Drive / Calendar / Sheets)** card, paste the entire contents of
that JSON file, and Save. It takes effect immediately, no restart.

Every Email/Drive/Calendar/Sheets node then has an **Impersonate** field.
Left blank, it acts as the service account's own identity - this works
right away for Drive/Sheets/Calendar (its own space, or anything shared
with its email address). Gmail specifically needs a real address there,
which needs one more one-time step: a Google Workspace super admin
authorizing this exact service account for domain-wide delegation, once,
in the Workspace Admin Console (a different site - admin.google.com, not
Cloud Console). `backend/README.md` has the full walkthrough for that
step, including the exact scopes to grant.

Use the **Test** button on the Settings card - with or without an email
address - to confirm this actually works before wiring it into a real
flow.

## 6. Set up Telegram (optional)

No Google Cloud setup needed - each person creates their own bot by
messaging **@BotFather** on Telegram (`/newbot`, follow the prompts), then
pastes the resulting token into the Connections page. After sending the new
bot one message, click "Finish linking" there to connect it. Works
immediately, nothing to configure on the hub itself.

## Confirming it really does start on boot

The install script already checks this for you (the "starts on boot" line
in its output should say `enabled`), but if you want to see it with your own
eyes, an actual reboot is the real test:

```bash
sudo reboot
# wait ~30-60 seconds, then from another device:
curl http://agenthub.local:8811/healthz
```

You should get `{"status":"ok"}` without having logged back into the Pi or
run anything yourself.

## Updating later

Two ways, take your pick:

**From inside the app** (Settings → Software updates) - point it at a GitHub
repo/branch you control, click "Check for updates," then "Update now." It
downloads, rebuilds, and restarts itself automatically - the systemd unit
uses `Restart=always` specifically so this works, detected via the
`INVOCATION_ID` environment variable systemd sets. Your flows, knowledge
bases, and connections are untouched - they live in `~/.agent-hub`, nowhere
near the code this replaces. See `backend/README.md`'s "Self-updates"
section for how it works and how to roll back if an update ever goes wrong.

**From the terminal**, same as before:
```bash
# pull/copy the new code over the existing agent-hub/ folder, then:
cd agent-hub
./deploy/install.sh
```

## Useful commands

| What | Command |
|---|---|
| Is it running? | `sudo systemctl status agent-hub` |
| Does it start on boot? | `systemctl is-enabled agent-hub` |
| Watch logs live | `journalctl -u agent-hub -f` |
| Restart it | `sudo systemctl restart agent-hub` |
| Stop it | `sudo systemctl stop agent-hub` |
| Stop it permanently (undo autostart) | `sudo systemctl disable --now agent-hub` |

## Troubleshooting

- **Can't reach the hub from another device on the same Wi-Fi at all**
  (not even by IP address, e.g. `http://192.168.1.95:8811` times out or
  refuses to connect) - work through these in order:
  1. **Confirm it's actually running**: `sudo systemctl status agent-hub`
     on the Pi. If it's not "active (running)", nothing on the network
     will reach it regardless of IP/firewall - see the log line below.
  2. **Confirm the IP is still current**: `hostname -I` on the Pi - DHCP
     can hand out a different address after a reboot or router restart if
     the Pi doesn't have a reserved/static IP. If it changed, that's the
     whole problem.
  3. **Check the Pi's own firewall**, if you ever enabled one:
     `sudo ufw status` - if it says "active" and port 8811 isn't listed,
     `sudo ufw allow 8811`.
  4. **Router/Wi-Fi client isolation**: some routers (especially
     guest networks, or mesh systems with an "isolate clients" or "AP
     isolation" setting) block devices on the same Wi-Fi from reaching
     each other entirely, even though both have internet access fine.
     This is a router setting, not something fixable on the Pi - check
     your router's admin page, or try both devices on a different network
     to confirm this is the cause.
  5. **Running on Windows instead of the Pi** (`windows-run.ps1`)? The
     very first time it starts listening on a network port, Windows
     commonly shows a "Windows Defender Firewall has blocked some
     features of this app" popup - if you (or whoever's used that laptop)
     ever dismissed it, or only checked "Private networks", other devices
     on the same Wi-Fi are silently blocked even though `localhost:8811`
     still works fine on that laptop itself. Windows Settings → Update &
     Security → Windows Security → Firewall & network protection →
     "Allow an app through firewall" → find Python/uvicorn → check both
     Private and Public.
- **Can't reach `agenthub.local` specifically, but the IP works fine**:
  some routers or isolated Wi-Fi networks block mDNS (the `.local` name
  resolution) specifically, even with client isolation off - just use the
  IP address directly going forward (`hostname -I` on the Pi).
- **Service is "active" but the page won't load**: check
  `journalctl -u agent-hub -n 50` for the actual error - usually a missing
  `backend/app/static` build or a dependency that failed to install.
- **A knowledge base upload sits at "processing" forever**: the local
  embedding model downloads on its first real use (~130MB) - it needs
  internet the first time, then works offline. Check the logs to see if
  that download is stuck.
- **`./deploy/install.sh` says "Unknown option"**: you're likely running it
  as `sh deploy/install.sh` instead of `./deploy/install.sh` (or
  `bash deploy/install.sh`) - it needs a real bash, not POSIX `sh`.
