"""ClipForge plans over HTTP: who can reach the billing, key and preview routes, and what a forged request gets.
Runs the app in-process with its own empty data folder. Nothing outside this machine is contacted."""
import hashlib, hmac, json, os, shutil, sys, tempfile, time
os.environ.update({"PEAKCUT_DATA": tempfile.mkdtemp(prefix="cf-bhttp-"), "DATABASE_URL": "", "CLIPFORGE_BILLING": "1",
                   "PEAKCUT_ACCOUNTS": "1", "PEAKCUT_VERIFY_EMAIL": "0", "PEAKCUT_PUBLIC_URL": "http://127.0.0.1:8765",
                   "RAZORPAY_KEY_ID": "", "RAZORPAY_KEY_SECRET": "", "RAZORPAY_WEBHOOK_SECRET": "test-webhook-secret-789",
                   "PEAKCUT_AI_KEY": "", "PEAKCUT_AI_MODELS": "", "PEAKCUT_SMTP_HOST": ""})
sys.path.insert(0, ".")
from fastapi.testclient import TestClient
from studio import billing, ctx, db, jobs, server
db.init()
fails = []
BASE = "http://127.0.0.1:8765"
H = {"Origin": BASE}
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

def client(email):
    c = TestClient(server.app, base_url=BASE, follow_redirects=False)
    r = c.post("/api/auth/signup", json={"name": "T", "email": email, "password": "local-test-pass-" + email[:3] + "-x9"}, headers=H)
    assert r.status_code == 200, r.text
    return c
anon = TestClient(server.app, base_url=BASE, follow_redirects=False)
a, b = client("ha@clipforge.test"), client("hb@clipforge.test")
uid_a = a.get("/api/status").json()["user"]["id"]

# ---- signed out
for path in ("/api/billing", "/api/me/ai"):
    check(f"{path} needs sign-in", anon.get(path).status_code, 401)
check("checkout needs sign-in", anon.post("/api/billing/checkout", json={"plan": "creator"}, headers=H).status_code, 401)

# ---- signed in, no plan
s = a.get("/api/billing").json()
check("the page learns there is no plan and 2 previews left", (s["billing"], s["plan"], s["previews_left"]), (True, None, 2))
check("prices come from the server", [p["price"] for p in s["plans"]], [49.0, 399.0, 999.0, 199.0, 499.0])
for path, words in (("/terms", "Your provider charges you directly"), ("/refunds", "Within 7 days of paying"), ("/privacy", "Digital Personal Data Protection Act"),
                    ("/contact", "Grievance officer"), ("/acceptable-use", "Acceptable Use Policy")):
    r = anon.get(path)
    check(f"{path} is public and says what it should", (r.status_code, words in r.text), (200, True))
home = anon.get("/").text
check("the front page shows today's plans, built from the plan list", all(x in home for x in ("Pro BYOK", "₹499", "1,000 clips a month", "400 clips a month", "+ GST")), True)
check("...and nothing from the old plans", any(x in home for x in ("minutes a month", "{{PRICING}}", "Priority in the queue")), False)
check("the terms list every plan with its price", all(x in anon.get("/terms").text for x in ("Pro BYOK", "₹499", "1,000 clips", "Creator BYOK")), True)
check("the BYOK plans are marked as running on the user's own key", [p["id"] for p in s["plans"] if p["own_key"]], ["byok", "byok_pro"])
check("checkout without payments set up is refused cleanly", a.post("/api/billing/checkout", json={"plan": "creator"}, headers=H).status_code, 400)
check("a made-up plan is refused", a.post("/api/billing/checkout", json={"plan": "free-forever"}, headers=H).status_code, 400)
check("a checkout from another website is refused", a.post("/api/billing/checkout", json={"plan": "creator"}, headers={"Origin": "https://evil.example"}).status_code, 403)
check("verifying a payment that was never made is refused", a.post("/api/billing/verify", json={"razorpay_order_id": "order_x", "razorpay_payment_id": "pay_x", "razorpay_signature": "0" * 64}, headers=H).status_code, 400)

# ---- the webhook: open to Razorpay, but only with its signature
check("a webhook without a signature is refused", anon.post("/api/billing/webhook", content=b'{"event":"payment.captured"}').status_code, 400)
check("a webhook with a wrong signature is refused", anon.post("/api/billing/webhook", content=b'{"event":"payment.captured"}', headers={"X-Razorpay-Signature": "ab" * 32}).status_code, 400)
with db.engine.begin() as cn:
    cn.execute(billing.payments.insert().values(order_id="order_H1", user_id=uid_a, plan="creator", amount=39900, status="created", created_at=time.time()))
body = json.dumps({"event": "order.paid", "payload": {"payment": {"entity": {"id": "pay_H1", "order_id": "order_H1", "amount": 39900}}}}).encode()
sig = hmac.new(b"test-webhook-secret-789", body, hashlib.sha256).hexdigest()
check("a signed webhook is accepted", anon.post("/api/billing/webhook", content=body, headers={"X-Razorpay-Signature": sig}).status_code, 200)
check("...and the paying user now has Creator", a.get("/api/billing").json()["plan"]["plan"], "creator")
check("...but the other user does not", b.get("/api/billing").json()["plan"], None)

# ---- previews belong to their owner
with ctx.as_user(uid_a):
    job = jobs.create({"type": "file", "path": "", "name": "x.mp4"}, {}, enqueue=False)
src = jobs.job_dir(job["id"]) / "source.mp4"
src.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
job.update(source_path=str(src), status="done", width=1920, height=1080, duration=30,
           clips=[{"id": "clip01", "start": 1, "end": 20, "status": "preview", "score": 80},
                  {"id": "clip02", "start": 5, "end": 25, "status": "locked", "score": 60}])
check("the owner can play a preview", a.get(f"/api/jobs/{job['id']}/clips/clip01/preview").status_code, 200)
check("another user cannot", b.get(f"/api/jobs/{job['id']}/clips/clip01/preview").status_code, 404)
check("nobody signed out can", anon.get(f"/api/jobs/{job['id']}/clips/clip01/preview").status_code, 401)
check("a locked clip has no preview to play", a.get(f"/api/jobs/{job['id']}/clips/clip02/preview").status_code, 404)
check("another user cannot unlock someone's clip", b.post(f"/api/jobs/{job['id']}/clips/clip02/unlock", headers=H).status_code, 404)
uid_b = b.get("/api/status").json()["user"]["id"]
with ctx.as_user(uid_b):
    jb = jobs.create({"type": "file", "path": "", "name": "y.mp4"}, {}, enqueue=False)
jb.update(status="done", clips=[{"id": "clip01", "start": 1, "end": 20, "status": "locked", "score": 70}])
r = b.post(f"/api/jobs/{jb['id']}/clips/clip01/unlock", headers=H)
check("a user without a plan is asked to choose one before a clip is made", (r.status_code, "plan" in r.json()["detail"].lower()), (402, True))

# ---- own AI key
check("a key for an address of the user's choosing is refused", a.put("/api/me/ai", json={"provider": "custom", "models": "m", "key": "k" * 20}, headers=H).status_code, 400)
check("a key that is too short is refused before anything is sent", a.put("/api/me/ai", json={"provider": "anthropic", "models": "claude-haiku-5-5", "key": "short"}, headers=H).status_code, 400)
check("the key settings never include a key", "key\"" not in json.dumps(a.get("/api/me/ai").json()).replace("key_hint", ""))

print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
