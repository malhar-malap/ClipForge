<p align="center"><img src="web/brand/logo.svg" alt="ClipForge" height="56"></p>

<p align="center"><b>Long videos in. Shorts people finish out.</b><br>
AI clipping for streamers, podcasters and creators: finds the moments worth posting, frames them for 9:16,<br>
and adds captions that pop. Built for gaming streams and Indian languages.</p>

---

## What it does

| | |
|---|---|
| **Finds the best moments** | Reads the transcript, hears loudness spikes and chat bursts, and has an AI score every moment on its hook, payoff and whether it works on its own. An optional stronger model re-ranks the finalists. |
| **Frames every scene** | Detects the facecam, the speaker or the gameplay in each scene of a clip (streamers switch scenes mid-clip) and frames each part on its own. HUDs stay in view. With an AI key, a vision model confirms the layout. |
| **Your facecam, your style** | Facecam on the top half, a floating circle, a floating window, or gameplay only. |
| **Captions that pop** | Word-by-word captions in three styles, with an outline, a dark box or a highlight box behind the spoken word. Hindi and Urdu come out in Roman letters (Hinglish). |
| **Any language** | English with Parakeet; Hindi, Tamil, Telugu, Spanish and ~100 more with Whisper. YouTube's own captions are used when they exist (never a translated or dubbed track). |
| **Live clipping** | Records a Twitch, Kick or YouTube stream and clips it while it is still live. |
| **Plans and payments** | Free previews in the browser, downloads with a plan (Trial, Creator, Creator BYOK, Pro) through Razorpay, clips per plan, and users' own AI keys stored encrypted. |
| **Posting** | Connect YouTube, Instagram and TikTok and post clips straight from a project. |

## Quick start (your own computer)

You need **Python 3.10 or newer**, **ffmpeg** and, for HD YouTube downloads, **Deno**. Check your Python with
`python3 --version`: the one built into macOS is 3.9, which is too old.

```bash
# macOS
brew install python@3.12 ffmpeg deno
# Ubuntu / Debian
sudo apt install python3 python3-venv ffmpeg
curl -fsSL https://deno.land/install.sh | sh
# Windows
winget install Python.Python.3.12
winget install Gyan.FFmpeg
winget install DenoLand.Deno
```

Then get ClipForge and start it inside its own Python environment (`.venv`), so its packages stay separate from
the rest of your computer:

```bash
git clone https://github.com/malhar-malap/ClipForge.git
cd ClipForge
python3 -m venv .venv                 # on macOS with Homebrew: python3.12 -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m studio.server
```

Open <http://127.0.0.1:8765>. The first start downloads the speech model (about 480 MB), so give it a few minutes.
Next time, only `source .venv/bin/activate` and `python -m studio.server` are needed. There is no sign-in on your own computer. Add an AI key under **Settings → AI**
(Claude, Gemini, OpenAI and others work; a vision-capable model also improves framing). Without a key, clips are
picked by loudness only.

### Setting it up with an AI coding agent

Claude Code, Codex, Cursor and similar agents can do the steps above for you. Open the cloned folder in the agent
and paste:

> Set up and start this project on my computer by following README.md and AGENTS.md. Use a Python 3.10+ virtual
> environment in `.venv`, install ffmpeg and Deno if they are missing, run `python tests/run.py`, then start the
> server and tell me the address to open. Do not put any keys in files; I will add my AI key in Settings → AI.

`AGENTS.md` (also loaded through `CLAUDE.md`) tells the agent how the project is laid out and which rules to keep.

## Running it as a website

Copy `.env.example` to `.env`; every setting is explained there. The ones that matter:

```ini
PEAKCUT_ACCOUNTS=1                        # everyone signs in
GOOGLE_CLIENT_FILE=/secrets/google_client.json   # "Sign in with Google"
CLIPFORGE_BILLING=1                       # free previews, paid downloads
CLIPFORGE_SECRET_KEY=...                  # encrypts users' own AI keys
RAZORPAY_KEY_ID=... RAZORPAY_KEY_SECRET=... RAZORPAY_WEBHOOK_SECRET=...
```

[`docs/DEPLOY.md`](docs/DEPLOY.md) walks through one server with Docker, PostgreSQL and automatic HTTPS:

```bash
docker compose up -d --build
```

Give a plan without payment (beta creators) or make someone an admin:

```bash
python -m studio.admin plan someone@example.com creator
python -m studio.admin grant you@example.com
```

## Plans

| Plan | Price (+ 18% GST) | Clips | Longest part of a video | Notes |
|---|---|---|---|---|
| Free previews | ₹0 | – | 1 hour | Best 3 clips of up to 2 videos a day, played in the browser |
| Trial | ₹49 once | 20 | 1 hour | 7 days, once per account |
| Creator | ₹399 / month | 300 | 1 hour | |
| Creator BYOK | ₹199 / month | 300 | 1 hour | Runs on the user's own AI key; starts when the key passes a test |
| Pro | ₹999 / month | 2,000 | 1.5 hours | Priority queue, live clipping |

Every clip made counts as one, whatever its length; failed clips and re-makes are free. A longer video is clipped from
the part chosen on the timeline.

Prices, clips and limits live only in `studio/billing.py`.

## How it is built

```
studio/          the server (FastAPI) and the clip pipeline
  brain.py         prompts: finding moments, ranking, captions
  vision.py        framing: faces (YuNet), webcam borders, scenes, AI vision
  render.py        layouts, captions and the ffmpeg render
  jobs.py          the video pipeline and the fair queue
  transcribe.py    speech to text (Parakeet), whisper.py for other languages
  billing.py       plans, minutes, previews, Razorpay
  keystore.py      users' own AI keys, encrypted
  live.py          live recording and clipping
  server.py        every web route and the request gate
web/             the pages: landing, app, sign-in, admin (plain HTML, CSS, JS)
tests/           the test suite (python tests/run.py)
deploy/          Caddy, nginx and GPU speech-worker configs
docs/            deployment guide
```

## Tests

```bash
python tests/run.py
```

Starts a throwaway copy on a spare port with an empty data folder and runs every test group against it. No keys
needed, nothing outside your machine is contacted.

## Security

Passwords are salted scrypt hashes; sessions are random tokens stored hashed in HTTP-only cookies; every route
works out the user from the session; users' AI keys are encrypted; payments count only after Razorpay's signature
checks out; the Docker image runs as an unprivileged user. Found a problem? Please report it privately through
GitHub's security advisories.

## Credits and licence

ClipForge is built on [PeakCut](https://github.com/haziqahmedqasmi/PeakCut) and released under the
[MIT licence](LICENSE). Caption fonts in `studio/fonts/` are under the SIL Open Font License. The YuNet face model in
`studio/models/` is MIT licensed (OpenCV Zoo).

Clip videos you made or have permission to use, and follow the terms of the sites you fetch from and post to.
