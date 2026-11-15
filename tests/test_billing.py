"""ClipForge plans: previews without a plan, the paywall, minutes, the trial, Creator BYOK and payment signatures.
Runs against the code directly with its own empty data folder and SQLite file. Nothing outside this machine is
contacted: Razorpay is never called (signatures are checked with made-up test secrets)."""
import hashlib, hmac, json, os, sys, tempfile, time
os.environ.update({"PEAKCUT_DATA": tempfile.mkdtemp(prefix="cf-billing-"), "DATABASE_URL": "", "CLIPFORGE_BILLING": "1",
                   "PEAKCUT_ACCOUNTS": "1", "RAZORPAY_KEY_ID": "rzp_test_localonly", "RAZORPAY_KEY_SECRET": "test-secret-not-real-123",
                   "RAZORPAY_WEBHOOK_SECRET": "test-webhook-secret-456", "CLIPFORGE_PREVIEWS_PER_DAY": "2"})
os.environ.pop("CLIPFORGE_SECRET_KEY", None)
sys.path.insert(0, ".")
import sqlalchemy as sa
from studio import ai, billing, ctx, db, jobs, keystore
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)
def raises(fn, exc=Exception):
    try:
        fn()
    except exc as e:
        return str(e) or True
    return False

db.init()
def user(email):
    uid = "u" + hashlib.sha1(email.encode()).hexdigest()[:12]
    with db.engine.begin() as c:
        c.execute(db.users.insert().values(id=uid, email=email, name="", created_at=time.time()))
    return uid
a, b, k = user("a@test.local"), user("b@test.local"), user("k@test.local")

# ---- no plan: previews only
check("without a plan nothing can be downloaded", billing.can_download(a)[0], False)
check("...and the page is told why", "plan" in billing.can_download(a)[1].lower())
with ctx.as_user(a):
    j1 = jobs.create({"type": "url", "url": "https://youtu.be/x", "name": "x"}, {}, enqueue=False)
check("a video sent without a plan becomes a preview", j1.get("preview"), True)
check("...fetched small (360p), since previews are not rendered", j1["options"]["quality"], 360)
with ctx.as_user(a):
    jobs.create({"type": "url", "url": "https://youtu.be/y", "name": "y"}, {}, enqueue=False)
    third = raises(lambda: jobs.create({"type": "url", "url": "https://youtu.be/z", "name": "z"}, {}, enqueue=False), billing.BillingError)
check("the third preview in a day is refused", bool(third))
with ctx.as_user(a):
    check("live recording needs a plan", bool(raises(lambda: jobs.create({"type": "live", "url": "https://twitch.tv/x", "name": "x"}, {}, enqueue=False, kind="live"), billing.BillingError)))
j1["clips"] = [{"id": "clip01", "start": 10, "end": 40, "status": "preview"}]
with ctx.as_user(a):
    check("a preview clip cannot be unlocked without a plan", bool(raises(lambda: jobs.request_unlock(j1["id"], "clip01"), ValueError)))

# ---- a plan
check("an unknown plan cannot be granted", bool(raises(lambda: billing.grant(a, "gold"), billing.BillingError)))
check("granting Creator starts it", billing.grant(a, "creator", "test"), "active")
check("now clips can be downloaded", billing.can_download(a)[0], True)
check("Creator has 600 minutes", billing.current(a)["minutes"], 600.0)
billing.charge(a, 90, "a 90 second clip")
check("a 90 second render uses 1.5 minutes", billing.current(a)["left"], 598.5)
with db.engine.begin() as c:
    c.execute(billing.plans.update().where(billing.plans.c.user_id == a).values(used=599.9))
check("a render bigger than what is left is refused", bool(raises(lambda: billing.charge(a, 600, "long"), billing.BillingError)))
with db.engine.begin() as c:
    c.execute(billing.plans.update().where(billing.plans.c.user_id == a).values(ends_at=time.time() - 1))
check("a plan past its end date stops", billing.current(a), None)
check("one user's plan is not another's", billing.can_download(b)[0], False)

