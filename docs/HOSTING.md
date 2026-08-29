# Hosting Pit Box for the team

## The real question is authentication

Pit Box has **no login**. Every endpoint is open to whoever can reach the port,
including `DELETE /api/nodes/{id}`, which removes a subsystem and everything
under it. So "put it on the internet" is not a hosting task, it is an auth task.

You have two ways to solve that without writing auth code, and one way that
needs none because nothing is exposed. Pick by how your team actually works:

| | Reaches it from | Teammate setup | Cost | Auth |
|---|---|---|---|---|
| **Cloudflare Tunnel + Access** ← recommended | anywhere | open a URL | ~$10/yr domain | Google / Microsoft SSO or email code |
| **Tailscale** | anywhere | install Tailscale once | free | your Tailscale identity |
| **Campus LAN only** | on campus | nothing | free | none — the network is the fence |

All three run the app on a machine **you** control (the shop PC, a spare laptop,
a Raspberry Pi). That is deliberate: your database is one file on that disk, so
backups are a file copy and there is no container that wipes itself on redeploy.

---

## Recommended: Cloudflare Tunnel + Access

Best fit for a team that turns over every year, because a new member needs
**nothing installed** — they open a link, sign in with the team Google account,
and they are in. You revoke someone by removing their email from a list.

It also never opens a port. `cloudflared` makes an **outbound** connection to
Cloudflare, so there is no port forwarding, no public IP, and nothing for campus
IT to approve or firewall.

### What you need

- A domain on Cloudflare (~$10/yr at cost from Cloudflare Registrar). If the
  team already owns one, use a subdomain: `pitbox.yourteam.org`.
- A machine that stays on.

### Steps

**1. Keep the app bound to localhost.** With a tunnel you never want it on the
LAN at all:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Build the UI first so FastAPI serves it at `/`:

```powershell
cd frontend; npm run build; cd ..
```

**2. Install cloudflared and log in.**

```powershell
winget install Cloudflare.cloudflared
cloudflared tunnel login
```

**3. Create the tunnel and point a hostname at it.**

```bash
cloudflared tunnel create pitbox
cloudflared tunnel route dns pitbox pitbox.yourteam.org
```

**4. Run it.** Create `C:\Users\<you>\.cloudflared\config.yml`:

```yaml
tunnel: pitbox
credentials-file: C:\Users\<you>\.cloudflared\<tunnel-id>.json
ingress:
  - hostname: pitbox.yourteam.org
    service: http://127.0.0.1:8000
  - service: http_status:404
```

```bash
cloudflared tunnel run pitbox
```

**5. Lock it down — do not skip this.** Until you add an Access policy the URL
is public. In the Cloudflare dashboard: **Zero Trust → Access → Applications →
Add a self-hosted application**, domain `pitbox.yourteam.org`, then add a policy:

- *Allow* → **Emails ending in** `@youruniversity.edu`, or
- *Allow* → **Emails** listing your team members explicitly.

Free for up to 50 users. Cloudflare now handles login and TLS; Pit Box never
sees a password, which is exactly why you do not have to write auth.

**6. Make both survive a reboot** so nobody has to remember:

```powershell
cloudflared service install
```

