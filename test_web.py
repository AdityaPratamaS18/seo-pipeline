#!/usr/bin/env python3
"""Redirect tests.

A real local server answering with the codes hosts actually send. The 308 case
is the one that made a live Vercel site read as unreachable on Python 3.9.
"""
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError
from urllib.request import Request

from stages.web import urlopen

results = []


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/r"):
            code = int(self.path[2:5])
            self.send_response(code)
            self.send_header("Location", "/final")
            self.end_headers()
        elif self.path == "/final":
            body = b"<h1>arrived</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


server = HTTPServer(("127.0.0.1", 0), Site)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_address[1]}"


def get(path):
    with urlopen(Request(base + path), timeout=5) as r:
        return r.status, r.geturl(), r.read()


print("\nEVERY REDIRECT A HOST SENDS IS FOLLOWED")
for code in (301, 302, 303, 307, 308):
    try:
        status, final, body = get(f"/r{code}")
        check(status == 200 and final.endswith("/final") and b"arrived" in body,
              f"{code} lands on the final page", f"got {status} at {final}")
    except Exception as e:                                          # noqa: BLE001
        check(False, f"{code} lands on the final page", repr(e))

print("\nA MISSING PAGE STILL FAILS")
try:
    get("/nope")
    check(False, "404 raises")
except HTTPError as e:
    check(e.code == 404, "404 raises, rather than reading as a page")

server.shutdown()
print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
