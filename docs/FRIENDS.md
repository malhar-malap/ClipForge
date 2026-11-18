# Sharing ClipForge with a few friends, from your own computer

ClipForge stays on your computer and does all the work there. Your friends open a normal `https://` link. A
Cloudflare Tunnel carries their visits to your computer, and Cloudflare Access is the guest list at the door: only
the email addresses you add can get past Cloudflare at all. Then everyone signs in to ClipForge as well.

```
friend's browser → https://clips.your-domain.com → Cloudflare (guest list) → tunnel → your computer, 127.0.0.1:8765
```

Nothing is opened on your router, and your home address is never shown. All of this is free, apart from the domain
(around $10 a year).

## What you need

- A domain whose DNS is on Cloudflare (buy one at Cloudflare, or move an existing one there).
- A free Cloudflare Zero Trust account: open **Zero Trust** in the Cloudflare dashboard and pick the free plan.
- ClipForge already running on your computer (see the README).

## 1. Settings

Add these to `.env` in the ClipForge folder (make the file from `.env.example` if you have none):

```ini
PEAKCUT_ACCOUNTS=1                                   # everyone signs in, each with their own projects
PEAKCUT_PUBLIC_URL=https://clips.your-domain.com     # the link your friends open
PEAKCUT_TUNNEL=1                                     # tells friends apart, see "Why PEAKCUT_TUNNEL" below
CLIPFORGE_SECRET_KEY=                                # make one with the command below
PEAKCUT_JOB_WORKERS=2                                # keeps your computer usable while friends clip
PEAKCUT_MAX_JOBS_PER_USER=2
PEAKCUT_MAX_VIDEO_HOURS=2
PEAKCUT_MAX_USER_GB=10
```

Make the secret key (it encrypts the AI key and sign-in tokens on disk):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Leave `PEAKCUT_HOST` alone: ClipForge must keep listening on 127.0.0.1 only. The tunnel is the only way in.

With sign-in on, the projects you made before belong to the old built-in owner, so your new account starts empty.

## 2. The tunnel

1. In the Cloudflare dashboard: **Zero Trust → Networks → Tunnels → Create a tunnel**, type **Cloudflared**, name it
   `clipforge`.
2. Pick your system (macOS: `brew install cloudflared` first) and run the install command it shows. That command
   holds the tunnel's token: do not paste it anywhere else or commit it. It installs the tunnel as a service, so it
   starts by itself.
3. Under **Public hostname**, add `clips` on `your-domain.com`, type **HTTP**, address **127.0.0.1:8765**. Save.

## 3. The guest list (do this before you share the link)

1. **Zero Trust → Access → Applications → Add an application → Self-hosted.**
2. Application domain: `clips.your-domain.com`.
3. Add a policy: action **Allow**, include **Emails**, and list your friends' addresses and your own.
4. Login method: **One-time PIN** is enough: Cloudflare emails a code, no passwords to manage.

Open the link in a private window to check: Cloudflare should ask for an email before ClipForge appears.

## 4. First start

1. Start ClipForge: `python -m studio.server`.
2. Open `https://clips.your-domain.com` (use this link yourself too, not 127.0.0.1, so sign-in works the same for
   everyone) and sign up.
3. Make yourself the admin, so only you can see and change the AI key:
   ```bash
   python -m studio.admin grant you@example.com
   ```
4. Add the AI key in **Settings → AI**. Friends use it but never see it.
5. Send your friends the link. They pass the guest list once, then sign up.

## Keeping it running

- The site is up only while your computer is on, awake and online. On a Mac plugged in, turn on
  **System Settings → Battery → Options → Prevent automatic sleeping when the display is off**, or run
  `caffeinate -s` in a terminal while friends use it.
- Every friend's clips use your AI key. Set a monthly spend limit at your AI service (for Anthropic: the Console's
  limits page), so a leak or a busy week can only cost so much.
- To shut the door at once, turn off the tunnel in the Cloudflare dashboard, or stop ClipForge.
- To remove a friend: take their email off the Access policy, and disable their account in ClipForge's admin page.

## Why PEAKCUT_TUNNEL

The tunnel runs on your computer, so every friend arrives from 127.0.0.1, the same address as you. Without this
setting ClipForge would count all of them as one visitor: one friend's wrong passwords would lock everyone out of
signing in. With it, ClipForge reads the visitor's address from the header Cloudflare adds (visitors cannot change
it), and only when the request comes from this computer. A visit through the tunnel is never treated as you sitting
at the computer, with or without the setting.

Use it only with a tunnel like this one. On a VPS behind Cloudflare's CDN, use `PEAKCUT_CLIENT_IP_HEADER` instead
(see DEPLOY.md).
