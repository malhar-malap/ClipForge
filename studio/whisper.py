"""Speech to text for languages other than English (Hindi, Hinglish, Urdu, Spanish...), with faster-whisper.

The main speech model (Parakeet, in transcribe.py) only understands English. Whisper understands about 100
languages, so it takes over when a video is not in English. It runs on this machine too: audio never leaves it.

Optional: if faster-whisper is not installed, everything falls back to the English model, as before.
The model is chosen with CLIPFORGE_WHISPER_MODEL (default "small": about 480 MB, downloaded once on first use).
"""
import os
import threading

import numpy as np

MODEL = os.environ.get("CLIPFORGE_WHISPER_MODEL", "small").strip() or "small"
DEVICE = os.environ.get("CLIPFORGE_WHISPER_DEVICE", "auto").strip() or "auto"
_lock = threading.Lock()
_model = None


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _get():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel
            from . import config
            _model = WhisperModel(MODEL, device=DEVICE, compute_type="int8",
                                  download_root=str(config.MODELS_DIR / "whisper"))
        return _model


def _float(audio: np.ndarray) -> np.ndarray:
    a = np.asarray(audio)
    return a.astype(np.float32) / 32768.0 if a.dtype != np.float32 else a


def detect_language(audio: np.ndarray) -> tuple:
    """(language code, confidence) for 16 kHz audio. Looks at up to 30 seconds."""
    sample = _float(audio)[: 30 * 16000]
    _segments, info = _get().transcribe(sample, beam_size=1, without_timestamps=True)   # language is known before any text
    return info.language or "", float(info.language_probability or 0.0)


def pick_sample(audio: np.ndarray, lo: int, hi: int) -> np.ndarray:
    """The loudest 30 seconds in the middle part of the video: the best chance of hearing speech, not an intro."""
    a, b = lo + (hi - lo) // 4, hi - (hi - lo) // 4
    if b - a <= 30 * 16000:
        return audio[lo:hi][: 30 * 16000]
    step = 15 * 16000
    best, best_rms = a, -1.0
    for x in range(a, b - 30 * 16000, step):
        seg = audio[x: x + 30 * 16000].astype(np.float32)
        rms = float(np.sqrt((seg ** 2).mean()))
        if rms > best_rms:
            best, best_rms = x, rms
    return audio[best: best + 30 * 16000]


def transcribe(audio: np.ndarray, lang: str, on_progress=None) -> list:
    """[{'w', 's', 'e'}] with word timings, in the language spoken (Hindi comes out in Devanagari; captions turn it
    into Roman letters later)."""
    a = _float(audio)
    total = max(1.0, len(a) / 16000)
    segments, _info = _get().transcribe(a, language=(lang or None), word_timestamps=True, vad_filter=True,
                                        beam_size=1, condition_on_previous_text=False)
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = (w.word or "").strip()
            if text:
                words.append({"w": text, "s": round(float(w.start), 2), "e": round(float(w.end), 2)})
        if on_progress:
            on_progress(min(1.0, float(seg.end) / total))
    return words
