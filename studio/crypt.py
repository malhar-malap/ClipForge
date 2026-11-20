"""Secrets kept in the data folder, encrypted: the server's AI key, the tokens of connected YouTube, Instagram and
Instagram accounts, and the platforms' app secrets. Same Fernet key as users' own AI keys (studio/keystore.py, from
CLIPFORGE_SECRET_KEY), so a copy of the data folder alone cannot read any of them.

Values written by older versions in plain text are still read, and are encrypted the next time they are saved."""
import re

PREFIX = "enc:v1:"
SENSITIVE = re.compile(r"(token|secret|webhook|password|^key$)", re.I)


def seal(value):
    if not isinstance(value, str) or not value or value.startswith(PREFIX):
        return value
    from .keystore import _f
    return PREFIX + _f().encrypt(value.encode()).decode()


def unseal(value):
    if not isinstance(value, str) or not value.startswith(PREFIX):
        return value
    from .keystore import _f
    try:
        return _f().decrypt(value[len(PREFIX):].encode()).decode()
    except Exception:  # noqa: BLE001 - the master key changed: the secret has to be entered again
        return ""


def seal_tree(data):
    """A copy of dicts and lists with every sensitive-looking string value encrypted."""
    if isinstance(data, dict):
        return {k: (seal(v) if isinstance(v, str) and SENSITIVE.search(str(k)) else seal_tree(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [seal_tree(v) for v in data]
    return data


def unseal_tree(data):
    if isinstance(data, dict):
        return {k: unseal_tree(v) for k, v in data.items()}
    if isinstance(data, list):
        return [unseal_tree(v) for v in data]
    return unseal(data)


def migrate():
    """At startup: encrypt secrets that older versions saved in plain text (the server AI key, connected-account
    tokens, platform app secrets, alert webhooks). Safe to run every time; files already encrypted are left alone."""
    import json
    from . import config
    paths = [config.DATA_DIR / "ai.json"] + list(config.USERS_DIR.glob("*/accounts.json")) + list(config.USERS_DIR.glob("*/settings.json")) \
        + list(config.DATA_DIR.glob("apps.json"))
    for f in paths:
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            sealed = seal_tree(raw)
            if sealed != raw:
                tmp = f.with_suffix(f.suffix + ".tmp")
                tmp.write_text(json.dumps(sealed, indent=1), encoding="utf-8")
                try:
                    tmp.chmod(0o600)
                except OSError:
                    pass
                tmp.replace(f)
        except (OSError, ValueError):
            continue
