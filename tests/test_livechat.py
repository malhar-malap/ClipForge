"""Live chat counting for YouTube: chat lines written by yt-dlp are counted as they arrive, and nothing is left behind.
yt-dlp is replaced by a stand-in that writes a few chat lines, so no network is used."""
import json, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, ".")
from studio import livechat
fails = []
def check(n, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

folder = Path(tempfile.mkdtemp())
msg = json.dumps({"replayChatItemAction": {"actions": [{"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {"message": "hi"}}}}]}})
other = json.dumps({"replayChatItemAction": {"actions": [{"addChatItemAction": {"item": {"liveChatPaidMessageRenderer": {}}}}]}})

class FakeYtDlp:
    def __init__(self, cmd, **kw):
        self.t0 = time.time()
        self.f = folder / "chat.live_chat.json.part"
    def poll(self):
        age = time.time() - self.t0
        lines = [msg, other, msg] + ([msg, msg] if age > 1.2 else [])
        self.f.write_text("\n".join(lines) + "\n" + '{"half": ', encoding="utf-8")     # a half-written last line
        return 0 if age > 2.6 else None
    def terminate(self): pass
    def wait(self, t=None): pass
    def kill(self): pass

livechat.subprocess.Popen = FakeYtDlp
n, state = [0], []
livechat.read_youtube("https://www.youtube.com/@someone/live", lambda: n.__setitem__(0, n[0] + 1), lambda: False, folder, state.append)
check("chat messages are counted as they arrive (paid stickers and half-written lines are not)", n[0], 4)
check("the reader says when it is reading and when it stopped", (state[0], state[-1]), (True, False))
check("the chat file is deleted afterwards", list(folder.glob("chat*")), [])
check("links are told apart", [livechat.platform(u) for u in ("https://youtu.be/x", "https://kick.com/x", "https://twitch.tv/x")], ["youtube", "kick", "twitch"])
print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
