"""Gaming and face layouts: deciding the layout from the faces found, and rendering each layout for real.
Runs against the code directly, with its own empty data folder. Needs ffmpeg; no AI key, no network."""
import os, subprocess, sys, tempfile
from pathlib import Path
os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="cf-layouts-"); os.environ["DATABASE_URL"] = ""
sys.path.insert(0, ".")
import numpy as np
from studio import render, vision
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

blank = np.random.default_rng(7).integers(0, 255, (12, 270, 480)).astype(np.uint8)   # a picture that keeps changing, like video
frozen = blank.copy(); frozen[:, 210:240, 420:450] = 90                                   # ...with a still sticker in one corner
cam_face = (0.88, 0.80, 0.055, 0.10)

# ---- deciding
per = [[cam_face] for _ in range(12)]
seen = vision.decide(per, blank, 1920, 1080)
check("a small face in the same corner all clip long is a facecam", seen["kind"], "facecam")
check("...and its webcam box contains the face", seen["cam"][0] <= cam_face[0] and seen["cam"][0] + seen["cam"][2] >= cam_face[0] + cam_face[2])
check("auto turns a facecam into the split layout", vision.choose_layout("auto", seen), "split")

moving = [[(0.1 + 0.06 * i, 0.4, 0.05, 0.09)] for i in range(12)]
check("a face that never changes (a sticker, an emote, a printed score face) is not a facecam",
      vision.decide([[(420 / 480, 210 / 270, 30 / 480, 30 / 270)]] * 12, frozen, 1920, 1080)["kind"] != "facecam")
cutout = blank.copy()                                     # a cut-out face sticker: the middle never changes...
cutout[:, 50:70, 40:60] = np.linspace(60, 200, 400).reshape(20, 20).astype(np.uint8)   # ...but its box corners show the video behind
check("a cut-out face sticker with the video moving behind its corners is not a facecam",
      vision.decide([[(36 / 480, 46 / 270, 28 / 480, 28 / 270)]] * 12, cutout, 1920, 1080)["kind"] != "facecam")
check("the AI pointing at a sticker is not believed",
      vision.decide([[(36 / 480, 46 / 270, 28 / 480, 28 / 270)]] * 12, cutout, 1920, 1080,
                    {"scene": "gameplay", "facecam": {"x": 0.05, "y": 0.15, "w": 0.1, "h": 0.15}})["kind"] != "facecam")
_, _, hook_y, cap_y = render.geometry(1920, 1080, "gamefocus", seen)
check("a floating circle facecam sits at the top centre, the hook just under it and the captions low",
      (hook_y > render.FLOAT_TOP + render.BUBBLE, cap_y > 1300), (True, True))
check("when the AI looked and saw no webcam, a small face is not used as one",
      vision.decide(per, blank, 1920, 1080, {"scene": "gameplay", "facecam": None})["kind"], "none")
check("a small face that moves around (a game character) is not a facecam", vision.decide(moving, blank, 1920, 1080)["kind"] != "facecam")

head = [[(0.35, 0.25, 0.18, 0.32)] for _ in range(12)]
seen_head = vision.decide(head, blank, 1920, 1080)
check("a big face is a talking head", seen_head["kind"], "head")
check("auto follows a talking head's face", vision.choose_layout("auto", seen_head), "face")

check("no faces: auto shows the whole frame", vision.choose_layout("auto", vision.decide([[]] * 12, blank, 1920, 1080)), "blur")
check("a vertical video is left alone", vision.decide(per, blank, 1080, 1920)["kind"], "none")
check("asking for split without a facecam falls back to the whole frame", vision.choose_layout("split", {"kind": "none"}), "blur")

hud_frames = (np.random.default_rng(1).integers(0, 255, (12, 270, 480))).astype(np.uint8)
hud_frames[:, 20:120, 10:90] = 0
hud_frames[:, 20:120:6, 10:90] = 255                 # a static striped box on the left: sharp and never changing
check("a static, detailed box on the left edge is a HUD", vision._hud(hud_frames), (True, False))
check("noise everywhere is not a HUD", vision._hud(np.random.default_rng(2).integers(0, 255, (12, 270, 480)).astype(np.uint8)), (False, False))

