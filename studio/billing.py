"""ClipForge plans: the trial week, Creator, Creator BYOK and Pro; minutes; payments through Razorpay.

Only active when CLIPFORGE_BILLING=1. With it off (a self-hosted copy) every check here says yes.

Rules:
- Previews are free for anyone signed in (a few a day). Rendering a clip in full quality and downloading it needs
  an active plan, and uses the clip's length from the plan's minutes.
- Prices and minutes live only here, on the server. A browser can ask for a plan by name, never set a price.
- A payment counts only after Razorpay's signature on it checks out (the browser's callback or the webhook).
  Activating is idempotent: the same payment can arrive twice and is counted once.
- Creator BYOK waits for a working AI key ("waiting_key") and turns active when the key passes a test call.
- The trial is once per account.
"""
import hashlib
import hmac
import json
import secrets
import threading
import time

import sqlalchemy as sa

from . import config, db

DAY = 86400
# price in paise (Rs 1 = 100 paise, GST included), minutes, days, and whose AI key is used
PLANS = {
    "trial":   {"label": "Trial week",    "price": 4900,  "minutes": 120,  "days": 7,  "ai": "ours", "once": True},
    "creator": {"label": "Creator",       "price": 39900, "minutes": 600,  "days": 30, "ai": "ours"},
    "byok":    {"label": "Creator BYOK",  "price": 19900, "minutes": 600,  "days": 30, "ai": "own"},
    "pro":     {"label": "Pro",           "price": 99900, "minutes": 2000, "days": 30, "ai": "ours"},
}

