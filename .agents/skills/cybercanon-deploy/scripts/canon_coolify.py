"""Deploy and inspect CyberCanon on the Cyberdyne Coolify instance.

Stdlib only. Reads COOLIFY_CYBERDYNE_URL and COOLIFY_CYBERDYNE_TOKEN from the
environment. Never prints an environment value: `envs` lists names only and
`logs` / `deploy` redact anything that looks like a credential.

    python3 canon_coolify.py deploy api|web [--force]
    python3 canon_coolify.py state
    python3 canon_coolify.py envs api|web
    python3 canon_coolify.py logs api|web [--lines N] [--grep REGEX]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request

APPS = {"api": "jzigiqhtqv2rl1zlthz9en8l", "web": "o5ry8gvl5iigfrkpbr3ogamj"}
POSTGRES = "gjib7dtmbdb5dfx4yyv9tpp1"
MINIO = "tswe2tfmixoldt24kbrghtkb"
POLL_S = 15
TIMEOUT_S = 900

REDACTIONS = (
    (re.compile(r"(x-access-token:)[^@\s]+@"), r"\1***@"),
    (re.compile(r"\b(gh[opsu]_)[A-Za-z0-9]+"), r"\1***"),
    (re.compile(r"(postgres(?:ql)?://[^:\s]+:)[^@\s]+@"), r"\1***@"),
    (re.compile(r"(https?://[^:\s/]+:)[^@\s]+@"), r"\1***@"),
)


def redact(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def call(method: str, path: str, body: dict | None = None) -> object:
    base = os.environ["COOLIFY_CYBERDYNE_URL"].rstrip("/") + "/api/v1"
    headers = {"Authorization": "Bearer " + os.environ["COOLIFY_CYBERDYNE_TOKEN"]}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def deployment_lines(deployment: dict) -> list[str]:
    raw = deployment.get("logs") or "[]"
    entries = json.loads(raw) if isinstance(raw, str) else raw
    return [entry.get("output", "") for entry in entries]


def wait_for(deployment_uuid: str) -> dict:
    deadline = time.monotonic() + TIMEOUT_S
    while True:
        deployment = call("GET", f"/deployments/{deployment_uuid}")
        if deployment.get("status") not in ("queued", "in_progress"):
            return deployment
        if time.monotonic() > deadline:
            return deployment
        time.sleep(POLL_S)


def interesting(line: str) -> bool:
    markers = ("Pre-deployment", "applied", "healthy", "Healthcheck", "Rolling", "rror")
    return any(marker in line for marker in markers) and not line.startswith("#")


def deploy(app: str, force: bool) -> int:
    # Coolify 4.3.x wants POST here; the global skill's GET is refused with 405.
    query = f"/deploy?uuid={APPS[app]}&force={'true' if force else 'false'}"
    queued = call("POST", query)
    deployment_uuid = queued["deployments"][0]["deployment_uuid"]
    print(f"queued {app}: deployment {deployment_uuid}")
    deployment = wait_for(deployment_uuid)
    status = deployment.get("status")
    print(f"status: {status}  commit: {(deployment.get('commit') or '')[:7]}")
    for line in deployment_lines(deployment):
        if interesting(line):
            print(redact(line[:240]))
    return 0 if status == "finished" else 1


def state() -> int:
    for name, uuid in APPS.items():
        app = call("GET", f"/applications/{uuid}")
        print(f"{name:9} {app.get('status'):20} health_check={app.get('health_check_enabled')}")
    database = call("GET", f"/databases/{POSTGRES}")
    print(f"{'postgres':9} {database.get('status')}")
    service = call("GET", f"/services/{MINIO}")
    print(f"{'minio':9} {service.get('status')}")
    return 0


def envs(app: str) -> int:
    rows = call("GET", f"/applications/{APPS[app]}/envs")
    for key in sorted({row["key"] for row in rows if not row.get("is_preview")}):
        print(key)
    return 0


def logs(app: str, lines: int, grep: str | None) -> int:
    answer = call("GET", f"/applications/{APPS[app]}/logs?lines={lines}")
    wanted = re.compile(grep) if grep else None
    for line in answer.get("logs", "").split("\n"):
        if "/readyz" in line or "/healthz" in line:
            continue
        if wanted is None or wanted.search(line):
            print(redact(line[:400]))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    deploying = commands.add_parser("deploy")
    deploying.add_argument("app", choices=APPS)
    deploying.add_argument("--force", action="store_true", help="rebuild without cache")
    commands.add_parser("state")
    listing = commands.add_parser("envs")
    listing.add_argument("app", choices=APPS)
    reading = commands.add_parser("logs")
    reading.add_argument("app", choices=APPS)
    reading.add_argument("--lines", type=int, default=200)
    reading.add_argument("--grep")
    arguments = parser.parse_args()
    if arguments.command == "deploy":
        return deploy(arguments.app, arguments.force)
    if arguments.command == "envs":
        return envs(arguments.app)
    if arguments.command == "logs":
        return logs(arguments.app, arguments.lines, arguments.grep)
    return state()


if __name__ == "__main__":
    sys.exit(main())
