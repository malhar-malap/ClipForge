"""Secrets in the data folder are encrypted: the server AI key, connected-account tokens and platform app secrets.
Older plain-text files are still read and are encrypted at startup. In-process, nothing outside is contacted."""
import json, os, sys, tempfile
os.environ.update({"PEAKCUT_DATA": tempfile.mkdtemp(prefix="cf-rest-"), "DATABASE_URL": "", "PEAKCUT_AI_KEY": "", "PEAKCUT_AI_MODELS": ""})
os.environ.pop("CLIPFORGE_SECRET_KEY", None)
sys.path.insert(0, ".")
from studio import ai, config, crypt, ctx, accounts
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)
ai.save("gemini", "model-a", "", "AIzaTopSecretServerKey123456")
raw = (config.DATA_DIR / "ai.json").read_text()
check("the server AI key is not stored as typed", "TopSecret" not in raw and crypt.PREFIX in raw)
check("...and still works", ai.key(), "AIzaTopSecretServerKey123456")
(config.DATA_DIR / "ai.json").write_text(json.dumps({"provider": "gemini", "models": ["m"], "base_url": "", "key": "AIzaOldPlainKey123456"}))
ai._saved["at"] = None
check("an older plain-text key is still read", ai.key(), "AIzaOldPlainKey123456")
crypt.migrate()
check("startup encrypts it", "AIzaOldPlainKey" not in (config.DATA_DIR / "ai.json").read_text())
ai._saved["at"] = None
check("...and it still works after", ai.key(), "AIzaOldPlainKey123456")
uid = "user_rest01"
with ctx.as_user(uid):
    accounts._write("accounts.json", [{"id": "a1", "platform": "youtube", "name": "Me", "refresh_token": "1//RefreshTokenSecret", "access_token": "ya29.AccessSecret", "added": 1}])
    on_disk = (accounts._dir() / "accounts.json").read_text()
    check("account tokens are not stored as given", "RefreshTokenSecret" not in on_disk and "AccessSecret" not in on_disk)
    check("...names and other fields stay readable", '"name": "Me"' in on_disk)
    check("...and the app still reads the tokens", accounts._read("accounts.json", [])[0]["refresh_token"], "1//RefreshTokenSecret")
check("non-secret fields are never encrypted", crypt.seal_tree({"name": "x", "models": ["a"], "id": "y"}), {"name": "x", "models": ["a"], "id": "y"})
print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