plans = sa.Table(
    "plans", db.meta,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("user_id", sa.String(40), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    sa.Column("plan", sa.String(16), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),          # active | waiting_key | ended
    sa.Column("starts_at", sa.Float, nullable=False),
    sa.Column("ends_at", sa.Float, nullable=False),
    sa.Column("minutes", sa.Float, nullable=False),
    sa.Column("used", sa.Float, nullable=False, server_default="0"),
    sa.Column("payment_id", sa.String(64), unique=True),         # Razorpay order id, or "grant:..." for an admin grant
    sa.Column("created_at", sa.Float, nullable=False),
)
payments = sa.Table(
    "payments", db.meta,
    sa.Column("order_id", sa.String(64), primary_key=True),      # Razorpay order id
    sa.Column("user_id", sa.String(40), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    sa.Column("plan", sa.String(16), nullable=False),
    sa.Column("amount", sa.Integer, nullable=False),             # paise, from PLANS when the order was made
    sa.Column("status", sa.String(12), nullable=False),          # created | paid
    sa.Column("payment_id", sa.String(64)),                      # Razorpay payment id, once paid
    sa.Column("created_at", sa.Float, nullable=False),
    sa.Column("paid_at", sa.Float),
)
uses = sa.Table(                                                 # minutes taken from a plan: one row per render
    "plan_uses", db.meta,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("plan_id", sa.String(32), nullable=False, index=True),
    sa.Column("user_id", sa.String(40), nullable=False, index=True),
    sa.Column("t", sa.Float, nullable=False),
    sa.Column("minutes", sa.Float, nullable=False),
    sa.Column("what", sa.String(120), nullable=False, server_default=""),
)
previews = sa.Table(                                             # videos previewed without a plan, for the daily limit
    "previews", db.meta,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("user_id", sa.String(40), nullable=False),
    sa.Column("t", sa.Float, nullable=False),
    sa.Index("previews_user_t", "user_id", "t"),
)

_lock = threading.Lock()


class BillingError(ValueError):
    pass


def on() -> bool:
    return config.BILLING


# ---------------------------------------------------------------- reading
def _row(r) -> dict:
    d = dict(r._mapping)
    p = PLANS.get(d["plan"], {})
    d.update(label=p.get("label", d["plan"]), ai=p.get("ai", "ours"),
             left=round(max(0.0, d["minutes"] - d["used"]), 1))
    return d


def current(uid) -> dict:
    """The plan this user can use right now (active or waiting for a key), or None. Ends plans that ran out."""
    now = time.time()
    with db.engine.begin() as c:
        rows = c.execute(sa.select(plans).where(plans.c.user_id == uid, plans.c.status != "ended")
                         .order_by(plans.c.created_at.desc())).fetchall()
        live = None
        for r in rows:
            if r.ends_at <= now:
                c.execute(plans.update().where(plans.c.id == r.id).values(status="ended"))
            elif live is None:
                live = r
    return _row(live) if live else None


def history(uid) -> list:
    with db.engine.connect() as c:
        rows = c.execute(sa.select(plans).where(plans.c.user_id == uid).order_by(plans.c.created_at.desc()).limit(20)).fetchall()
    return [_row(r) for r in rows]


def had_trial(uid) -> bool:
    with db.engine.connect() as c:
        return bool(c.execute(sa.select(plans.c.id).where(plans.c.user_id == uid, plans.c.plan == "trial").limit(1)).first())


def uses_own_key(uid) -> bool:
    p = current(uid) if on() and uid else None
    return bool(p and p["ai"] == "own")


def can_download(uid) -> tuple:
    """(yes or no, why not). Without billing: always yes."""
    if not on():
        return True, ""
    p = current(uid)
    if not p:
        return False, "Choose a plan to download clips. Previews stay free."
    if p["status"] == "waiting_key":
        return False, "Your Creator BYOK plan starts when your AI key passes its test. Add it under Settings, AI."
    if p["left"] <= 0:
        return False, "Your plan has no minutes left. Upgrade or wait for it to renew."
    return True, ""


def is_paid(uid) -> bool:
    """Does this user get the full experience now (all clips, the stronger ranking, full-quality renders)?"""
    return can_download(uid)[0] if on() else True


def summary(uid) -> dict:
    """What the page shows about plans."""
    p = current(uid) if on() else None
    return {"billing": on(), "plan": p and {k: p[k] for k in ("plan", "label", "status", "ends_at", "minutes", "used", "left", "ai")},
            "trial_used": had_trial(uid) if on() else False,
            "plans": [{"id": k, "label": v["label"], "price": v["price"] / 100, "minutes": v["minutes"], "days": v["days"],
                       "own_key": v["ai"] == "own"} for k, v in PLANS.items()],
            "razorpay_key": config.RAZORPAY_KEY_ID if on() else "",
            "previews_left": previews_left(uid) if on() and not p else None, "preview_clips": config.PREVIEW_CLIPS}


# ---------------------------------------------------------------- minutes and previews
def charge(uid, seconds: float, what: str = "") -> None:
    """Take a render's length from the plan. Raises BillingError if the plan cannot cover it."""
    if not on():
        return
    minutes = round(max(0.1, seconds / 60.0), 2)
    with _lock:
        ok, why = can_download(uid)
        if not ok:
            raise BillingError(why)
        p = current(uid)
        if p["left"] + 0.5 < minutes:                    # half a minute of grace, so a clip never fails by seconds
            raise BillingError(f"This clip needs {minutes:g} minutes and your plan has {p['left']:g} left.")
        with db.engine.begin() as c:
            c.execute(plans.update().where(plans.c.id == p["id"]).values(used=plans.c.used + minutes))
            c.execute(uses.insert().values(plan_id=p["id"], user_id=uid, t=time.time(), minutes=minutes, what=what[:120]))


def previews_left(uid) -> int:
    since = time.time() - DAY
    with db.engine.connect() as c:
        n = c.execute(sa.select(sa.func.count()).select_from(previews).where(previews.c.user_id == uid, previews.c.t >= since)).scalar()
    return max(0, config.PREVIEWS_PER_DAY - int(n or 0))


def start_preview(uid) -> None:
    """Count one more preview video for a user without a plan. Raises BillingError past the daily limit."""
    with _lock:
        if previews_left(uid) <= 0:
            raise BillingError(f"You've used today's {config.PREVIEWS_PER_DAY} free previews. Choose a plan, or come back tomorrow.")
        with db.engine.begin() as c:
            c.execute(previews.insert().values(user_id=uid, t=time.time()))


# ---------------------------------------------------------------- starting a plan
def _activate(c, uid, plan, payment_ref) -> str:
    """Start a plan inside an open transaction. The same payment_ref twice starts it once."""
    if c.execute(sa.select(plans.c.id).where(plans.c.payment_id == payment_ref)).first():
        return "already"
    spec = PLANS[plan]
    now = time.time()
    status = "waiting_key" if spec["ai"] == "own" and not _has_working_key(uid) else "active"
    # a new plan replaces the one running now
    c.execute(plans.update().where(plans.c.user_id == uid, plans.c.status != "ended").values(status="ended", ends_at=now))
    c.execute(plans.insert().values(id=secrets.token_hex(8), user_id=uid, plan=plan, status=status, starts_at=now,
                                    ends_at=now + spec["days"] * DAY, minutes=float(spec["minutes"]), used=0.0,
                                    payment_id=payment_ref, created_at=now))
    return status


def grant(uid, plan, note="admin") -> str:
    """Start a plan without a payment (admin grants, beta creators). Returns the plan's status."""
    if plan not in PLANS:
        raise BillingError("Unknown plan.")
    with _lock, db.engine.begin() as c:
        return _activate(c, uid, plan, f"grant:{note}:{secrets.token_hex(6)}")


def _has_working_key(uid) -> bool:
    from . import keystore
    return keystore.has_tested_key(uid)


def key_tested(uid) -> None:
    """The user's own AI key just passed its test: a BYOK plan waiting for it starts now."""
    with db.engine.begin() as c:
        c.execute(plans.update().where(plans.c.user_id == uid, plans.c.status == "waiting_key").values(status="active"))


def key_removed(uid) -> None:
    """The user's own key is gone: a running BYOK plan pauses until a new key passes its test."""
    with db.engine.begin() as c:
        ids = [r.id for r in c.execute(sa.select(plans).where(plans.c.user_id == uid, plans.c.status == "active")).fetchall()
               if PLANS.get(r.plan, {}).get("ai") == "own"]
        if ids:
            c.execute(plans.update().where(plans.c.id.in_(ids)).values(status="waiting_key"))


# ---------------------------------------------------------------- Razorpay
def _rzp_auth():
    if not (config.RAZORPAY_KEY_ID and config.razorpay_secret()):
        raise BillingError("Payments are not set up on this server yet.")
    return config.RAZORPAY_KEY_ID, config.razorpay_secret()


def create_order(uid, plan) -> dict:
    """A Razorpay order for a plan, at the price set here. Returns what the checkout on the page needs."""
    if not on():
        raise BillingError("Plans are not used on this server.")
    if plan not in PLANS:
        raise BillingError("Choose one of the plans.")
    if PLANS[plan].get("once") and had_trial(uid):
        raise BillingError("The trial week is once per account. Choose Creator or Pro.")
    import httpx
    amount = PLANS[plan]["price"]
    r = httpx.post("https://api.razorpay.com/v1/orders", auth=_rzp_auth(), timeout=20,
                   json={"amount": amount, "currency": "INR", "receipt": f"cf_{secrets.token_hex(6)}",
                         "notes": {"plan": plan, "user": uid}})
    if r.status_code != 200:
        raise BillingError("The payment service did not answer. Try again in a moment.")
    order = r.json()
    if int(order.get("amount", 0)) != amount:
        raise BillingError("The payment service returned a different amount.")
    with db.engine.begin() as c:
        c.execute(payments.insert().values(order_id=order["id"], user_id=uid, plan=plan, amount=amount, status="created",
                                           created_at=time.time()))
    return {"order_id": order["id"], "amount": amount, "currency": "INR", "key": config.RAZORPAY_KEY_ID,
            "plan": plan, "label": PLANS[plan]["label"]}


def _paid(order_id, payment_id, amount=None, uid=None) -> str:
    """Mark an order paid and start its plan, once. `uid` given: the order must be that user's."""
    with _lock, db.engine.begin() as c:
        row = c.execute(sa.select(payments).where(payments.c.order_id == order_id)).first()
        if not row:
            raise BillingError("Unknown order.")
        if uid is not None and row.user_id != uid:
            raise BillingError("Unknown order.")
        if amount is not None and int(amount) != int(row.amount):
            raise BillingError("The amount paid does not match the plan.")
        if row.status != "paid":
            c.execute(payments.update().where(payments.c.order_id == order_id)
                      .values(status="paid", payment_id=str(payment_id)[:64], paid_at=time.time()))
        status = _activate(c, row.user_id, row.plan, order_id)
    if status != "already":
        _receipt(row.user_id, row.plan, row.amount, order_id)
    return status


def _receipt(uid, plan, amount_paise, order_id):
    """Email the receipt for a paid plan. A mail problem never undoes or delays the plan itself."""
    try:
        from . import mailer
        with db.engine.connect() as c:
            email = c.execute(sa.select(db.users.c.email).where(db.users.c.id == uid)).scalar()
        p = current(uid)
        if email and p:
            spec = PLANS[plan]
            mailer.deliver(email, mailer.m_receipt(spec["label"], amount_paise / 100, spec["minutes"],
                                                   time.strftime("%d %b %Y", time.gmtime(p["ends_at"])), order_id))
    except Exception:  # noqa: BLE001
        pass


def verify_checkout(uid, order_id: str, payment_id: str, signature: str) -> str:
    """The checkout on the page says it paid: believe it only if Razorpay's signature matches."""
    _, secret = _rzp_auth()
    want = hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want, str(signature or "")):
        raise BillingError("That payment could not be verified.")
    return _paid(str(order_id), str(payment_id), uid=uid)


def webhook(body: bytes, signature: str) -> str:
    """Razorpay's server telling ours a payment went through (covers a closed tab after paying)."""
    secret = config.razorpay_webhook_secret()
    if not secret:
        raise BillingError("Webhook not set up.")
    want = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want, str(signature or "")):
        raise BillingError("Bad signature.")
    event = json.loads(body.decode("utf-8"))
    if event.get("event") not in ("payment.captured", "order.paid"):
        return "ignored"
    pay = ((event.get("payload") or {}).get("payment") or {}).get("entity") or {}
    order_id = pay.get("order_id") or (((event.get("payload") or {}).get("order") or {}).get("entity") or {}).get("id")
    if not order_id:
        return "ignored"
    return _paid(order_id, pay.get("id") or "", amount=pay.get("amount"))
