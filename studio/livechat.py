"""Reading a live stream's chat, to count messages per second. Twitch is read in live.py (its IRC chat); this file
reads YouTube, through yt-dlp, which follows a live chat as it happens. Only the number of messages matters: nothing
anyone writes is stored or sent anywhere.

Kick is not read yet: its supported way is Kick's developer API (an app registered with Kick, chat events sent to
this server's public address), which needs a deployed server.

Each reader calls `count()` once per message and returns when `stop()` says so or the stream ends."""
import subprocess
import sys
import time
from pathlib import Path



def platform(url: str) -> str:
    u = (url or "").lower()
    return "kick" if "kick.com/" in u else "youtube" if ("youtube.com" in u or "youtu.be" in u) else "twitch" if "twitch.tv/" in u else ""


# ---------------------------------------------------------------- YouTube
def read_youtube(url: str, count, stop, folder: Path, on=lambda v: None):
    """Count YouTube live chat messages until stop() is true. yt-dlp follows the chat and writes each message as a
    line to a file; that file is read as it grows, and deleted afterwards."""
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / "chat"
    for old in folder.glob("chat*.json*"):
        old.unlink(missing_ok=True)
    cmd = [sys.executable, "-m", "yt_dlp", "--skip-download", "--write-subs", "--sub-langs", "live_chat", "--no-warnings",
           "--quiet", "-o", str(out), url]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    f, pos = None, 0
    try:
        while not stop():
            if f is None:
                found = next(iter(folder.glob("chat*.live_chat.json*")), None)
                if found:
                    f = found
                    on(True)
            if f is not None:
                try:
                    with f.open("rb") as h:
                        h.seek(pos)
                        data = h.read()
                except OSError:
                    data = b""
                if data:
                    keep = data.rfind(b"\n") + 1            # only whole lines; a half-written one waits for next time
                    for line in data[:keep].splitlines():
                        if b"addChatItemAction" in line and b"liveChatTextMessageRenderer" in line:
                            count()
                    pos += keep
            if p.poll() is not None:
                break                                     # the stream (or the chat) ended
            time.sleep(1.0)
    finally:
        on(False)
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()
        for old in folder.glob("chat*"):
            old.unlink(missing_ok=True)
