"""Swear words in captions and on-screen text are masked with stars: "fuck" becomes "f***". The first letter
stays so the line still reads naturally. Covers common English swear words and the common Hindi and Urdu ones as
people type them in Roman letters (Hinglish), since captions for those videos are written that way."""
import re

# Whole words, and the roots that start longer words ("fucking", "bullshit" is listed on its own).
_ROOTS = (
    "fuck", "fuk", "fck", "motherfuck", "shit", "bullshit", "bitch", "bastard", "asshole", "dick", "cunt", "pussy",
    "slut", "whore", "wank", "bollock", "twat", "prick", "cock", "nigg", "fag",
    # Hindi / Urdu in Roman letters
    "bhenchod", "behenchod", "bhanchod", "benchod", "bhencho", "behnchod", "madarchod", "maderchod", "madarchoot",
    "chutiya", "chutiye", "chutia", "chootiya", "chod", "chut", "gaand", "gand", "gandu", "lund", "lauda", "lavda",
    "loda", "lode", "jhaat", "jhant", "randi", "harami", "haramzada", "haramkhor", "kutta", "kutti", "kamina",
    "kamine", "bhosdi", "bhosda", "bhosdike", "bsdk", "betichod",
)
_WORDS = {"ass", "arse", "damn", "crap", "mc", "bc", "mkc", "bkl", "tmkc", "wtf", "stfu", "fml", "sala", "saala", "saali"}
_SAFE = {"cocktail", "cockpit", "peacock", "hancock", "dickens", "scunthorpe", "class", "pass", "grass", "assist",
         "assassin", "chodna", "gandhi", "gandhinagar", "pricked", "shitake", "shiitake", "lunda", "kuttappa", "glass",
         "mass", "bass", "brass", "lass", "sass", "chodu", "assume", "assets", "asset", "embassy", "harass"}
_CORE = re.compile(r"^(\W*)([\w']+?)(\W*)$", re.UNICODE)


def is_bad(word: str) -> bool:
    w = re.sub(r"[^a-z]", "", (word or "").lower())
    if not w or w in _SAFE:
        return False
    if w in _WORDS:
        return True
    return any(w.startswith(r) for r in _ROOTS) and not any(w.startswith(s) for s in _SAFE)


def mask_word(word: str) -> str:
    """One word, its punctuation kept: "fucking!" -> "f******!"."""
    m = _CORE.match(word or "")
    if not m or not is_bad(m.group(2)):
        return word
    core = m.group(2)
    return m.group(1) + core[0] + "*" * (len(core) - 1) + m.group(3)


def mask_text(text: str) -> str:
    """Every word in a line of text (a hook, a caption line)."""
    return " ".join(mask_word(w) for w in (text or "").split(" "))


def mask_words(words: list) -> list:
    """Caption words ([{"w", "s", "e"}, ...]) with swear words masked."""
    return [dict(w, w=mask_word(w.get("w", ""))) for w in words]
