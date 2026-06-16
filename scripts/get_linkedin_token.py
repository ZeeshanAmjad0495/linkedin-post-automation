#!/usr/bin/env python3
"""One-time helper to obtain a LinkedIn access token + your author URN.

Prerequisites (see README, step 1):
  - A LinkedIn Developer app with the "Sign In with LinkedIn using OpenID Connect"
    and "Share on LinkedIn" products enabled.
  - Redirect URL configured to:  http://localhost:8000/callback
  - LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET set in your .env

Usage:
  python scripts/get_linkedin_token.py

It opens your browser, you approve access, and it writes LINKEDIN_ACCESS_TOKEN
and LINKEDIN_AUTHOR_URN straight into your .env (the token is not printed).
"""
from __future__ import annotations

import os
import re
import secrets
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
sys.path.insert(0, PROJECT_ROOT)
from src.config import Config  # noqa: E402

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
SCOPES = "openid profile email w_member_social"

_result: dict = {}
_expected_state: str | None = None


def _update_env_file(path: str, updates: dict[str, str]) -> None:
    """Insert/replace KEY=value lines in .env and lock it down to 0600."""
    lines: list[str] = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        match = re.match(r"\s*([A-Z0-9_]+)\s*=", line)
        key = match.group(1) if match else None
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        returned_state = (params.get("state") or [None])[0]
        if not returned_state or not _expected_state or not secrets.compare_digest(
            returned_state, _expected_state
        ):
            # CSRF / auth-code-injection guard: reject any callback whose state
            # doesn't match the value we generated for this run.
            _result["error"] = "state_mismatch"
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h3>Invalid OAuth state. Aborting.</h3></body></html>")
            return
        _result["code"] = (params.get("code") or [None])[0]
        _result["error"] = (params.get("error_description") or params.get("error") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        msg = "Authorization received. You can close this tab and return to the terminal."
        if _result.get("error"):
            msg = f"Authorization failed: {_result['error']}"
        self.wfile.write(f"<html><body><h3>{msg}</h3></body></html>".encode())

    def log_message(self, *_):  # silence default logging
        return


def main() -> int:
    cfg = Config.load()
    if not cfg.linkedin_client_id or not cfg.linkedin_client_secret:
        print("ERROR: set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in .env first.")
        return 2

    global _expected_state
    redirect = cfg.linkedin_redirect_uri
    parsed = urllib.parse.urlparse(redirect)
    host, port = parsed.hostname or "localhost", parsed.port or 8000

    _expected_state = secrets.token_urlsafe(32)
    auth_link = AUTH_URL + "?" + urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": cfg.linkedin_client_id,
            "redirect_uri": redirect,
            "scope": SCOPES,
            "state": _expected_state,
        }
    )
    print("Opening your browser to authorize. If it doesn't open, visit:\n", auth_link, "\n")
    webbrowser.open(auth_link)

    server = HTTPServer((host, port), _Handler)
    server.handle_request()  # serve exactly one callback
    server.server_close()

    if _result.get("error") or not _result.get("code"):
        print("ERROR: did not receive an authorization code.", _result.get("error") or "")
        return 1

    token_resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": _result["code"],
            "redirect_uri": redirect,
            "client_id": cfg.linkedin_client_id,
            "client_secret": cfg.linkedin_client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if token_resp.status_code != 200:
        print("ERROR exchanging code:", token_resp.status_code, token_resp.text[:300])
        return 1
    token = token_resp.json().get("access_token")
    expires = token_resp.json().get("expires_in")

    userinfo = requests.get(USERINFO_URL, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if userinfo.status_code != 200:
        print("ERROR fetching userinfo:", userinfo.status_code, userinfo.text[:300])
        print("Token was obtained but URN lookup failed. You can set LINKEDIN_AUTHOR_URN manually.")
        sub = None
    else:
        sub = userinfo.json().get("sub")

    if not token:
        print("ERROR: token exchange succeeded but no access_token was returned.")
        return 1

    updates = {"LINKEDIN_ACCESS_TOKEN": token}
    if sub:
        updates["LINKEDIN_AUTHOR_URN"] = f"urn:li:person:{sub}"
    _update_env_file(ENV_PATH, updates)

    print("\n" + "=" * 70)
    print(f"SUCCESS — credentials written to {ENV_PATH} (permissions set to 600).")
    print(f"  LINKEDIN_ACCESS_TOKEN = ****{token[-4:]}  (hidden; not printed)")
    if sub:
        print(f"  LINKEDIN_AUTHOR_URN   = urn:li:person:{sub}")
    else:
        print("  LINKEDIN_AUTHOR_URN   = (URN lookup failed; set it manually in .env)")
    print("=" * 70)
    if expires:
        days = int(expires) // 86400
        print(f"\nNote: this access token expires in ~{days} days. Re-run this script to renew.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
