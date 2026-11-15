"""Looks at a clip's frames and decides how to lay it out in 9:16.

Everything runs on this machine with OpenCV: no frames are ever sent to an AI service.

What it finds, from about one frame per second of the clip:
- a facecam: a face that stays in the same small spot (a webcam box in a corner of gameplay),
- a talking head: a large face, or a face that is the main subject,
- the HUD: parts of the picture that never change and have sharp detail (health bar, minimap, score),
  so a gameplay crop can keep them in view.

The answer is a plain dict that render.py turns into ffmpeg filters. If OpenCV is missing or anything goes wrong,
`analyze` returns {"kind": "none"} and the clip falls back to the full-frame layout, so a clip is never lost to this.
"""
import subprocess

import numpy as np

from .media import NO_WINDOW

SAMPLE_W = 480            # frames are looked at this wide: enough for a small facecam, cheap to scan
MAX_SAMPLES = 40
CAM_MAX_AREA = 0.06       # a face box under this share of the frame can be a facecam
CAM_MIN_SHARE = 0.55      # ...if it is in the same place in at least this share of the frames
HEAD_MIN_AREA = 0.012     # a face this big (or bigger) that is not a facecam is a talking head


def _frames(src, start, dur, src_w, src_h):
    """Grey frames of the clip, SAMPLE_W wide, about one per second (at most MAX_SAMPLES)."""
    h = max(2, int(round(SAMPLE_W * src_h / max(1, src_w) / 2)) * 2)
    fps = min(1.0, MAX_SAMPLES / max(dur, 1.0))
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, start):.2f}", "-t", f"{max(0.5, dur):.2f}", "-i", str(src),
           "-vf", f"fps={fps:.4f},scale={SAMPLE_W}:{h},format=gray", "-f", "rawvideo", "-"]
    p = subprocess.run(cmd, capture_output=True, timeout=300, creationflags=NO_WINDOW)
    raw = p.stdout
    n = len(raw) // (SAMPLE_W * h)
    if n == 0:
        return np.zeros((0, h, SAMPLE_W), dtype=np.uint8)
    return np.frombuffer(raw[: n * SAMPLE_W * h], dtype=np.uint8).reshape(n, h, SAMPLE_W)


def _detector():
    import cv2
    return cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def _faces(frames):
    """Per frame: face boxes as fractions of the frame (x, y, w, h)."""
    import cv2
    det = _detector()
    fh, fw = frames.shape[1], frames.shape[2]
    out = []
    for f in frames:
        g = cv2.equalizeHist(f)
        boxes = det.detectMultiScale(g, scaleFactor=1.1, minNeighbors=5, minSize=(16, 16))
        out.append([(x / fw, y / fh, w / fw, h / fh) for (x, y, w, h) in (boxes if len(boxes) else [])])
    return out


def _clusters(per_frame):
    """Group face boxes that sit in the same place across frames. Returns [(share of frames, median box)]."""
    groups = []                                   # [[boxes], set(frame indexes)]
    for i, boxes in enumerate(per_frame):
        for b in boxes:
            cx, cy = b[0] + b[2] / 2, b[1] + b[3] / 2
            for g in groups:
                m = np.median(np.array(g[0]), axis=0)
                if abs(cx - (m[0] + m[2] / 2)) < max(0.04, m[2] * 0.6) and abs(cy - (m[1] + m[3] / 2)) < max(0.05, m[3] * 0.6):
                    g[0].append(b)
                    g[1].add(i)
                    break
            else:
                groups.append([[b], {i}])
    n = max(1, len(per_frame))
    found = [(len(g[1]) / n, tuple(float(v) for v in np.median(np.array(g[0]), axis=0)), np.array(g[0])) for g in groups]
    return sorted(found, key=lambda x: -x[0])