# ---- the trial
billing.grant(b, "trial", "test")
check("the trial is once per account", bool(raises(lambda: billing.create_order(b, "trial"), billing.BillingError)))
check("the trial gives 120 minutes for 7 days", (billing.current(b)["minutes"], round((billing.current(b)["ends_at"] - time.time()) / 86400)), (120.0, 7))

# ---- Creator BYOK
check("BYOK waits for a tested key", billing.grant(k, "byok", "test"), "waiting_key")
check("...and cannot download yet", billing.can_download(k)[0], False)
check("only known AI services are allowed for a user's key", bool(raises(lambda: keystore.clean("custom", ["m"], "x" * 20), ValueError)))
check("a key with spaces is refused", bool(raises(lambda: keystore.clean("anthropic", ["claude-haiku-5-5"], "abc def ghi jkl mno"), ValueError)))
keystore.save(k, "anthropic", ["claude-haiku-5-5"], "sk-test-not-a-real-key-0001", tested=True)
billing.key_tested(k)
check("a tested key starts the BYOK plan", billing.current(k)["status"], "active")
with db.engine.connect() as c:
    stored = c.execute(sa.select(keystore.user_ai.c.key_enc)).scalar()
check("the key is stored encrypted, not as typed", "sk-test-not-a-real-key" not in stored and len(stored) > 40)
check("the page only ever sees the last four characters", (keystore.public(k)["key_hint"], "sk-test" in json.dumps(keystore.public(k))), ("0001", False))
with ctx.as_user(k):
    ai.forget_own(k)
    check("AI calls for a BYOK user run on their own key", (ai.current()["provider"], ai.key()), ("anthropic", "sk-test-not-a-real-key-0001"))
with ctx.as_user(b):
    check("...and never on another user's", ai.key() != "sk-test-not-a-real-key-0001")
keystore.remove(k)
billing.key_removed(k)
check("removing the key pauses the BYOK plan", billing.current(k)["status"], "waiting_key")
with ctx.as_user(k):
    ai.forget_own(k)
    check("...and nothing runs on the server's key meanwhile", (ai.ready(), ai.key()), (False, ""))

# ---- payments: only Razorpay's signature counts, once
with db.engine.begin() as c:
    c.execute(billing.payments.insert().values(order_id="order_T1", user_id=b, plan="pro", amount=99900, status="created", created_at=time.time()))
sig = hmac.new(b"test-secret-not-real-123", b"order_T1|pay_T1", hashlib.sha256).hexdigest()
check("a wrong signature is refused", bool(raises(lambda: billing.verify_checkout(b, "order_T1", "pay_T1", "0" * 64), billing.BillingError)))
check("another user cannot claim the payment", bool(raises(lambda: billing.verify_checkout(a, "order_T1", "pay_T1", sig), billing.BillingError)))
check("a correct signature starts the plan", billing.verify_checkout(b, "order_T1", "pay_T1", sig), "active")
check("the plan is the one that was ordered, at the server's price", billing.current(b)["plan"], "pro")
check("the same payment twice is counted once", billing.verify_checkout(b, "order_T1", "pay_T1", sig), "already")

with db.engine.begin() as c:
    c.execute(billing.payments.insert().values(order_id="order_T2", user_id=a, plan="creator", amount=39900, status="created", created_at=time.time()))
def hook(payload):
    body = json.dumps(payload).encode()
    return body, hmac.new(b"test-webhook-secret-456", body, hashlib.sha256).hexdigest()
body, s2 = hook({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_T2", "order_id": "order_T2", "amount": 100}}}})
check("a webhook with a different amount is refused", bool(raises(lambda: billing.webhook(body, s2), billing.BillingError)))
body, s2 = hook({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_T2", "order_id": "order_T2", "amount": 39900}}}})
check("a webhook with a bad signature is refused", bool(raises(lambda: billing.webhook(body, "f" * 64), billing.BillingError)))
check("a signed webhook starts the plan", billing.webhook(body, s2), "active")
check("...and the same webhook again does nothing new", billing.webhook(body, s2), "already")
check("other events are ignored", billing.webhook(*hook({"event": "payment.failed", "payload": {}})), "ignored")

print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