check("a HUD on the left pulls the gameplay crop to the left", render._game_window(1920, 1080, 1080 / 1280, [True, False])[0], 0)
check("a HUD on the right pulls it to the right", render._game_window(1920, 1080, 1080 / 1280, [False, True])[0] + render._game_window(1920, 1080, 1080 / 1280, [False, True])[1], 1920)
check("HUDs on both sides show the whole width", render._game_window(1920, 1080, 1080 / 1280, [True, True]), None)

# ---- the kind of video changes the framing
check("sports: a normal moment shows the action, not the reaction cam", vision.choose_layout("auto", seen, "split", "sports", False) != "split")
check("sports: a moment where reactions are the point brings the facecam in", vision.choose_layout("auto", seen, "split", "sports", True), "split")
check("gaming keeps the facecam as before", vision.choose_layout("auto", seen, "split", "gaming", False), "split")
two = [[(0.18, 0.25, 0.11, 0.2), (0.66, 0.27, 0.1, 0.19)] for _ in range(12)]
seen_two = vision.decide(two, blank, 1920, 1080)
check("two people in the shot all clip long are a duo", (seen_two["kind"], len(seen_two.get("faces", []))), ("duo", 2))
check("a podcast with both people in the shot shows them one above the other", vision.choose_layout("auto", seen_two, "split", "podcast"), "duo")
check("...a gaming video follows one face instead", vision.choose_layout("auto", seen_two, "split", "gaming"), "face")
check("asking for the duo layout with one person falls back to following them", vision.choose_layout("duo", seen_head), "face")
from studio import brain
check("titles give a fair guess at the kind of video without an AI",
      [brain.detect_content(t) for t in ("Beat Neymar, Win $500,000", "Valorant ranked grind", "The Diary Of A CEO Ep 212", "LA trip vlog")],
      ["sports", "gaming", "podcast", "talking"])
check("each kind of video gets its own idea of a good moment", "spicy or controversial" in brain._head("podcast", title="t", uploader="u", n=2)
      and "goals, big plays" in brain._head("sports", title="t", uploader="u", n=2))

# ---- rendering every layout for real
work = Path(tempfile.mkdtemp(prefix="cf-layouts-media-"))
src = work / "game.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=4",
                "-f", "lavfi", "-i", "sine=frequency=300:duration=4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(src)], check=True)
render.install_fonts()
words = [{"w": w, "s": 0.5 + i * 0.4, "e": 0.8 + i * 0.4} for i, w in enumerate("that was a clean clutch".split())]
cases = {"split": {"kind": "facecam", "cam": [0.8, 0.75, 0.18, 0.2], "face": list(cam_face), "hud": [True, False]},
         "gamefocus": {"kind": "facecam", "cam": [0.8, 0.75, 0.18, 0.2], "face": list(cam_face), "hud": [True, True]},
         "face": {"kind": "head", "cx": 0.3, "face": [0.25, 0.2, 0.1, 0.2]},
         "duo": {"kind": "duo", "faces": [[0.18, 0.25, 0.11, 0.2], [0.66, 0.27, 0.1, 0.19]], "face": [0.18, 0.25, 0.11, 0.2]}}
for lay, s in cases.items():
    try:
        out = render.render_clip(src, work / "out", f"c_{lay}", {"start": 0, "end": 3, "hook": "NO WAY", "layout": lay, "seen": s},
                                 words, 1280, 720)
        dims = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                               "-of", "csv=p=0", str(work / "out" / out["file"])], capture_output=True, text=True).stdout.strip()
        check(f"the {lay} layout renders a 1080x1920 clip", (out["layout"], dims), (lay, "1080,1920"))
    except Exception as e:  # noqa: BLE001
        check(f"the {lay} layout renders a 1080x1920 clip", repr(e)[:300], "no error")

print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
