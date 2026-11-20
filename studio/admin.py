"""Everything only an admin may do: the numbers on /admin, and switching accounts off.

Who is an admin is the `is_admin` value on their row in the users table and nothing else. No web request can
change it, and no email address is special in the code. It is set by hand, on the server:

    python -m studio.admin list
    python -m studio.admin grant someone@example.com
    python -m studio.admin revoke someone@example.com
    python -m studio.admin plan someone@example.com creator     (trial, creator, pro, byok, byok_pro: no payment needed)

Admins see accounts and AI use. They do not see anyone's videos, clips or connected accounts."""
import shutil
import sys
import time
from collections import defaultdict

import sqlalchemy as sa

from . import config, db

class Refused(ValueError):
    """Something an admin asked for that is not allowed. `status` is the HTTP status to answer with."""
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


def _day(t):
    return time.strftime("%Y-%m-%d", time.localtime(t))


def _log(c, admin_id: str, action: str, target_id: str = None, detail: str = ""):
    c.execute(db.admin_log.insert().values(t=time.time(), admin_id=admin_id, action=action[:30], target_id=target_id,
                                           detail=detail[:300]))


# ---------------------------------------------------------------- the dashboard
def overview() -> dict:
    from . import ai, auth, jobs, live, load, mailer, transcribe
    now = time.time()
    midnight = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1))
    d7, d30 = now - 7 * 86400, now - 30 * 86400
    u, g = db.users.c, db.usage.c
    tok = g.tokens_in + g.tokens_out
    with db.engine.connect() as c:
        rows = c.execute(sa.select(db.users).order_by(u.created_at.desc()).limit(2000)).all()
        n_users = c.execute(sa.select(sa.func.count()).select_from(db.users)).scalar()
        verified = {r[0] for r in c.execute(sa.select(db.email_ok.c.user_id))}
        used = {r[0]: (r[1], int(r[2] or 0)) for r in c.execute(sa.select(g.user_id, sa.func.count(), sa.func.sum(tok)).group_by(g.user_id))}
        calls_today = c.execute(sa.select(sa.func.count()).select_from(db.usage).where(g.t >= midnight)).scalar()

        days = [_day(now - 86400 * i) for i in range(29, -1, -1)]
        daily = {d: {"day": d, "signups": 0, "tokens": 0, "calls": 0, "revenue": 0} for d in days}
        for (created,) in c.execute(sa.select(u.created_at).where(u.created_at >= now - 31 * 86400)):
            if _day(created) in daily:
                daily[_day(created)]["signups"] += 1
        for r in c.execute(sa.select(g.t, g.tokens_in, g.tokens_out).where(g.t >= now - 31 * 86400)):
            if _day(r[0]) in daily:
                x = daily[_day(r[0])]
                x["tokens"] += int(r[1]) + int(r[2]); x["calls"] += 1          # noqa: E702
        by_purpose = [[r[0], r[1], int(r[2] or 0)] for r in c.execute(
            sa.select(g.purpose, sa.func.count(), sa.func.sum(tok)).group_by(g.purpose).order_by(sa.func.sum(tok).desc()).limit(12))]
        emails = {r.id: r.email for r in rows}
        log = [{"t": r._mapping["t"], "admin": emails.get(r.admin_id, ""), "action": r.action, "target": emails.get(r.target_id, ""),
                "detail": r.detail} for r in c.execute(sa.select(db.admin_log).order_by(db.admin_log.c.t.desc()).limit(40))]

    revenue, on_plan = _money(now, daily)
    all_jobs = jobs.all_jobs()
    vids, clips = defaultdict(int), defaultdict(int)
    for j in all_jobs:
        vids[j["user"]] += 1
        clips[j["user"]] += sum(1 for k in j["clips"] if k.get("status") == "done")
    verify_on = config.VERIFY_EMAIL
    users = [{"id": r.id, "email": r.email, "name": r.name, "role": "admin" if r.is_admin else "user", "disabled": bool(r.disabled),
              "verified": (not verify_on) or r.id in verified, "google": bool(r.google_sub),
              "created_at": r.created_at, "last_seen": r.last_seen,
              "ai_calls": used.get(r.id, (0, 0))[0], "tokens": used.get(r.id, (0, 0))[1],
              "videos": vids[r.id], "clips": clips[r.id], "plan": on_plan.get(r.id, "")} for r in rows]
    return {
        "totals": {"users": int(n_users), "verified": sum(1 for x in users if x["verified"]),
                   "disabled": sum(1 for x in users if x["disabled"]), "admins": sum(1 for x in users if x["role"] == "admin"),
                   "signups_today": sum(1 for x in users if x["created_at"] >= midnight),
                   "signups_7d": sum(1 for x in users if x["created_at"] >= d7),
                   "signups_30d": sum(1 for x in users if x["created_at"] >= d30),
                   "active_7d": sum(1 for x in users if (x["last_seen"] or 0) >= d7),
                   "ai_calls": sum(v[0] for v in used.values()), "ai_calls_today": int(calls_today),
                   "tokens": sum(v[1] for v in used.values()),
                   "videos": len(all_jobs), "clips": sum(clips.values()), "recording": len(live.active()),
                   "working": sum(1 for j in all_jobs if j["status"] in ("queued", "running"))},
        "daily": list(daily.values()), "by_purpose": by_purpose, "users": users, "log": log, "revenue": revenue,
        "server": {"speech_model": transcribe.model_ready(), "ai_key": ai.ready(), "ai_provider": ai.label(),
                   "ai_model": (ai.models() or [""])[0], "google": auth.google_ready(), "mail": mailer.ready(),
                   "free_gb": round(shutil.disk_usage(config.DATA_DIR).free / 1e9, 1),
                   "disk_total_gb": round(shutil.disk_usage(config.DATA_DIR).total / 1e9, 1), "ram_total_gb": round(load.ram_total_gb(), 1),
                   "load": load.state(), "running": jobs.running_now(), "waiting": jobs.waiting_total(),
                   "database": config.DATABASE_URL.split(":", 1)[0].split("+")[0]}}


