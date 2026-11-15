"""Users' own AI keys (Creator BYOK), encrypted in the database.

- Each key is encrypted with Fernet (AES + an integrity check) under the server's master key
  (CLIPFORGE_SECRET_KEY). Without that setting a master key is made once and kept in the data folder's
  secrets/ folder, readable only by the app: fine on one machine, but a server should set it in its environment so
  a copy of the data folder alone cannot read the keys.
- A key is only decrypted on the server, for a call to the AI service the user chose. It is never sent back to the
  page (only its last four characters), never logged, and never written anywhere else.
- Only known AI services are allowed here: their addresses are fixed, so a user cannot point the server at an
  address of their choosing (no "custom" or "ollama" for users).
"""
import os
import threading
import time

import sqlalchemy as sa

from . import config, db

USER_PROVIDERS = ("anthropic", "openai", "gemini", "openrouter", "groq", "xai")

user_ai = sa.Table(
    "user_ai", db.meta,
    sa.Column("user_id", sa.String(40), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("provider", sa.String(20), nullable=False),
    sa.Column("models", sa.String(400), nullable=False),          # comma separated, tried in order
    sa.Column("key_enc", sa.Text, nullable=False),                # Fernet token
    sa.Column("hint", sa.String(8), nullable=False, server_default=""),
    sa.Column("tested_at", sa.Float),                             # set when a test call with it worked
    sa.Column("updated_at", sa.Float, nullable=False),
)

_lock = threading.Lock()
_fernet = None
_cache: dict = {}            # user id -> (when read, settings dict or None)
CACHE_SECONDS = 30


def _master() -> bytes:
    k = config.master_key()
    if k:
        return k.encode()
    from cryptography.fernet import Fernet
    folder = config.DATA_DIR / "secrets"
    f = folder / "master.key"
    with _lock:
        if not f.exists():
            folder.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_bytes(Fernet.generate_key())
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            tmp.replace(f)
    return f.read_bytes().strip()


def _f():
    global _fernet
    if _fernet is None:
        from cryptography.fernet import Fernet
        _fernet = Fernet(_master())
    return _fernet


def _forget(uid):
    _cache.pop(uid, None)


def get(uid) -> dict:
    """The user's own AI settings, decrypted, or None. Kept in memory for a few seconds."""
    hit = _cache.get(uid)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    with db.engine.connect() as c:
        r = c.execute(sa.select(user_ai).where(user_ai.c.user_id == uid)).first()
    out = None
    if r:
        try:
            key = _f().decrypt(r.key_enc.encode()).decode()
        except Exception:  # noqa: BLE001 - the master key changed: the user has to paste the key again
            key = ""
        out = {"provider": r.provider, "models": [m for m in r.models.split(",") if m], "base_url": "", "key": key,
               "hint": r.hint, "tested_at": r.tested_at}
    _cache[uid] = (time.time(), out)
    return out


def public(uid) -> dict:
    s = get(uid)
    return {"providers": list(USER_PROVIDERS), "saved": bool(s), "provider": s and s["provider"],
            "models": s["models"] if s else [], "key_hint": s["hint"] if s else "", "tested": bool(s and s["tested_at"])}


def has_tested_key(uid) -> bool:
    s = get(uid)
    return bool(s and s["key"] and s["tested_at"])


def clean(provider: str, models, key: str) -> tuple:
    """(provider, models, key) checked and tidied, or ValueError saying what is wrong."""
    import re
    p = str(provider or "").strip().lower()
    if p not in USER_PROVIDERS:
        raise ValueError("Choose one of the AI services in the list.")
    if isinstance(models, str):
        models = models.split(",")
    ms = [str(m).strip()[:120] for m in (models or []) if str(m).strip()][:3]
    if not ms or any(not re.fullmatch(r"[\w.\-:/@]+", m) for m in ms):
        raise ValueError("Enter the model id exactly as the service names it.")
    key = str(key or "").strip()
    if not 12 <= len(key) <= 400 or any(ch.isspace() for ch in key):
        raise ValueError("That doesn't look like an API key.")
    return p, ms, key


def save(uid, provider: str, models, key: str, tested: bool) -> None:
    p, ms, key = clean(provider, models, key)
    now = time.time()
    row = {"provider": p, "models": ",".join(ms), "key_enc": _f().encrypt(key.encode()).decode(), "hint": key[-4:],
           "tested_at": now if tested else None, "updated_at": now}
    with db.engine.begin() as c:
        if c.execute(sa.select(user_ai.c.user_id).where(user_ai.c.user_id == uid)).first():
            c.execute(user_ai.update().where(user_ai.c.user_id == uid).values(**row))
        else:
            c.execute(user_ai.insert().values(user_id=uid, **row))
    _forget(uid)


def remove(uid) -> None:
    with db.engine.begin() as c:
        c.execute(user_ai.delete().where(user_ai.c.user_id == uid))
    _forget(uid)
