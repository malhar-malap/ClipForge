"""AI settings page: Test checks what is on the screen (saved or not), and an empty key box means the saved key.
In-process, with the AI service replaced: nothing outside this machine is contacted."""
import os, sys, tempfile
os.environ.update({"PEAKCUT_DATA": tempfile.mkdtemp(prefix="cf-aiset-"), "DATABASE_URL": "", "PEAKCUT_ACCOUNTS": "0",
                   "PEAKCUT_AI_KEY": "", "PEAKCUT_AI_MODELS": "", "PEAKCUT_PUBLIC_URL": "http://127.0.0.1:8765"})
sys.path.insert(0, ".")
from fastapi.testclient import TestClient
from studio import ai, db, server
db.init()
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)
c = TestClient(server.app, base_url="http://127.0.0.1:8765")
H = {"Origin": "http://127.0.0.1:8765"}
seen = []
ai.call = lambda m, p, s: (seen.append((m, ai.key())), (["ok"], 3, 1))[1]
c.put("/api/ai", json={"provider": "gemini", "models": "model-argon", "key": "AIzaSavedKey1234567890"}, headers=H)
r = c.post("/api/ai/test", json={"provider": "gemini", "models": "model-flash"}, headers=H)
check("Test checks the model on screen, not the saved one", (r.status_code, seen[-1][0]), (200, "model-flash"))
check("...with the saved key when the key box is empty", seen[-1][1], "AIzaSavedKey1234567890")
check("...and nothing is saved by testing", ai.models(), ["model-argon"])
r = c.post("/api/ai/test", json={"provider": "openai", "models": "gpt-x"}, headers=H)
check("another service with an empty key box asks for its key", (r.status_code, "key" in r.json()["detail"].lower()), (400, True))
r = c.post("/api/ai/test", json={"provider": "gemini", "models": "gemini flash 2.8"}, headers=H)
check("a model name with spaces is explained", (r.status_code, "Find models" in r.json()["detail"]), (400, True))
r = c.put("/api/ai", json={"provider": "gemini", "models": "model-flash", "key": None}, headers=H)
check("saving a new model with the key box empty keeps the saved key", (r.json()["has_key"], ai.key()), (True, "AIzaSavedKey1234567890"))
r = c.post("/api/ai/test", headers=H)
check("Test with no form tests what is saved", (r.status_code, seen[-1][0]), (200, "model-flash"))
print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
