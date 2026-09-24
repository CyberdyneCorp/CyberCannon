"""Check a CyberCanon production deployment the way a person and the worker see it.

Stdlib only, except `browser` and `write`, which need Playwright
(`pip install playwright && playwright install chromium`).

Environment:
    COOLIFY_CYBERDYNE_URL, COOLIFY_CYBERDYNE_TOKEN  read the worker credential
    CANON_SMOKE_USER, CANON_SMOKE_PASSWORD          the smoke-test person (browser, write)

No credential or token is ever printed: tokens are decoded to their claims.

    python3 verify_prod.py status          worker token -> /status (working copy, index)
    python3 verify_prod.py wait-index      block until /status says the index is in sync
    python3 verify_prod.py refusal         junk bearer -> 401 body (then grep the log)
    python3 verify_prod.py worker          worker token claims + an authenticated read
    python3 verify_prod.py browser         sign in on the web app, report banners
    python3 verify_prod.py write --confirm create one annotation (commits to the repo)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.backend.coolify.cyberdynecorp.ai"
WEB = "https://canon.backend.coolify.cyberdynecorp.ai"
TOKEN_URL = "https://auth.backend.coolify.cyberdynecorp.ai/api/v1/auth/oauth2/token"
API_APP = "jzigiqhtqv2rl1zlthz9en8l"
PROJECT = "ronin"
ASSET = "mech_scout"
VIEW = "concept/mech_scout_front.png"
SESSION_KEY = "cybercanon.session"


def get_json(url: str, token: str | None = None) -> tuple[int, object]:
    headers = {"Authorization": "Bearer " + token} if token else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def worker_token() -> str:
    base = os.environ["COOLIFY_CYBERDYNE_URL"].rstrip("/") + "/api/v1"
    headers = {"Authorization": "Bearer " + os.environ["COOLIFY_CYBERDYNE_TOKEN"]}
    request = urllib.request.Request(f"{base}/applications/{API_APP}/envs", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        rows = json.load(response)
    env = {row["key"]: row["value"] for row in rows if not row.get("is_preview")}
    form = {
        "grant_type": "client_credentials",
        "client_id": env["CANON_WORKER_CLIENT_ID"],
        "client_secret": env["CANON_WORKER_CLIENT_SECRET"],
        "audience": "cybercanon",
    }
    body = urllib.parse.urlencode(form).encode()
    content = {"Content-Type": "application/x-www-form-urlencoded"}
    request = urllib.request.Request(TOKEN_URL, body, content)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["access_token"]


def claims(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def project_status(token: str) -> dict:
    _, answer = get_json(API + "/status", token)
    return next(p for p in answer["data"]["projects"] if p["project"] == PROJECT)


def status() -> int:
    project = project_status(worker_token())
    print(json.dumps(project, indent=2))
    return 0


def wait_index(timeout_s: int = 300) -> int:
    token, deadline = worker_token(), time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        index = project_status(token)["index"]
        if index["in_sync"]:
            print("in sync at", index["indexed_revision"][:10])
            return 0
        time.sleep(10)
    print("index not in sync after", timeout_s, "s:", index)
    return 1


def refusal() -> int:
    code, body = get_json(f"{API}/v1/projects/{PROJECT}/assets", "junk.token.here")
    print(code, json.dumps(body))
    print('now: canon_coolify.py logs api --grep \'"status": 401\'  -> expect a non-null "reason"')
    return 0 if code == 401 else 1


def worker() -> int:
    token = worker_token()
    print({k: claims(token).get(k) for k in ("type", "sub", "client_id", "aud")})
    code, _ = get_json(f"{API}/v1/projects/{PROJECT}/assets", token)
    print("assets read as worker:", code)
    return 0 if code == 200 else 1


def signed_in_page(playwright):  # type: ignore[no-untyped-def]
    import re

    browser = playwright.chromium.launch()
    page = browser.new_page()
    page.goto(WEB + "/sign-in")
    page.get_by_text(re.compile("Sign in with CyberdyneAuth")).first.click()
    page.wait_for_load_state("networkidle")
    page.fill("input[type=email]", os.environ["CANON_SMOKE_USER"])
    page.fill("input[type=password]", os.environ["CANON_SMOKE_PASSWORD"])
    page.keyboard.press("Enter")
    page.wait_for_url(re.compile(re.escape(WEB) + r"/(?!sign-in).*"), timeout=30000)
    page.wait_for_load_state("networkidle")
    return browser, page


def browser_check() -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser, page = signed_in_page(playwright)
        page.wait_for_timeout(2000)
        body = page.inner_text("body")
        for phrase in ("Signed in as", "no git identity", "API is not answering"):
            print(f"{phrase!r}: {phrase in body}")
        token = json.loads(page.evaluate(f"sessionStorage.getItem('{SESSION_KEY}')"))
        picked = ("aud", "client_id", "roles", "type")
        print("access token:", {k: claims(token["accessToken"]).get(k) for k in picked})
        browser.close()
    return 0


def write(label: str) -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser, page = signed_in_page(playwright)
        token = json.loads(page.evaluate(f"sessionStorage.getItem('{SESSION_KEY}')"))
        headers = {
            "Authorization": "Bearer " + token["accessToken"],
            "Content-Type": "application/json",
            "Idempotency-Key": f"smoke-{label}",
        }
        annotation = {
            "id": f"an_smoke_{label}",
            "kind": "art-direction",
            "text": f"Deployment smoke test ({label}).",
            "anchor": {"view": VIEW, "u": 0.5, "v": 0.5},
        }
        url = f"{API}/v1/projects/{PROJECT}/assets/{ASSET}/annotations"
        started = time.monotonic()
        response = page.request.post(url, headers=headers, data=json.dumps(annotation))
        print(response.status, f"{time.monotonic() - started:.2f}s", response.text()[:300])
        browser.close()
    return 0 if response.status == 200 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "wait-index", "refusal", "worker", "browser"):
        commands.add_parser(name)
    writing = commands.add_parser("write")
    writing.add_argument("--confirm", action="store_true", help="it commits to the repository")
    writing.add_argument("--label", required=True, help="unique: id and idempotency key")
    arguments = parser.parse_args()
    if arguments.command == "write":
        if not arguments.confirm:
            print("refusing: a write commits to the content repository; pass --confirm")
            return 2
        return write(arguments.label)
    handlers = {
        "status": status,
        "wait-index": wait_index,
        "refusal": refusal,
        "worker": worker,
        "browser": browser_check,
    }
    return handlers[arguments.command]()


if __name__ == "__main__":
    sys.exit(main())
