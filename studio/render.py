"""Turns a time range into a vertical clip: 9:16 layout, bouncy word captions, hook title, cover."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config, roman
from .media import NO_WINDOW, run

W, H = config.OUT_W, config.OUT_H

# ASS colours are &HBBGGRR. `size` is the ASS font size (line height); _Font turns it into real pixels.
STYLES = {
    "bounce": {"label": "Bounce", "font": "Poppins ExtraBold", "size": 132, "base": "FFFFFF", "active": "00F0FF",
               "strong": "FFFFFF", "outline": 7, "pop": 112, "upper": True, "per": 3},
    "hype": {"label": "Hype", "font": "Anton", "size": 152, "base": "FFFFFF", "active": "3C3CFF",
             "strong": "00D7FF", "outline": 7, "pop": 114, "upper": True, "per": 2},
    "clean": {"label": "Clean", "font": "Poppins ExtraBold", "size": 100, "base": "FFFFFF", "active": "6BD7FF",
              "strong": "FFFFFF", "outline": 5, "pop": 106, "upper": False, "per": 4},
}
HOOK = {"font": "Poppins ExtraBold", "size": 96, "ink": "14100E", "box": "FFFFFF", "pad_x": 36, "pad_y": 22, "radius": 26,
        "max_w": 900}
FONT_FILES = {"Poppins ExtraBold": "Poppins-ExtraBold.ttf", "Anton": "Anton-Regular.ttf", "Archivo Black": "ArchivoBlack-Regular.ttf"}
CAP_MAX_W = 960   # captions never run wider than this, whatever is said


class _Font:
    """Measures text exactly as the renderer will draw it, so every word can be placed by hand: the highlighted
    word can grow without pushing its neighbours, and the heading box fits its text."""
    _cache: dict = {}

    def __init__(self, name):
        import struct
        path = Path(__file__).resolve().parent / "fonts" / FONT_FILES.get(name, FONT_FILES["Poppins ExtraBold"])
        d = path.read_bytes()
        tables = {}
        for i in range(struct.unpack(">H", d[4:6])[0]):
            tag, _, off, _ = struct.unpack(">4sIII", d[12 + 16 * i: 28 + 16 * i])
            tables[tag] = off
        self.upm = struct.unpack(">H", d[tables[b"head"] + 18: tables[b"head"] + 20])[0]
        o = tables[b"OS/2"]
        self.asc, self.desc = struct.unpack(">HH", d[o + 74: o + 78])      # what the renderer sizes the font by
        self.cap = struct.unpack(">h", d[o + 88: o + 90])[0] or int(self.upm * 0.7)
        self.path = str(path)
        self._pil = {}

    @classmethod
    def get(cls, name):
        if name not in cls._cache:
            cls._cache[name] = cls(name)
        return cls._cache[name]

    def em(self, size):
        return size * self.upm / (self.asc + self.desc)

    def width(self, text, size):
        """Pixels wide at this ASS size."""
        try:
            from PIL import ImageFont
            if "f" not in self._pil:
                self._pil["f"] = ImageFont.truetype(self.path, 200)
            return self._pil["f"].getlength(text) * self.em(size) / 200
        except Exception:  # noqa: BLE001 - no measuring library: a fair estimate keeps clips rendering
            return len(text) * self.em(size) * 0.62

    def cap_shift(self, size):
        """How far below the anchor the middle of a capital letter sits when text is centred on a point."""
        return ((self.asc - self.desc) / 2 - self.cap / 2) * size / (self.asc + self.desc)


CAPTION_LEAD = 0.0  # measured: word stamps are within 0.15 s of the voice, so no shift is needed
def install_fonts():
    """Copy the bundled caption fonts next to the data, so captions look the same on every machine and server."""
    src = Path(__file__).resolve().parent / "fonts"
    for f in src.glob("*.ttf"):
        if not (config.FONTS_DIR / f.name).exists():
            shutil.copyfile(f, config.FONTS_DIR / f.name)


LAYOUTS = {"auto": "Auto (finds the facecam, the speaker or the action)",
           "split": "Facecam on top, gameplay below",
           "gamefocus": "Gameplay with a floating round facecam",
           "pip": "Gameplay with a floating facecam window",
           "game": "Gameplay only, framed on the action",
           "face": "Follow the speaker's face",
           "blur": "Full frame + blurred fill", "zoom": "Zoomed in + blurred fill", "crop": "Fill the screen (centre crop)"}
CAM_H = 640                    # split layout: the facecam panel on top (its height follows the webcam's shape)
BUBBLE = 400                   # gamefocus layout: the round facecam, in pixels
PIP_W = 470                    # pip layout: the floating facecam window's width
FLOAT_TOP = 150                # the floating facecam sits at the top centre, below the apps' own top buttons
CAP_BGS = {"none": "Outline only", "box": "Dark box behind the words", "word": "Highlight box on the spoken word"}


def cam_height(seen, src_w, src_h) -> int:
    """Split layout: the facecam panel keeps the webcam's own shape, between a third and nearly half the screen."""
    cam = (seen or {}).get("cam")
    if not cam or not src_w:
        return CAM_H
    ar = (cam[2] * src_w) / max(1, cam[3] * src_h)
    return _even(min(900, max(560, W / max(0.5, ar))))


