"""Every email ClipForge sends, in one design, over SMTP.

Works with any SMTP service: Gmail (with an app password), Resend, Postmark, Brevo, Amazon SES and so on. Set
PEAKCUT_SMTP_HOST, PEAKCUT_SMTP_PORT (587), PEAKCUT_SMTP_USER, PEAKCUT_SMTP_PASSWORD_FILE (a file holding the password)
and PEAKCUT_MAIL_FROM ("ClipForge <you@example.com>"). Without them nothing is sent; on your own computer the link is
printed in the server's output instead.

The emails:
  verify          confirm your email address (after signing up with a password)
  reset           choose a new password
  welcome         welcome, and how to make the first clip (every new account)
  password_changed  security notice after a password change or reset
  receipt         a plan was paid for: what was bought, until when
  clips_ready     a long video has finished
  test            the admin's "are emails working?" check
"""
import html
import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr

from . import config

log = logging.getLogger("clipforge.mail")

LOGO = config.ROOT / "web" / "brand" / "logo-email.png"   # PNG: email apps don't show SVG
LOGO_CID = "clipforge-logo"
INK, PAPER, CARD, LINE, DIM, ACCENT = "#1C1B19", "#F6F1E8", "#FFFDF9", "#E6DDCE", "#6E6A62", "#E4572E"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
SERIF = "Georgia,'Times New Roman',serif"


def ready() -> bool:
    return bool(config.SMTP_HOST and config.MAIL_FROM and (not config.SMTP_USER or config.smtp_password()))


def _html(m: dict, logo_src: str = "cid:" + LOGO_CID) -> str:
    """The ClipForge email: paper background, a card with a vermilion line on top, a serif headline, one clear button,
    optional detail rows and a note, and a quiet footer. Tables and inline styles only: what every email app shows alike."""
    e = html.escape
    site = config.PUBLIC_URL
    kicker = f'<tr><td style="font-family:{SANS};font-size:12px;letter-spacing:.14em;text-transform:uppercase;font-weight:700;color:{ACCENT};padding-bottom:10px">{e(m["kicker"])}</td></tr>' if m.get("kicker") else ""
    paras = "".join(f'<tr><td style="font-family:{SANS};font-size:16px;line-height:1.65;color:#3A3834;padding-bottom:16px">{e(p)}</td></tr>' for p in m.get("body", []))
    steps = ""
    if m.get("steps"):
        rows = "".join(f'<tr><td valign="top" style="width:34px;padding:0 0 12px"><div style="width:26px;height:26px;line-height:26px;border-radius:13px;background:{ACCENT};color:#fff;text-align:center;font-family:{SANS};font-size:13px;font-weight:700">{i}</div></td>'
                       f'<td style="font-family:{SANS};font-size:15px;line-height:1.55;color:#3A3834;padding:2px 0 12px"><b style="color:{INK}">{e(t)}</b><br>{e(d)}</td></tr>' for i, (t, d) in enumerate(m["steps"], 1))
        steps = f'<tr><td style="padding:4px 0 10px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table></td></tr>'
    details = ""
    if m.get("details"):
        rows = "".join(f'<tr><td style="font-family:{SANS};font-size:14px;color:{DIM};padding:9px 0;border-top:1px solid {LINE}">{e(k)}</td>'
                       f'<td align="right" style="font-family:{SANS};font-size:14px;color:{INK};font-weight:600;padding:9px 0;border-top:1px solid {LINE}">{e(v)}</td></tr>' for k, v in m["details"])
        details = f'<tr><td style="padding:2px 0 22px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-bottom:1px solid {LINE}">{rows}</table></td></tr>'
    button = ""
    if m.get("button") and m.get("link"):
        button = (f'<tr><td style="padding:6px 0 26px"><table role="presentation" cellpadding="0" cellspacing="0"><tr><td style="border-radius:999px;background:{INK}">'
                  f'<a href="{e(m["link"])}" style="display:inline-block;padding:15px 30px;font-family:{SANS};font-size:16px;font-weight:700;color:{PAPER};text-decoration:none;border-radius:999px">{e(m["button"])} &rarr;</a>'
                  f'</td></tr></table></td></tr>')
    note = (f'<tr><td style="padding:0 0 22px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="background:#FBF1E6;border:1px solid #F1DFCB;border-radius:12px;padding:14px 16px;font-family:{SANS};font-size:14px;line-height:1.55;color:#5A4A40">{e(m["note"])}</td></tr></table></td></tr>') if m.get("note") else ""
    small = f'<tr><td style="font-family:{SANS};font-size:13px;line-height:1.6;color:{DIM};padding-bottom:18px">{e(m["outro"])}</td></tr>' if m.get("outro") else ""
    fallback = (f'<tr><td style="border-top:1px solid {LINE};padding-top:16px;font-family:{SANS};font-size:12px;line-height:1.6;color:#A29C91">'
                f'Button not working? Copy this link into your browser:<br><a href="{e(m["link"])}" style="color:{INK};word-break:break-all">{e(m["link"])}</a></td></tr>') if m.get("button") and m.get("link") else ""
    title = e(m["title"])
    if m.get("accent") and m["accent"] in m["title"]:      # one word of the headline in vermilion italics
        title = title.replace(e(m["accent"]), f'<em style="font-style:italic;color:{ACCENT}">{e(m["accent"])}</em>', 1)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light"><title>{e(m["title"])}</title></head>
