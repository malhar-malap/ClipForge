"""Swear words in captions and hooks are masked with stars, English and Hinglish, without catching normal words."""
import sys
sys.path.insert(0, ".")
from studio import profanity
fails = []
def check(n, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

check("an English swear word keeps its first letter", profanity.mask_word("fuck"), "f***")
check("...longer forms and punctuation too", profanity.mask_word("Fucking!"), "F******!")
check("Hinglish swear words are masked", [profanity.mask_word(w) for w in ("bhenchod", "chutiya", "bsdk")], ["b*******", "c******", "b***"])
check("normal words are left alone", [profanity.mask_word(w) for w in ("class", "assist", "cocktail", "Gandhi", "glass", "assume")],
      ["class", "assist", "cocktail", "Gandhi", "glass", "assume"])
check("a hook line is masked word by word", profanity.mask_text("WHAT THE FUCK BRO"), "WHAT THE F*** BRO")
check("caption words keep their timings", profanity.mask_words([{"w": "shit", "s": 1.0, "e": 1.4}]), [{"w": "s***", "s": 1.0, "e": 1.4}])
print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
