"""Friends reaching ClipForge through a Cloudflare Tunnel on this computer. The tunnel hands every visitor over from
127.0.0.1, so ClipForge must tell them apart by Cloudflare's header, and must never treat them as the person sitting
at the computer. Uses its own temporary folder; nothing else is touched."""
import os, sys, tempfile
os.environ.update(PEAKCUT_DATA=tempfile.mkdtemp(prefix="pc-tunnel-"), DATABASE_URL="", PEAKCUT_ACCOUNTS="1",
                  PEAKCUT_PUBLIC_URL="https://clips.example.com")
for name in ("PEAKCUT_TUNNEL", "PEAKCUT_TRUST_PROXY", "PEAKCUT_CLIENT_IP_HEADER"):
    os.environ.pop(name, None)
sys.path.insert(0, ".")
from starlette.requests import Request
from studio import server

fails = []


def check(n, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}"))
    ok or fails.append(n)


def req(peer, cf=None):
    headers = [(b"cf-connecting-ip", cf.encode())] if cf is not None else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (peer, 50000)})


os.environ["PEAKCUT_TUNNEL"] = "1"
check("tunnel on: friend A is known by their own address", server._ip(req("127.0.0.1", "203.0.113.7")), "203.0.113.7")
check("tunnel on: friend B is someone else", server._ip(req("127.0.0.1", "198.51.100.9")), "198.51.100.9")
check("tunnel on: a junk header gives no made-up address", server._ip(req("127.0.0.1", "not an ip")), "tunnel")
check("tunnel on: you at the computer are still 127.0.0.1", server._ip(req("127.0.0.1")), "127.0.0.1")
check("tunnel on: the header from another machine is ignored", server._ip(req("192.168.1.30", "203.0.113.7")), "192.168.1.30")
check("a friend through the tunnel is not at this computer", server._on_this_computer(req("127.0.0.1", "203.0.113.7")), False)
check("you at the computer are", server._on_this_computer(req("127.0.0.1")), True)

os.environ.pop("PEAKCUT_TUNNEL")
check("tunnel off: the header is not believed", server._ip(req("127.0.0.1", "203.0.113.7")), "127.0.0.1")
check("tunnel off: a tunnel visitor is still not at this computer", server._on_this_computer(req("127.0.0.1", "203.0.113.7")), False)

print("ALL PASSED" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