def _hud(frames, cam=None):
    """Which side edges hold a HUD: static pixels with sharp detail. Returns (left, right) booleans."""
    if len(frames) < 4:
        return False, False
    import cv2
    stack = frames.astype(np.float32)
    still = stack.std(axis=0) < 6.0                                 # barely changes across the clip
    edges = np.mean([np.abs(cv2.Laplacian(f, cv2.CV_32F)) for f in frames[:: max(1, len(frames) // 8)]], axis=0) > 18
    mask = still & edges
    h, w = mask.shape
    if cam:                                                         # the facecam's border is static too: not a HUD
        x, y, cw, ch = cam
        px, py = cw * 0.4, ch * 0.4                                 # the webcam box is often bigger than our guess
        mask[max(0, int((y - py) * h)): int((y + ch + py) * h), max(0, int((x - px) * w)): int((x + cw + px) * w)] = False
    strip = int(w * 0.22)
    left, right = mask[:, :strip].mean(), mask[:, w - strip:].mean()
    middle = mask[:, strip: w - strip].mean()
    return bool(left > 0.012 and left > middle * 2.5), bool(right > 0.012 and right > middle * 2.5)


def _cam_box(face, aspect):
    """The webcam box around a facecam face: head and shoulders, at the panel's aspect ratio (fractions)."""
    x, y, w, h = face
    cw = min(1.0, w * 3.0)
    ch = min(1.0, cw / aspect)
    cx, cy = x + w / 2, y + h / 2 + h * 0.15
    cx0 = min(max(0.0, cx - cw / 2), 1.0 - cw)
    cy0 = min(max(0.0, cy - ch / 2), 1.0 - ch)
    return (round(cx0, 4), round(cy0, 4), round(cw, 4), round(ch, 4))


def decide(per_frame, frames, src_w, src_h):
    """The layout for a clip, from its faces and frames. Pure logic: easy to test with made-up faces."""
    landscape = src_w > src_h * 1.05
    clusters = _clusters(per_frame)
    if not landscape:
        return {"kind": "none"}
    frame_aspect = src_w / max(1, src_h)
    for share, box, boxes in clusters:
        area = box[2] * box[3]
        steady = len(boxes) > 1 and float(np.std(boxes[:, 0])) < 0.02 and float(np.std(boxes[:, 1])) < 0.02
        cx = box[0] + box[2] / 2
        off_centre = abs(cx - 0.5) > 0.18 or box[1] > 0.55 or box[1] + box[3] < 0.35
        if share >= CAM_MIN_SHARE and area <= CAM_MAX_AREA and steady and off_centre:
            # panel 1080x640 (16:9-ish) in source fractions: width/height ratio adjusted for the frame's own shape
            cam = _cam_box(box, (1080 / 640) / frame_aspect)
            left, right = _hud(frames, cam)
            return {"kind": "facecam", "cam": cam, "face": [round(v, 4) for v in box], "hud": [left, right]}
    if clusters:
        share, box, _ = clusters[0]
        if share >= 0.4 and box[2] * box[3] >= HEAD_MIN_AREA:
            return {"kind": "head", "cx": round(box[0] + box[2] / 2, 4), "face": [round(v, 4) for v in box]}
    left, right = _hud(frames)
    return {"kind": "none", "hud": [left, right]}


def analyze(src, start, end, src_w, src_h) -> dict:
    """Look at the clip from `start` to `end` seconds of `src` and say what is in it."""
    try:
        frames = _frames(src, start, end - start, src_w, src_h)
        if len(frames) == 0:
            return {"kind": "none"}
        return decide(_faces(frames), frames, src_w, src_h)
    except Exception:  # noqa: BLE001 - no OpenCV, an odd file: the clip still renders in the full-frame layout
        return {"kind": "none"}


def choose_layout(requested: str, seen: dict) -> str:
    """What `auto` becomes for this clip, and whether a chosen gaming layout can work at all."""
    kind = (seen or {}).get("kind", "none")
    if requested == "auto":
        return {"facecam": "split", "head": "face"}.get(kind, "blur")
    if requested in ("split", "gamefocus") and kind != "facecam":
        return "blur"            # no facecam in this clip: show the whole picture instead of an empty panel
    if requested == "face" and kind not in ("head", "facecam"):
        return "crop"
    return requested
