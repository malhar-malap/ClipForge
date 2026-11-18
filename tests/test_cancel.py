"""Cancel: a video started by mistake stops at its next step. Nothing finished: the project goes away. Some clips
finished: they are kept and the rest are dropped. Runs against the code directly, with its own empty data folder."""
import os, sys, tempfile, time
os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="cf-cancel-"); os.environ["DATABASE_URL"] = ""; os.environ["PEAKCUT_ACCOUNTS"] = "0"
sys.path.insert(0, ".")
from pathlib import Path
from studio import ctx, db, jobs
db.init()
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

def _raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def fake(status, clips=()):
    jid = f"t{time.time_ns()}"
    d = Path(os.environ["PEAKCUT_DATA"]) / jid; d.mkdir()
    j = {"id": jid, "user": ctx.uid(), "creator": "", "dir": str(d), "status": status, "stage": "", "progress": 0.3,
         "clips": [dict(c) for c in clips], "source": {"type": "url"}, "title": "t", "options": {}}
    jobs._jobs[jid] = j; jobs._by_user.setdefault(j["user"], {})[jid] = j
    return j

with ctx.as_user(ctx.uid_or_none() or "local"):
    j = fake("queued")
    check("a video still waiting is removed straight away", (jobs.cancel(j["id"]), j["id"] in jobs._jobs), ("deleted", False))

    j = fake("running")
    check("a running video with nothing finished is marked to stop", (jobs.cancel(j["id"]), j["cancel"]), ("deleted", True))
    try:
        jobs._set(j, progress=0.5)
        stopped = False
    except jobs.Cancelled:
        stopped = True
    check("...and stops at its very next step", stopped)
    jobs._wrap_up_cancel(j)
    check("...then the project is gone", j["id"] in jobs._jobs, False)

    j = fake("running", [{"id": "c1", "status": "done", "start": 0, "end": 10}, {"id": "c2", "status": "rendering", "start": 20, "end": 30}])
    check("a running video with a finished clip keeps it", jobs.cancel(j["id"]), "stopped")
    jobs._wrap_up_cancel(j)
    check("...the finished clip stays, the unfinished one is dropped", ([c["id"] for c in j["clips"]], j["status"]), (["c1"], "done"))
    check("a finished video cannot be cancelled", jobs.cancel(j["id"]), "nothing")

# ---- free up space: the original goes, the clips stay
import subprocess
with ctx.as_user(ctx.uid_or_none() or "local"):
    j = fake("done", [{"id": "c1", "status": "done", "start": 0, "end": 3}])
    src = Path(j["dir"]) / "source.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10:duration=3", "-f", "lavfi",
                    "-i", "sine=frequency=300:duration=3", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(src)], check=True)
    (Path(j["dir"]) / "clips").mkdir()
    (Path(j["dir"]) / "clips" / "c1.mp4").write_bytes(b"clip")
    check("the page is told how big the original is", "original_mb" in jobs.public(j), True)
    jobs.free_space(j["id"])
    check("freeing space removes the original video", src.exists(), False)
    check("...keeps the clips", (Path(j["dir"]) / "clips" / "c1.mp4").exists(), True)
    check("...and keeps a small copy of the sound, so a clip from a link can still be re-made", (Path(j["dir"]) / "audio.opus").exists(), True)
    up = fake("done", [{"id": "c1", "status": "preview", "start": 0, "end": 3}]); up["source"] = {"type": "file"}
    check("an upload with clips still in preview keeps its original",
          _raises(lambda: jobs.free_space(up["id"])), True)

print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