<body style="margin:0;padding:0;background:{PAPER};-webkit-text-size-adjust:100%">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{PAPER}">{e(m.get("preheader") or (m.get("body") or [m["title"]])[0])}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER}"><tr><td align="center" style="padding:36px 14px 40px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:540px">
    <tr><td style="padding:0 4px 20px"><a href="{e(site)}" style="text-decoration:none"><img src="{e(logo_src)}" width="150" height="36" alt="ClipForge" style="display:block;border:0;width:150px;height:36px"></a></td></tr>
    <tr><td style="background:{CARD};border:1px solid {LINE};border-radius:22px;overflow:hidden">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr><td style="height:5px;line-height:5px;font-size:0;background:{ACCENT};border-radius:22px 22px 0 0">&nbsp;</td></tr>
        <tr><td style="padding:34px 34px 18px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          {kicker}
          <tr><td style="font-family:{SERIF};font-size:34px;line-height:1.1;font-weight:400;color:{INK};padding-bottom:18px;letter-spacing:-.01em">{title}</td></tr>
          {paras}{steps}{details}{button}{note}{small}{fallback}
        </table></td></tr>
      </table></td></tr>
    <tr><td align="center" style="padding:24px 10px 0;font-family:{SANS};font-size:12px;line-height:1.7;color:#A29C91">
      {e(m.get("why") or "You're getting this because of your ClipForge account.")}<br>
      <a href="{e(site)}" style="color:{DIM};text-decoration:underline">ClipForge</a> &nbsp;&middot;&nbsp;
      <a href="{e(site)}/privacy" style="color:{DIM};text-decoration:underline">Privacy</a> &nbsp;&middot;&nbsp;
      <a href="{e(site)}/terms" style="color:{DIM};text-decoration:underline">Terms</a></td></tr>
  </table></td></tr></table></body></html>"""


def _text(m: dict) -> str:
    """The plain-text part, for email apps that show text only."""
    out = [m["title"], ""] + list(m.get("body", []))
    for i, (t, d) in enumerate(m.get("steps") or [], 1):
        out.append(f"{i}. {t}: {d}")
    for k, v in m.get("details") or []:
        out.append(f"{k}: {v}")
    if m.get("button") and m.get("link"):
        out += ["", f"{m['button']}: {m['link']}"]
    if m.get("note"):
        out += ["", m["note"]]
    if m.get("outro"):
        out += ["", m["outro"]]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- the emails
def m_verify(link):
    return {"subject": "Confirm your email for ClipForge", "kicker": "One quick step", "title": "Confirm your email", "accent": "email",
            "body": ["Thanks for joining ClipForge. Confirm this is your email address and you're ready to start clipping."],
            "button": "Confirm my email", "link": link,
            "outro": "The link works for 3 days. If you didn't sign up for ClipForge, you can ignore this email."}


def m_reset(link):
    return {"subject": "Reset your ClipForge password", "kicker": "Password reset", "title": "Choose a new password", "accent": "new",
            "body": ["Someone asked to reset the password for your ClipForge account. If that was you, choose a new one below."],
            "button": "Choose a new password", "link": link,
            "note": "Didn't ask for this? Ignore this email: your password stays the same and nobody can change it without this link.",
            "outro": "The link works for one hour and only once."}


def m_welcome(name):
    site = config.PUBLIC_URL
    return {"subject": "Welcome to ClipForge", "kicker": "Welcome aboard", "title": f"Hey {name or 'there'}, let's make some shorts", "accent": "shorts",
            "body": ["Your ClipForge account is ready. Here's how to get your first clips in a few minutes:"],
            "steps": [("Paste a link or upload", "A YouTube, Twitch or Kick video, or a recording from your PC or console."),
                      ("Pick your style", "Facecam layout, caption style and background, with a live preview."),
                      ("Get your clips", "The best moments come back framed for 9:16, captioned and ready to post.")],
            "button": "Make your first clip", "link": site + "/app",
            "outro": "Free previews are on us every day. When you want full 1080p downloads, pick a plan from the Plans page."}


def m_password_changed(when_text):
    return {"subject": "Your ClipForge password was changed", "kicker": "Security notice", "title": "Your password was changed", "accent": "changed",
            "body": [f"The password for your ClipForge account was changed {when_text}. Other devices were signed out."],
            "note": "If this wasn't you, reset your password now and check your email account's security: someone may have access to it.",
            "button": "Reset my password", "link": config.PUBLIC_URL + "/reset",
            "outro": "If it was you, there's nothing else to do."}


def m_receipt(plan_label, amount_rupees, minutes, until_text, order_id):
    return {"subject": f"Your ClipForge {plan_label} plan is active", "kicker": "Payment received", "title": f"You're on {plan_label}", "accent": plan_label,
            "body": ["Thanks for your payment. Your plan is active and your minutes are ready to use."],
            "details": [("Plan", plan_label), ("Amount paid", f"₹{amount_rupees:,.0f} (GST included)"), ("Minutes", f"{minutes:,}"),
                        ("Valid until", until_text), ("Order", order_id)],
            "button": "Open ClipForge", "link": config.PUBLIC_URL + "/app",
            "outro": "Plans don't renew by themselves. Keep this email as your receipt.", "why": "You're getting this because you bought a ClipForge plan."}


def m_clips_ready(title, count, link):
    return {"subject": f"{count} clip{'s' if count != 1 else ''} ready: {title[:60]}", "kicker": "Your clips are ready", "title": f"{count} new clip{'s' if count != 1 else ''}, ready to post", "accent": "ready",
            "body": [f"We finished “{title}”. The best moments are framed, captioned and waiting for you."],
            "button": "See my clips", "link": link,
            "outro": "Tip: open a clip to change its hook, captions or facecam style before you download it.",
            "why": "You're getting this because a long video finished on your ClipForge account."}


def m_test():
    return {"subject": "ClipForge test email", "kicker": "All good", "title": "Your emails are working", "accent": "working",
            "body": ["This test email came through, so sign-up confirmations, password resets and receipts will reach people."],
            "button": "Open ClipForge", "link": config.PUBLIC_URL + "/app"}


KINDS = {"verify": lambda: m_verify(config.PUBLIC_URL + "/auth/verify?t=example"), "reset": lambda: m_reset(config.PUBLIC_URL + "/reset?t=example"),
         "welcome": lambda: m_welcome("Malhar"), "password_changed": lambda: m_password_changed("today at 3:42 PM"),
         "receipt": lambda: m_receipt("Creator", 399, 600, "16 Dec 2026", "order_ExAmPlE123"),
         "clips_ready": lambda: m_clips_ready("I'm Back for Rank 1.", 6, config.PUBLIC_URL + "/app"), "test": m_test}


def preview(kind="verify") -> str:
    """An email for viewing in a browser (admin preview): the logo is inlined so it shows without an email app."""
    import base64
    data = "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode() if LOGO.is_file() else ""
    return _html(KINDS.get(kind, KINDS["verify"])(), logo_src=data)


def deliver(to: str, m: dict) -> bool:
    """Send one email in the background. Returns False when no mail service is set up."""
    if not ready():
        if config.HTTPS:      # a real site: a sign-in link must never sit in a log file
            log.warning("Email not set up, so nothing was sent: %s", m["subject"])
        else:                 # on your own computer the link is printed so you can use it
            print(f"[ClipForge mail] {m['subject']} for {to}: {m.get('link', '')}", flush=True)
        return False
    msg = EmailMessage()
    name, addr = parseaddr(config.MAIL_FROM)
    msg["From"] = formataddr((name or "ClipForge", addr))
    msg["To"] = to
    msg["Subject"] = m["subject"]
    msg["Message-ID"] = make_msgid(domain=addr.split("@")[-1] if "@" in addr else None)
    msg.set_content(_text(m))
    msg.add_alternative(_html(m), subtype="html")
    if LOGO.is_file():   # the logo travels inside the email, so it shows without loading anything from the web
        msg.get_payload()[1].add_related(LOGO.read_bytes(), maintype="image", subtype="png", cid=f"<{LOGO_CID}>",
                                         filename="clipforge.png", disposition="inline")

    def work():
        try:
            if config.SMTP_PORT == 465:
                with smtplib.SMTP_SSL(config.SMTP_HOST, 465, context=ssl.create_default_context(), timeout=20) as s:
                    if config.SMTP_USER:
                        s.login(config.SMTP_USER, config.smtp_password())
                    s.send_message(msg)
            else:
                with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
                    s.starttls(context=ssl.create_default_context())
                    if config.SMTP_USER:
                        s.login(config.SMTP_USER, config.smtp_password())
                    s.send_message(msg)
        except Exception as e:  # noqa: BLE001 - never the password in the message: smtplib does not echo it
            log.error("Could not send %r to %s: %s", m["subject"], to, e)
            print(f"[ClipForge mail] could not send {m['subject']!r} to {to}: {e}", flush=True)

    threading.Thread(target=work, daemon=True).start()
    return True


def send(to: str, subject: str, title: str, intro: str, button: str, link: str, outro: str) -> bool:
    """Older call style, still used in a few places: one paragraph and one button."""
    return deliver(to, {"subject": subject, "title": title, "body": [intro], "button": button, "link": link, "outro": outro})
