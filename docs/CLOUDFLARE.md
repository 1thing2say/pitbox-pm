# Running Pit Box behind Cloudflare Access

This is the deployment the app is built for. Cloudflare checks who you are;
Pit Box trusts the answer. There are no passwords, no accounts to create, and
nothing to hand over at the end of the year except the Cloudflare login.

**How access works once this is set up:** a new member with a school email opens
the URL, Cloudflare emails them a one-time code, and they are in. Pit Box sees
their email, creates their member record on the spot, and they appear in the
assignee list. Nobody runs a script. When they graduate and the school disables
their email, they stop being able to get a code.

---

## The security model, in one paragraph

Read this before changing anything about how the app is started.

Pit Box binds **127.0.0.1** — it accepts connections only from its own machine.
`cloudflared` runs on that machine, dials *out* to Cloudflare, and is the sole
route in. Cloudflare enforces your Access policy, then adds a
`Cf-Access-Authenticated-User-Email` header, and the app trusts it.

That trust is only safe because nothing else can reach the app to set that
header. **If you ever bind it to `0.0.0.0`, forward the port, or put it on the
LAN, anyone who can reach the port can forge that header and walk in as anybody.**
No port is ever opened by this setup — that is the point of a tunnel.

---

## What you need

- A domain on Cloudflare. Around $10/yr at cost from Cloudflare Registrar; a
  subdomain like `pitbox.yourteam.org` is fine.
- A machine that stays on, with Pit Box running.
- A free Cloudflare Zero Trust plan — covers 50 users.

---

## Part 1 — on the machine

**1. Build the UI and run the app on localhost.**

```powershell
cd frontend; npm run build; cd ..
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`PITBOX_AUTH_MODE` defaults to `cloudflare`, so there is nothing to set. Confirm:

```powershell
curl.exe http://127.0.0.1:8000/api/health
# {"status":"ok","team":"MESA ARC Racing","auth_mode":"cloudflare"}
```

Hitting it directly now returns **403** with a message about Access. That is
correct — it means the app refuses anything that did not come through the tunnel.

**2. Install cloudflared and sign in.**

```powershell
winget install Cloudflare.cloudflared
cloudflared tunnel login
```

**3. Create the tunnel and point a hostname at it.**

```bash
cloudflared tunnel create pitbox
cloudflared tunnel route dns pitbox pitbox.yourteam.org
```

`create` prints a tunnel ID and the path to a credentials JSON — you need both next.

**4. Write the config.** Copy `deploy/cloudflared-config.example.yml` to
`%USERPROFILE%\.cloudflared\config.yml` and fill in the tunnel name, the
credentials path, and your hostname.

**5. Run it.**

```bash
cloudflared tunnel run pitbox
```

> At this point the URL is **live and unprotected**. Do Part 2 now, before
> sharing it with anyone.

---

## Part 2 — on the Cloudflare dashboard

This is the part that actually gates access.

**1.** Go to <https://one.dash.cloudflare.com> and pick your account. This is
**Zero Trust**, a different dashboard from the main Cloudflare one.

**2.** In the sidebar: **Access → Applications → Add an application**.

**3.** Choose **Self-hosted**.

**4.** Fill in the application:

| Field | Value |
|---|---|
| Application name | `Pit Box` |
| Session duration | `1 month` — how long before members re-authenticate |
| Subdomain | `pitbox` |
| Domain | `yourteam.org` |

**5.** Continue to policies and **add a policy**:

| Field | Value |
|---|---|
| Policy name | `Team members` |
| Action | **Allow** |
| Selector | **Emails ending in** |
| Value | `@youruniversity.edu` |

That single rule is the whole access-control system: anyone with a school email
gets in, everyone else does not. If your school's addresses are inconsistent,
use the **Emails** selector and list people instead — more precise, but then you
are back to maintaining a list, which is the thing this design avoids.

**6.** Login methods: **One-time PIN** is on by default and needs no setup —
Cloudflare emails a code. That is enough. If your school uses Google Workspace
or Microsoft 365, adding it under **Settings → Authentication** gives one-click
sign-in instead of a code.

**7.** Save the application.

**8. Verify it actually blocks.** Open the URL in a private window. You should
get a Cloudflare login prompt, *not* Pit Box. Try a personal email — it must be
refused. Only then share the link.

---

## Part 3 — make it survive a reboot

```powershell
cloudflared service install
```

And install the app's own boot task, from an **elevated** PowerShell:

```powershell
.\deploy\install-tasks.ps1
```

Then reboot the machine and load the URL from your phone on cellular. If it
comes up without you touching anything, all three pieces work together.

---

## Day-to-day

**Removing someone before they graduate:** add a Block policy above the Allow
policy with their email. Cloudflare evaluates in order.

**Signing out** clears the Cloudflare session at `/cdn-cgi/access/logout` — the
app's Sign out button already points there in this mode.

**Uptime monitoring:** `/api/health` is behind Access like everything else, so an
external monitor gets the login page. If you want one, add a **Bypass** policy
scoped to the path `/api/health`. It reveals only that the service is up.

**Local development** has no tunnel, so `dev.ps1` sets `PITBOX_AUTH_MODE=none`
and runs with no auth at all. That is fine on your own machine and nowhere else.

---

## If it breaks

| Symptom | Cause |
|---|---|
| 403 "No Cloudflare Access identity" | Reached the app without going through the tunnel, or no Access policy is attached to the hostname |
| Cloudflare login appears, then 502 | Tunnel is up, app is not — start uvicorn |
| Login prompt loops | Session duration too short, or the browser is blocking third-party cookies |
| Everyone gets in, including outsiders | The application in Part 2 was never created, or its domain does not exactly match the hostname |

The last one is worth checking deliberately: a tunnel with no Access
application in front is a public URL.

---

## If you ever leave Cloudflare

The app still has a built-in login — scrypt passwords and revocable sessions —
switched off by default. Set `PITBOX_AUTH_MODE=password`, create an admin with
`python scripts/create_user.py --email you@school.edu --name "You" --admin`, and
`/login` starts working. Nothing else changes.