For the app itself, either Task Scheduler ("At startup", run `run.ps1`) or
[NSSM](https://nssm.cc/) to install uvicorn as a Windows service.

---

## Alternative: Tailscale (no domain needed)

If you do not want to buy a domain, this is the better option. It builds a
private network between your devices; the app is simply not reachable from the
public internet.

```powershell
winget install Tailscale.Tailscale
tailscale up
```

Run the app bound to the Tailscale interface (or `0.0.0.0`, since only tailnet
devices can route to it):

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Each teammate installs Tailscale, signs into the same tailnet, and opens
`http://<machine-name>:8000` via MagicDNS. Free tier covers 100 devices.

Trade-off: every teammate installs a client and joins the tailnet. For a small
technical team that is fine; for handing a link to a sponsor or a faculty
advisor, it is friction, and Cloudflare Access wins.

---

## Fallback: campus LAN only

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Teammates use `http://<the-pc's-ip>:8000`. Zero setup.

Be honest about what this is: **anyone on the campus network can edit or delete
anything**, with no record of who did it. That is often an acceptable trade for
a shop tool on a trusted network — but treat it as a stepping stone, and get the
backup job running before you rely on it.

---

## Why not Fly.io / Railway / Render

They work, and they are the obvious answer for a normal web app. They are a
worse fit here for three specific reasons:

1. **Persistent storage is the trap.** A container filesystem resets on every
   redeploy. Without a mounted volume for `pitbox.db` *and* `storage/`, a
   routine deploy silently destroys a season of work. This is the single most
   common way student projects lose their data.
2. **You still have no auth.** Hosting it there means writing login before it is
   safe to share, which is real work. Cloudflare Access is a checkbox.
3. **Something has to be maintained after you graduate.** A billing account that
   lapses takes the app with it.

If you have no machine that can stay on, then a PaaS is right. In that case use
Fly.io, mount a volume at `/data`, point both paths into it, and still put
Cloudflare Access in front:

```
PITBOX_DATABASE_URL=sqlite:////data/pitbox.db
PITBOX_STORAGE_DIR=/data/storage
```

Move to Postgres only when several people write at once and you see SQLite lock
errors — the schema and every query port unchanged.

---

## Keeping it running unattended

Two scheduled tasks handle "comes back after a reboot" and "gets backed up
without anyone remembering". Install both:

```powershell
# from an ELEVATED PowerShell (right-click > Run as administrator)
cd "C:\MESA Baja\Project manager"
.\deploy\install-tasks.ps1
```

Without admin it installs the backup task and tells you it skipped the server
one. To do only that on purpose:

```powershell
.\deploy\install-tasks.ps1 -BackupOnly
```

| Task | When | Runs as | Admin to install? |
|---|---|---|---|
| **Pit Box Backup** | Sundays 18:00 | you, when logged on | no |
| **Pit Box Server** | 30 s after boot | SYSTEM | **yes** |

The server task runs as **SYSTEM** on purpose: that is what lets the shop PC
reboot at 3 a.m. after Windows Update and come back with Pit Box serving, with
nobody logged in. That is also the only reason it needs admin to install.

The backup task deliberately does *not* run as SYSTEM. It runs as you, only
while you are logged on, which needs no stored password and no elevation.
`StartWhenAvailable` is set so a backup missed because the machine was off is
taken at the next opportunity rather than skipped forever.

### Bind address

The server task reads `PITBOX_HOST` / `PITBOX_PORT` from the **machine**
environment, because a SYSTEM task never sees your user variables. The installer
sets them:

```powershell
.\deploy\install-tasks.ps1                        # 127.0.0.1 - for Cloudflare Tunnel
.\deploy\install-tasks.ps1 -BindHost 0.0.0.0      # for LAN or Tailscale
```

Localhost is the default on purpose. With a tunnel in front, the app should not
be reachable on the network at all.

### Checking on it

```powershell
Start-ScheduledTask  -TaskName 'Pit Box Server'      # start now, no reboot
Get-ScheduledTaskInfo -TaskName 'Pit Box Server'     # LastTaskResult 0 = fine
Get-Content deploy\logs\pitbox.log -Tail 30 -Wait    # follow the log
.\deploy\uninstall-tasks.ps1                         # remove both, data untouched
```

Output goes to `deploy\logs\pitbox.log` (rotated at 2 MB, five kept), because a
task started by Windows has no console to print to. If the server task shows a
non-zero `LastTaskResult`, that log has the traceback.

### The tunnel, too

`cloudflared` installs its own Windows service, so it survives reboots
independently:

```powershell
cloudflared service install
```

Check both are up after a reboot before you trust it: reboot the machine, wait a
minute, and load the URL from your phone on cellular data — that proves the
tunnel, the Access policy, and the boot task all work together.

## Backups: do this before you share the link

**Do not just copy `pitbox.db`.** The database runs in WAL mode, so recent
writes live in `pitbox.db-wal` until SQLite checkpoints them. While the app is
running, a plain copy can capture a file that opens perfectly and is missing
almost everything. On this machine mid-session the main file was 4 KB and the
WAL was 408 KB — a naive copy would have "backed up" 1% of the data.

Use the script, which uses SQLite's online backup API, folds in the WAL, copies
the uploaded files, and verifies the result before reporting success:

```bash
python scripts/backup.py --keep 20
```

```
database  84.0 KB  ->  backups/pitbox-2026-08-28_2015/pitbox.db
          projects=1  nodes=57  tags=11  node_tags=9  attachments=1  members=5
files     1 files, 9 B
```

Schedule it weekly (Task Scheduler → weekly → run
`.venv\Scripts\python.exe scripts\backup.py --keep 20`) and point `--out` at
OneDrive, Google Drive, or a USB stick, so the backup is not on the same disk as
the thing it is backing up.

**Restoring:** stop the app, copy `pitbox.db` and `storage/` back over the
originals, delete any leftover `pitbox.db-wal` / `pitbox.db-shm`, start it again.

Once a season, actually restore a backup into a scratch folder and open it. An
untested backup is a rumour.