def _ts(t):
    t = max(0.0, t)
    h, m = int(t // 3600), int(t % 3600 // 60)
    return f"{h}:{m:02d}:{t % 60:05.2f}"


def _clean(text):
    return re.sub(r"[\x00-\x1f\x7f]+", " ", re.sub(r"[{}\\]", "", str(text))).strip()


def _key(word):
    return re.sub(r"[^a-z0-9']", "", word.lower())


def _groups(words, per):
    out, cur = [], []
    for w in words:
        if cur and (len(cur) >= per or sum(len(x["w"]) for x in cur) + len(w["w"]) > 16
                    or w["s"] - cur[-1]["e"] > 0.45 or cur[-1]["w"][-1:] in ".?!"):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def geometry(src_w, src_h, layout, seen=None):
    """Where the video sits in the 1080x1920 frame, and where hook and captions go."""
    if src_h >= src_w and layout != "crop":
        layout = "crop"  # already vertical or square: nothing to gain from a blurred fill
    if layout == "split":
        ch = cam_height(seen, src_w, src_h)
        return layout, H, ch, ch + int((H - ch) * 0.6)  # hook sits on the seam, captions over the gameplay
    if layout in ("gamefocus", "pip"):            # facecam floats at the top centre: hook just under it, captions low
        return layout, H, FLOAT_TOP + float_height(layout, seen, src_w, src_h) + 40, 1400
    if layout in ("face", "game"):
        return layout, H, 300, 1380
    if layout == "blur":
        fg_h = min(H, int(round(W * src_h / src_w / 2)) * 2)
    elif layout == "zoom":
        fg_h = 1000
    else:
        fg_h = H
    top = (H - fg_h) // 2
    if layout == "crop":
        return layout, fg_h, 300, 1380
    return layout, fg_h, max(230, top - 190), min(1640, top + fg_h + 180)


def float_height(layout, seen, src_w, src_h) -> int:
    """How tall the floating facecam is on the 1080x1920 frame (circle or window, white border included)."""
    if layout == "gamefocus":
        return BUBBLE + 14
    cam = (seen or {}).get("cam")
    if not cam or not src_w or not src_h:
        return 300
    return _even(PIP_W * cam[3] * src_h / max(1, cam[2] * src_w)) + 12


def _rrect(x0, y0, x1, y1, r) -> str:
    """An ASS drawing of a rounded rectangle."""
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    n = lambda v: f"{v:.0f}"                                                         # noqa: E731
    return (f"m {n(x0 + r)} {n(y0)} l {n(x1 - r)} {n(y0)} b {n(x1)} {n(y0)} {n(x1)} {n(y0)} {n(x1)} {n(y0 + r)} "
            f"l {n(x1)} {n(y1 - r)} b {n(x1)} {n(y1)} {n(x1)} {n(y1)} {n(x1 - r)} {n(y1)} "
            f"l {n(x0 + r)} {n(y1)} b {n(x0)} {n(y1)} {n(x0)} {n(y1)} {n(x0)} {n(y1 - r)} "
            f"l {n(x0)} {n(y0 + r)} b {n(x0)} {n(y0)} {n(x0)} {n(y0)} {n(x0 + r)} {n(y0)}")


def _hook_events(hook, dur, y):
    """The heading: dark text in a white rounded box that fits it, on one line or two balanced ones."""
    f, size = _Font.get(HOOK["font"]), HOOK["size"]
    words = hook.split()
    if not words:
        return []
    lines = [" ".join(words)]
    if f.width(lines[0], size) > HOOK["max_w"] and len(words) > 1:      # two lines, split where they come out most even
        cut = min(range(1, len(words)), key=lambda i: max(f.width(" ".join(words[:i]), size), f.width(" ".join(words[i:]), size)))
        lines = [" ".join(words[:cut]), " ".join(words[cut:])]
    widest = max(f.width(l, size) for l in lines)
    if widest > HOOK["max_w"]:
        size = max(40, int(size * HOOK["max_w"] / widest))
        widest = max(f.width(l, size) for l in lines)
    line_h = f.em(size) * 1.16
    bw, bh = widest + 2 * HOOK["pad_x"], line_h * len(lines) + 2 * HOOK["pad_y"]
    x0, y0, r = (W - bw) / 2, y - bh / 2, min(HOOK["radius"], bh / 2)
    x1, y1 = x0 + bw, y0 + bh
    n = lambda v: f"{v:.0f}"                                                         # noqa: E731
    box = (f"m {n(x0 + r)} {n(y0)} l {n(x1 - r)} {n(y0)} b {n(x1)} {n(y0)} {n(x1)} {n(y0)} {n(x1)} {n(y0 + r)} "
           f"l {n(x1)} {n(y1 - r)} b {n(x1)} {n(y1)} {n(x1)} {n(y1)} {n(x1 - r)} {n(y1)} "
           f"l {n(x0 + r)} {n(y1)} b {n(x0)} {n(y1)} {n(x0)} {n(y1)} {n(x0)} {n(y1 - r)} "
           f"l {n(x0)} {n(y0 + r)} b {n(x0)} {n(y0)} {n(x0)} {n(y0)} {n(x0 + r)} {n(y0)}")
    span = f"{_ts(0)},{_ts(dur)}"
    ev = [f"Dialogue: 3,{span},Hook,,0,0,0,,{{\\an7\\pos(0,0)\\fad(160,0)\\c&H{HOOK['box']}&\\p1}}{box}{{\\p0}}"]
    for i, line in enumerate(lines):
        cy = y - line_h * (len(lines) - 1) / 2 + i * line_h - f.cap_shift(size)
        ev.append(f"Dialogue: 4,{span},Hook,,0,0,0,,{{\\an5\\pos({W // 2},{cy:.0f})\\fad(160,0)\\fs{size}}}{line}")
    return ev


def build_ass(words, start, end, hook, style_name, highlight, hook_y, cap_y, cap_bg="none") -> str:
    st = STYLES.get(style_name, STYLES["bounce"])
    cap_bg = cap_bg if cap_bg in CAP_BGS else "none"
    words = [dict(w, s=w["s"] - CAPTION_LEAD, e=w["e"] - CAPTION_LEAD) for w in words]
    strong = {_key(h) for h in highlight if _key(h)}
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{st['font']},{st['size']},&H00{st['base']},&H00{st['base']},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,{st['outline']},0,5,0,0,0,1
Style: Hook,{HOOK['font']},{HOOK['size']},&H00{HOOK['ink']},&H00{HOOK['ink']},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dur = end - start
    ev = _hook_events(_clean(hook), dur, hook_y)
    f = _Font.get(st["font"])
    inside = [dict(w, w=_clean(w["w"])) for w in words if w["s"] >= start - 0.05 and w["s"] < end]
    inside = sorted((w for w in inside if w["w"]), key=lambda w: w["s"])
    for i, w in enumerate(inside[:-1]):
        w["e"] = max(w["s"], min(w["e"], inside[i + 1]["s"]))
    groups = _groups(inside, st["per"])
    for gi, g in enumerate(groups):
        g_start = max(0.0, g[0]["s"] - start)
        g_end = min(g[-1]["e"] + 0.25, groups[gi + 1][0]["s"] if gi + 1 < len(groups) else end) - start
        if g_end - g_start < 0.02:
            continue
        texts = []
        for x in g:
            t = re.sub(r"[.,;:]+$", "", x["w"])
            texts.append(t.upper() if st["upper"] else t)
        if not all(roman.drawable(t) for t in texts):
            # A script the caption font cannot draw (Japanese, Thai, Chinese...): its words cannot be measured, so
            # they are not placed one by one. The line is drawn whole and centred, in a font the system has for it.
            line = " ".join(texts)
            fs = max(44, min(int(st["size"] * 0.7), int(1500 / max(1, len(line)) * 1.6)))
            ev.append(f"Dialogue: 1,{_ts(g_start)},{_ts(g_end)},Cap,,60,60,0,,{{\\an5\\pos({W // 2},{cap_y:.0f})\\q0\\fs{fs}}}{line}")
            continue
        size = st["size"]
        gap = f.width("n n", size) - 2 * f.width("n", size) + (2 * st["outline"] + 6) * size / st["size"]   # a space, plus room for both outlines
        total = sum(f.width(t, size) for t in texts) + gap * (len(texts) - 1)
        if total > CAP_MAX_W:                                  # a long phrase: shrink it to fit, never run off the frame
            size = max(36, int(size * CAP_MAX_W / total))
            gap = f.width("n n", size) - 2 * f.width("n", size) + (2 * st["outline"] + 6) * size / st["size"]   # a space, plus room for both outlines
            total = sum(f.width(t, size) for t in texts) + gap * (len(texts) - 1)
        cy = cap_y - f.cap_shift(size)
        x = (W - total) / 2
        p = st["pop"]
        line_h = f.em(size) * 1.0
        if cap_bg == "box":                                   # one dark rounded box behind the whole line
            ev.append(f"Dialogue: 0,{_ts(g_start)},{_ts(g_end)},Cap,,0,0,0,,{{\\an7\\pos(0,0)\\bord0\\shad0\\c&H000000&\\1a&H48&\\p1}}"
                      f"{_rrect(x - 34, cap_y - line_h * 0.62, x + total + 34, cap_y + line_h * 0.62, 26)}{{\\p0}}")
        for i, (w, t) in enumerate(zip(g, texts)):
            wd = f.width(t, size)
            p = max(104, min(st["pop"], 100 + int(2200 / max(wd, 1))))   # long words grow less, so they never touch their neighbours
            pos = f"\\an5\\pos({x + wd / 2:.0f},{cy:.0f})\\fs{size}"
            x += wd + gap
            a = max(g_start, w["s"] - start)
            b = (g[i + 1]["s"] - start) if i + 1 < len(g) else g_end
            base = st["strong"] if _key(w["w"]) in strong else st["base"]
            if a - g_start >= 0.02:                                                   # waiting to be said
                ev.append(f"Dialogue: 1,{_ts(g_start)},{_ts(a)},Cap,,0,0,0,,{{{pos}\\c&H{base}&}}{t}")
            if b - a >= 0.02 and cap_bg == "word":                                   # being said: a coloured box behind it
                bx0 = x - wd - gap - 16
                ev.append(f"Dialogue: 2,{_ts(a)},{_ts(b)},Cap,,0,0,0,,{{\\an7\\pos(0,0)\\bord0\\shad0\\c&H{st['active']}&\\p1}}"
                          f"{_rrect(bx0, cap_y - line_h * 0.6, bx0 + wd + 32, cap_y + line_h * 0.6, 18)}{{\\p0}}")
                ev.append(f"Dialogue: 3,{_ts(a)},{_ts(b)},Cap,,0,0,0,,{{{pos}\\c&H14100E&\\bord0}}{t}")
            elif b - a >= 0.02:                                                       # being said: colour and a quick pop, in front
                ev.append(f"Dialogue: 2,{_ts(a)},{_ts(b)},Cap,,0,0,0,,{{{pos}\\c&H{st['active']}&\\fscx94\\fscy94"
                          f"\\t(0,90,\\fscx{p}\\fscy{p})\\t(90,200,\\fscx{p - 5}\\fscy{p - 5})}}{t}")
            if g_end - b >= 0.02:                                                     # said
                ev.append(f"Dialogue: 1,{_ts(b)},{_ts(g_end)},Cap,,0,0,0,,{{{pos}\\c&H{base}&\\fscx{p - 5}\\fscy{p - 5}"
                          f"\\t(0,90,\\fscx100\\fscy100)}}{t}")
    return head + "\n".join(ev) + "\n"


def _even(v) -> int:
    """Rounded down to an even number of pixels (video sizes and offsets must be even). Never below 0."""
    return max(0, int(v) // 2 * 2)


def _game_window(src_w, src_h, aspect, hud, cx=None):
    """Where the gameplay crop sits, as (x, width) in source pixels, or None to show the whole width.
    It is centred on the action when that is known (`cx`, 0-1), else on the middle (an FPS crosshair); a HUD on one
    side pulls it to that side; HUDs on both sides mean the whole width is shown."""
    gw = max(2, _even(src_h * aspect))
    if gw >= src_w:
        return None
    left, right = (list(hud or []) + [False, False])[:2]
    if left and right:
        return None
    if left:
        x = 0
    elif right:
        x = src_w - gw
    else:
        x = (cx if cx is not None else 0.5) * src_w - gw / 2
    return min(max(0, _even(x)), _even(src_w - gw)), gw


def _panel(label_in, label_out, src_w, src_h, pw, ph, hud, cx=None):
    """Gameplay into a pw x ph panel: cropped to fill it (keeping a HUD in view), or the whole width over a blur."""
    win = _game_window(src_w, src_h, pw / ph, hud, cx)
    if win:
        x, gw = win
        return (f"[{label_in}]crop={gw}:{_even(src_h)}:{x}:0,scale={pw}:{ph}:force_original_aspect_ratio=increase,"
                f"crop={pw}:{ph}[{label_out}];")
    fg_h = min(ph, _even(pw * src_h / max(1, src_w)))
    return (f"[{label_in}]split=2[{label_out}a][{label_out}b];"
            f"[{label_out}a]scale=270:{_even(270 * ph / pw)}:force_original_aspect_ratio=increase,"
            f"crop=270:{_even(270 * ph / pw)},boxblur=6:2,scale={pw}:{ph},eq=brightness=-0.14:saturation=1.15[{label_out}c];"
            f"[{label_out}b]scale={pw}:{fg_h}[{label_out}d];[{label_out}c][{label_out}d]overlay=0:(H-h)/2[{label_out}];")


def _box_px(box, src_w, src_h):
    x, y, w, h = box
    pw, ph = max(2, _even(w * src_w)), max(2, _even(h * src_h))
    px = min(max(0, _even(x * src_w)), _even(src_w - pw))
    py = min(max(0, _even(y * src_h)), _even(src_h - ph))
    return px, py, pw, ph


def _action_cx(seen, aspect=None, src_w=0, src_h=0):
    """The horizontal centre of the action (0-1): the AI's subject box, else the middle. When the webcam sits at one
    side, the gameplay window is moved just clear of it so no sliver of the webcam shows in the gameplay."""
    seen = seen or {}
    sub = seen.get("subject")
    cx = sub[0] + sub[2] / 2 if sub and sub[2] < 0.95 else None
    cam = seen.get("cam")
    if cam and aspect and src_w and src_h:
        gw = min(1.0, src_h * aspect / src_w)                # the window's width, as a share of the frame
        c = cx if cx is not None else 0.5
        x0, x1 = c - gw / 2, c + gw / 2
        cam_l, cam_r = cam[0], cam[0] + cam[2]
        if x0 < cam_r <= 0.5 and cam_r + gw <= 1.0:
            cx = cam_r + gw / 2                              # webcam on the left: start right after it
        elif x1 > cam_l >= 0.5 and cam_l - gw >= 0.0:
            cx = cam_l - gw / 2                              # webcam on the right: end just before it
    return cx


def _chain(inp, out, layout, fg_h, src_w, src_h, seen, t=""):
    """The ffmpeg filters that turn input label `inp` into a 1080x1920 picture labelled `out`.
    `t` makes every inner label unique, so several of these can live in one graph (one per scene)."""
    seen = seen or {}
    L = lambda n: f"{n}{t}"                                                          # noqa: E731
    head = f"[{inp}]fps={config.OUT_FPS},setsar=1"
    if layout == "split" and seen.get("cam"):
        ch = cam_height(seen, src_w, src_h)
        cx, cy, cw, chh = _box_px(seen["cam"], src_w, src_h)
        return (f"{head},split=2[{L('c')}][{L('g')}];[{L('c')}]crop={cw}:{chh}:{cx}:{cy},scale={W}:{ch}:force_original_aspect_ratio=increase,"
                f"crop={W}:{ch}[{L('cam')}];" + _panel(L("g"), L("game"), src_w, src_h, W, H - ch, seen.get("hud"), _action_cx(seen, W / (H - ch), src_w, src_h))
                + f"[{L('cam')}][{L('game')}]vstack=inputs=2,setsar=1[{out}];")
    if layout in ("gamefocus", "pip") and seen.get("cam"):
        cx, cy, cw, chh = _box_px(seen["cam"], src_w, src_h)
        game = _panel(L("g"), L("game"), src_w, src_h, W, H, seen.get("hud"), _action_cx(seen, W / H, src_w, src_h))
        if layout == "gamefocus":                      # a circle around the face, from inside the webcam box
            fx, fy, fw, fh = seen.get("face") or (seen["cam"][0] + seen["cam"][2] * .3, seen["cam"][1] + seen["cam"][3] * .2,
                                                     seen["cam"][2] * .4, seen["cam"][3] * .5)
            side = _even(min(chh, cw, max(fw * src_w, fh * src_h) * 2.6))
            bx = min(max(cx, _even((fx + fw / 2) * src_w - side / 2)), _even(cx + cw - side))
            by = min(max(cy, _even((fy + fh / 2) * src_h - side / 2)), _even(cy + chh - side))
            r, ring = BUBBLE // 2, BUBBLE // 2 + 7
            return (f"{head},split=2[{L('c')}][{L('g')}];" + game
                    + f"[{L('c')}]crop={side}:{side}:{bx}:{by},scale={BUBBLE}:{BUBBLE},format=yuva420p,"
                    f"geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='if(lte(hypot(X-{r},Y-{r}),{r - 1}),255,0)'[{L('bub')}];"
                    f"color=c=white:s={2 * ring}x{2 * ring},format=yuva420p,geq=lum=255:cb=128:cr=128:a='if(lte(hypot(X-{ring},Y-{ring}),{ring}),255,0)'[{L('ring')}];"
                    f"[{L('game')}][{L('ring')}]overlay={(W - 2 * ring) // 2}:{FLOAT_TOP}:shortest=1[{L('gr')}];"
                    f"[{L('gr')}][{L('bub')}]overlay={(W - BUBBLE) // 2}:{FLOAT_TOP + 7}:format=auto,setsar=1[{out}];")
        ph = _even(PIP_W * chh / max(1, cw))           # the webcam as a floating window with rounded corners
        rr = 26
        a = (f"if(gt(abs(X-W/2),W/2-{rr})*gt(abs(Y-H/2),H/2-{rr}),"
             f"if(lte(hypot(abs(X-W/2)-(W/2-{rr}),abs(Y-H/2)-(H/2-{rr})),{rr}),255,0),255)")
        return (f"{head},split=2[{L('c')}][{L('g')}];" + game
                + f"[{L('c')}]crop={cw}:{chh}:{cx}:{cy},scale={PIP_W}:{ph},pad={PIP_W + 12}:{ph + 12}:6:6:white,format=yuva420p,"
                f"geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='{a}'[{L('pip')}];"
                f"[{L('game')}][{L('pip')}]overlay={(W - PIP_W - 12) // 2}:{FLOAT_TOP}:format=auto,setsar=1[{out}];")
    if layout == "face" and (seen.get("cx") is not None or seen.get("face")):
        cxf = seen.get("cx")
        if cxf is None:
            fx, _, fw, _ = seen["face"]
            cxf = fx + fw / 2
        cw = min(_even(src_w), _even(src_h * W / H))
        x = min(max(0, _even(cxf * src_w - cw / 2)), _even(src_w - cw))
        return f"{head},crop={cw}:{_even(src_h)}:{x}:0,scale={W}:{H},setsar=1[{out}];"
    if layout == "game":
        return (f"{head}[{L('g')}];" + _panel(L("g"), L("gp"), src_w, src_h, W, H, seen.get("hud"), _action_cx(seen, W / H, src_w, src_h))
                + f"[{L('gp')}]setsar=1[{out}];")
    if layout in ("split", "gamefocus", "pip", "face"):
        layout, fg_h = "blur", min(H, int(round(W * src_h / max(1, src_w) / 2)) * 2) if src_w else H
    if layout == "crop":
        return f"{head},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[{out}];"
    return (f"{head},split=2[{L('a')}][{L('b')}];"
            f"[{L('a')}]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=6:2,"
            f"scale={W}:{H},eq=brightness=-0.14:saturation=1.15[{L('bg')}];"
            f"[{L('b')}]scale={W}:{fg_h}:force_original_aspect_ratio=increase,crop={W}:{fg_h}[{L('fg')}];"
            f"[{L('bg')}][{L('fg')}]overlay=0:(H-h)/2,setsar=1[{out}];")


def _filter(layout, fg_h, src_w=0, src_h=0, seen=None, parts=None):
    """The whole picture graph, ending in [v0]. `parts` = [(t0, t1, layout, seen), ...] frames each scene of the clip
    on its own and joins them back into one continuous clip."""
    if not parts or len(parts) == 1:
        if parts:
            layout, seen = parts[0][2], parts[0][3]
        return _chain("0:v", "v0", layout, fg_h, src_w, src_h, seen)
    n = len(parts)
    g = f"[0:v]split={n}" + "".join(f"[i{k}]" for k in range(n)) + ";"
    for k, (t0, t1, lay, sn) in enumerate(parts):
        g += f"[i{k}]trim=start={t0:.3f}:end={t1:.3f},setpts=PTS-STARTPTS[t{k}];"
        _, fh, _, _ = geometry(src_w, src_h, lay, sn)
        g += _chain(f"t{k}", f"s{k}", lay, fh, src_w, src_h, sn, t=f"_{k}")
    g += "".join(f"[s{k}]scale={W}:{H},setsar=1[u{k}];" for k in range(n))      # every scene exactly the same shape
    return g + "".join(f"[u{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0,setsar=1[v0];"


_qsv_ok = None
RENDER_SECONDS = 600      # one clip's video encode; far beyond normal, so a frozen encoder is stopped, not waited on


def render_clip(src: Path, out_dir: Path, name: str, clip: dict, words: list, src_w: int, src_h: int) -> dict:
    """Writes <name>.mp4, <name>.jpg and <name>.ass into out_dir. Returns file names."""
    out_dir.mkdir(parents=True, exist_ok=True)
    start, end = clip["start"], clip["end"]
    wanted = clip.get("layout", "blur")
    cam_style = clip.get("cam_style") or "split"
    seen, parts = {}, None
    if wanted in ("auto", "split", "gamefocus", "pip", "game", "face"):
        from . import vision
        seen = clip.get("seen") or vision.analyze(src, start, end, src_w, src_h)
        if seen.get("kind") == "multi":
            parts = [(g["t0"], g["t1"], vision.choose_layout(wanted, g, cam_style), g) for g in seen["segments"]]
            main = max(parts, key=lambda q: q[1] - q[0])          # captions sit where the longest scene wants them
            wanted, main_seen = main[2], main[3]
        else:
            wanted, main_seen = vision.choose_layout(wanted, seen, cam_style), seen
    else:
        main_seen = {}
    layout, fg_h, hook_y, cap_y = geometry(src_w, src_h, wanted, main_seen)
    ass = build_ass(words, start, end, clip.get("hook", ""), clip.get("style", "bounce"),
                    clip.get("highlight_words", []), hook_y, cap_y, clip.get("cap_bg") or "none")
    # The clip is made in a short work folder and moved into place afterwards. The caption step of ffmpeg cannot
    # open files whose full path is longer than 260 characters on Windows, which a data folder deep inside other
    # folders easily reaches. Inside the work folder every name is short and relative (a drive colon would also
    # break the filter syntax).
    work = Path(tempfile.mkdtemp(prefix="pk"))
    try:
        out = _render_in(work, src, out_dir, name, start, end, layout, fg_h, ass, src_w, src_h, main_seen, parts)
        out["seen"] = seen
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _render_in(work: Path, src: Path, out_dir: Path, name: str, start, end, layout, fg_h, ass: str,
               src_w=0, src_h=0, seen=None, parts=None) -> dict:
    global _qsv_ok
    (work / f"{name}.ass").write_text(ass, encoding="utf-8")
    (work / "f").mkdir()
    for f in config.FONTS_DIR.glob("*.ttf"):
        shutil.copyfile(f, work / "f" / f.name)
    fc = _filter(layout, fg_h, src_w, src_h, seen, parts) + f"[v0]ass={name}.ass:fontsdir=f[v]"
    base = ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{end - start:.2f}", "-i", str(src),
            "-filter_complex", fc, "-map", "[v]", "-map", "0:a:0", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", "-pix_fmt"]
    encoders = []
    if _qsv_ok is not False:
        encoders.append(("qsv", ["nv12", "-c:v", "h264_qsv", "-global_quality", "23", "-preset", "fast"]))
    encoders.append(("x264", ["yuv420p", "-c:v", "libx264", "-crf", "19", "-preset", "fast", "-profile:v", "high"]))
    err = None
    for label, enc in encoders:
        p = subprocess.run(base + enc + [f"{name}.mp4"], cwd=work, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=NO_WINDOW, timeout=RENDER_SECONDS)
        if p.returncode == 0:
            if label == "qsv":
                _qsv_ok = True
            break
        err = p.stderr[-1200:]
        if label == "qsv":
            _qsv_ok = False
    else:
        raise RuntimeError(f"Render failed: {err}")
    cover_t = min(1.2, (end - start) / 2)
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{cover_t:.2f}", "-i", f"{name}.mp4", "-frames:v", "1",
         "-q:v", "3", f"{name}.jpg"], cwd=work)
    for ext in ("mp4", "jpg", "ass"):
        shutil.move(str(work / f"{name}.{ext}"), str(out_dir / f"{name}.{ext}"))
    return {"file": f"{name}.mp4", "cover": f"{name}.jpg", "layout": layout}
