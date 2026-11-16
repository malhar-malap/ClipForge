"""YouTube captions and audio: the transcript and sound used must be the original language, never a translation
or an AI dub (videos with dubbed audio list many languages). No network: made-up video info."""
import os, sys, tempfile
os.environ.update({"PEAKCUT_DATA": tempfile.mkdtemp(prefix="cf-yt-"), "DATABASE_URL": ""})
sys.path.insert(0, ".")
from studio import media, roman
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)
dubbed = {"formats": [{"acodec": "mp4a", "language": "ar", "format_note": "Arabic (dubbed)"},
                      {"acodec": "mp4a", "language": "en-US", "format_note": "English (US) original (default), medium"},
                      {"acodec": "none", "vcodec": "avc1"}]}
auto = {"ar-orig": [{}], "en-orig": [{}], "en": [{}], "fr": [{}]}
check("a dubbed video: the spoken language is the track marked original", media._spoken_language(dubbed), "en-US")
check("...and its English transcript is used, not the Arabic one", media._original_track(dubbed, auto), "en-orig")
check("no original marked, one -orig track: that one", media._original_track({"formats": []}, {"hi-orig": [{}], "en": [{}]}), "hi-orig")
check("no way to tell which is original: none (our own model transcribes)", media._original_track({"formats": []}, {"ar-orig": [{}], "en-orig": [{}]}), None)
check("the language YouTube gives the video is used when no track says original", media._original_track({"language": "hi", "formats": []}, {"hi": [{}], "en": [{}]}), "hi")
check("downloads ask for the original audio first", "format_note*=original" in media._video_format(1080))
check("Arabic letters with hamza are spelled, not shown as symbols", roman.to_roman("إلى لوس أنجلوس"), "ili los anjlos")
check("nothing undrawable is left in Arabic captions", roman.drawable(roman.to_roman("هذا هو السبب في أنني لم أبث")))
print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