def _money(now: float, daily: dict):
    """Paid plans: money in (in paise) overall, in 30 days and per day, and which plan each person is on.
    Nothing when payments are switched off."""
    from . import billing
    if not billing.on():
        return None, {}
    p, pl = billing.payments.c, billing.plans.c
    with db.engine.connect() as c:
        paid = c.execute(sa.select(p.amount, p.paid_at).where(p.status == "paid")).all()
        live = c.execute(sa.select(pl.user_id, pl.plan).where(pl.status == "active", pl.ends_at > now)
                         .order_by(pl.created_at)).all()
    for amount, t in paid:
        if t and _day(t) in daily:
            daily[_day(t)]["revenue"] += int(amount)
    on_plan = {uid: plan for uid, plan in live}
    counts = defaultdict(int)
    for plan in on_plan.values():
        counts[billing.PLANS.get(plan, {}).get("label", plan)] += 1
    return {"total": sum(int(a) for a, _ in paid), "d30": sum(int(a) for a, t in paid if t and t >= now - 30 * 86400),
            "payments": len(paid), "active": dict(counts)}, {u: billing.PLANS.get(x, {}).get("label", x) for u, x in on_plan.items()}


def user_detail(uid: str) -> dict:
    """One account's AI use. Not their videos, clips or connected accounts."""
    g = db.usage.c
    tok = g.tokens_in + g.tokens_out
    with db.engine.connect() as c:
        r = c.execute(sa.select(db.users).where(db.users.c.id == uid)).first()
        if not r:
            raise Refused("No such account", 404)
        recent = [{"t": x._mapping["t"], "tokens": int(x.tokens_in) + int(x.tokens_out), "purpose": x.purpose}
                  for x in c.execute(sa.select(db.usage).where(g.user_id == uid).order_by(g.t.desc()).limit(40))]
        by_purpose = [[x[0], int(x[1] or 0), x[2]] for x in c.execute(
            sa.select(g.purpose, sa.func.sum(tok), sa.func.count()).where(g.user_id == uid)
            .group_by(g.purpose).order_by(sa.func.sum(tok).desc()))]
        devices = c.execute(sa.select(sa.func.count()).select_from(db.sessions).where(
            db.sessions.c.user_id == uid, db.sessions.c.expires_at > time.time())).scalar()
    return {"id": r.id, "email": r.email, "name": r.name, "role": "admin" if r.is_admin else "user", "disabled": bool(r.disabled),
            "created_at": r.created_at, "last_seen": r.last_seen,
            "signed_in_devices": int(devices), "recent": recent, "by_purpose": by_purpose}


# ---------------------------------------------------------------- actions
def set_disabled(admin, uid: str, off) -> dict:
    if not isinstance(off, bool):
        raise Refused("Bad request.")
    with db.engine.begin() as c:
        target = c.execute(sa.select(db.users).where(db.users.c.id == uid)).first()
        if not target:
            raise Refused("No such account", 404)
        if target.id == admin.id:
            raise Refused("You can't disable your own account.")
        if target.is_admin:
            raise Refused("Admin accounts can't be disabled from here.")
        c.execute(db.users.update().where(db.users.c.id == uid).values(disabled=off))
        if off:
            c.execute(db.sessions.delete().where(db.sessions.c.user_id == uid))   # signed out everywhere, at once
        _log(c, admin.id, "disable" if off else "enable", uid)
    from . import auth
    auth.forget(uid)
    return {"ok": True, "disabled": off}


# ---------------------------------------------------------------- by hand, on the server
def set_admin(email: str, on: bool) -> bool:
    email = email.strip().lower()
    with db.engine.begin() as c:
        r = c.execute(sa.select(db.users).where(db.users.c.email == email)).first()
        if not r:
            return False
        c.execute(db.users.update().where(db.users.c.id == r.id).values(is_admin=on))
        if not on:
            c.execute(db.sessions.delete().where(db.sessions.c.user_id == r.id))
        _log(c, r.id, "role:admin" if on else "role:user", r.id, "set from the server command line")
    return True


def _cli(argv):
    db.init()
    if argv[:1] == ["list"]:
        with db.engine.connect() as c:
            for r in c.execute(sa.select(db.users).order_by(db.users.c.created_at)):
                print(f"{'admin' if r.is_admin else 'user ':5}  {'disabled' if r.disabled else '        '}  {r.email}")
        return 0
    if len(argv) == 3 and argv[0] == "plan":
        from . import billing
        with db.engine.connect() as c:
            r = c.execute(sa.select(db.users).where(db.users.c.email == argv[1].strip().lower())).first()
        if not r:
            print(f"No account with the email {argv[1]}. They need to sign up first.")
            return 1
        try:
            status = billing.grant(r.id, argv[2], "cli")
        except billing.BillingError as e:
            print(f"{e} Plans: {', '.join(billing.PLANS)}")
            return 1
        with db.engine.begin() as c:
            _log(c, r.id, "plan", r.id, f"{argv[2]} granted from the server command line")
        print(f"{argv[1]} now has the {billing.PLANS[argv[2]]['label']} plan ({status}).")
        return 0
    if len(argv) == 2 and argv[0] in ("grant", "revoke"):
        if not set_admin(argv[1], argv[0] == "grant"):
            print(f"No account with the email {argv[1]}. They need to sign up first.")
            return 1
        print(f"{argv[1]} is now {'an admin' if argv[0] == 'grant' else 'a normal user'}.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
