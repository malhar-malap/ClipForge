"""The profile pages and the admin money view: changing your name, your plan history, and revenue for admins.
Runs the app in-process with its own empty data folder. Nothing outside this machine is contacted."""
import os, sys, tempfile, time
os.environ.update({"PEAKCUT_DATA": tempfile.mkdtemp(prefix="cf-prof-"), "DATABASE_URL": "", "CLIPFORGE_BILLING": "1",
                   "PEAKCUT_ACCOUNTS": "1", "PEAKCUT_VERIFY_EMAIL": "0", "PEAKCUT_PUBLIC_URL": "http://127.0.0.1:8765",
                   "RAZORPAY_KEY_ID": "", "RAZORPAY_KEY_SECRET": "", "PEAKCUT_AI_KEY": "", "PEAKCUT_AI_MODELS": "", "PEAKCUT_SMTP_HOST": ""})
sys.path.insert(0, ".")
from fastapi.testclient import TestClient
from studio import auth, billing, db, server
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
    return c, r.json()["user"]["id"]
anon = TestClient(server.app, base_url=BASE, follow_redirects=False)
a, uid_a = client("pa@clipforge.test")
b, uid_b = client("pb@clipforge.test")

# ---- your name
check("changing a name needs sign-in", anon.put("/api/me", json={"name": "X"}, headers=H).status_code, 401)
r = a.put("/api/me", json={"name": "  Asha    Rao  ", "email": "evil@clipforge.test", "is_admin": True}, headers=H)
check("a name is saved, with the spaces tidied", (r.status_code, r.json()["user"]["name"]), (200, "Asha Rao"))
me = a.get("/api/auth/me").json()["user"]
check("...and nothing else in the body changes", (me["email"], me["is_admin"]), ("pa@clipforge.test", False))
check("an empty name is refused", a.put("/api/me", json={"name": "   "}, headers=H).status_code, 400)
check("a very long name is cut short", len(a.put("/api/me", json={"name": "x" * 500}, headers=H).json()["user"]["name"]), 80)
check("markup in a name is kept as plain text for the page to escape", a.put("/api/me", json={"name": "<b>hi</b>"}, headers=H).json()["user"]["name"], "<b>hi</b>")
check("someone else's name is untouched", b.get("/api/auth/me").json()["user"]["name"], "T")
check("a request from another site is refused", a.put("/api/me", json={"name": "Z"}, headers={"Origin": "https://evil.example"}).status_code, lambda s: s in (403, 400))

# ---- plan history
check("plan history needs sign-in", anon.get("/api/billing/history").status_code, 401)
check("no plans yet: an empty history", a.get("/api/billing/history").json(), {"items": []})
billing.grant(uid_a, "creator", "test")
h = a.get("/api/billing/history").json()["items"]
check("a given plan shows in the history", [(x["plan"], x["label"], x["source"], x["status"]) for x in h], [("creator", "Creator", "grant", "active")])
check("the history leaves out payment references", any("payment_id" in x for x in h), False)
check("...and only the owner sees it", b.get("/api/billing/history").json(), {"items": []})

# ---- revenue on the admin page
check("the admin overview is hidden from normal users", a.get("/api/admin/overview").status_code, 404)
with db.engine.begin() as c:
    c.execute(db.users.update().where(db.users.c.id == uid_b).values(is_admin=True))
    c.execute(billing.payments.insert().values(order_id="order_test_1", user_id=uid_a, plan="creator", amount=47082, status="paid",
                                               payment_id="pay_test_1", created_at=time.time(), paid_at=time.time()))
    c.execute(billing.payments.insert().values(order_id="order_test_2", user_id=uid_a, plan="pro", amount=99999, status="created",
                                               created_at=time.time()))
auth.forget(uid_b)
ov = b.get("/api/admin/overview").json()
rv = ov["revenue"]
check("revenue counts only paid orders", (rv["total"], rv["d30"], rv["payments"]), (47082, 47082, 1))
check("active plans are counted by name", rv["active"], {"Creator": 1})
check("each account shows its plan", {u["email"]: u["plan"] for u in ov["users"]}, {"pa@clipforge.test": "Creator", "pb@clipforge.test": ""})
check("money in shows on today's bar", sum(d["revenue"] for d in ov["daily"]), 47082)

print(f"\n{len(fails)} failed" if fails else "\nALL PASSED")
sys.exit(1 if fails else 0)
