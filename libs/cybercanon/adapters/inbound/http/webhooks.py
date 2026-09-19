"""The repository notification endpoint — D4's optimisation, not its guarantee.

*"The scheduler is the guarantee; the webhook is an optimisation."* Everything
about this module follows from that one sentence. A notification shortens the
wait between a commit landing and the working copy seeing it; it is never the
reason the working copy is current, because webhooks are lost, misconfigured and
silently disabled by repository administrators, and a project that was quietly
hours stale with nothing reporting it is the failure D4 refuses.

So the endpoint is allowed to do exactly one thing — ask for the refresh the
timer would have asked for later — and `hosted-repository` fixes what happens in
each of the four cases:

* **authenticated, for a configured project, on its branch** — refresh now;
* **unauthenticated** — *"it SHALL be ignored, and no refresh SHALL occur"*. Not
  a retry, not a queue: ignored. The origin of a notification is the only thing
  standing between an open endpoint and anybody being able to make this service
  fetch on demand;
* **an unknown project** and **an uninteresting branch** — *"accepted and
  discarded without error"*, because a repository host that got an error back
  would start disabling the hook, and the projects that *are* configured would
  lose their optimisation over a project that never existed.

**The decision is a pure function** (:func:`classify`) and the router only
dispatches it. That keeps the four cases testable with no application, no
transport and no signature ceremony, and keeps this module what every inbound
adapter here has to be: a translator.

Authentication is an HMAC of the exact bytes received, compared in constant time.
Not a shared bearer token in a header, because the body is what is being
attested — a token proves somebody knows the token, and a digest proves *this
notification* came from somebody who does.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

WEBHOOK_PATH = "/hooks/repository"
"""Where a repository host posts. Outside the versioned surface deliberately.

The versioned prefix is a contract with *our* clients about the shape of our
resources. This is an inbound hint from a third party whose payload shape we do
not control and barely read; versioning it would imply a promise nobody needs.
"""

HOOK_TAG = "hooks"

SIGNATURE_HEADER = "X-Canon-Signature"
ALGORITHM = "sha256"
PREFIX = f"{ALGORITHM}="

PROJECT_FIELD = "project"
REF_FIELD = "ref"
BRANCH_REFS = "refs/heads/"

ACCEPTED = 202
UNAUTHORIZED = 401
MALFORMED = 400


class Notice(Enum):
    """What a notification turned out to be. Four of the five are not errors."""

    REFRESHED = "refreshed"
    UNAUTHENTICATED = "unauthenticated"
    UNKNOWN_PROJECT = "unknown_project"
    OTHER_BRANCH = "other_branch"
    UNREADABLE = "unreadable"

    @property
    def refreshes(self) -> bool:
        return self is Notice.REFRESHED

    def __str__(self) -> str:
        return self.value


STATUSES: Mapping[Notice, int] = {
    Notice.REFRESHED: ACCEPTED,
    Notice.UNKNOWN_PROJECT: ACCEPTED,
    Notice.OTHER_BRANCH: ACCEPTED,
    Notice.UNAUTHENTICATED: UNAUTHORIZED,
    Notice.UNREADABLE: MALFORMED,
}
"""One mapping from outcome to status, in one place, the way D10 asks for.

Accepted-and-discarded is a 202 and so is a refresh: from the repository host's
side both mean *received, nothing for you to do*, which is what keeps a hook for
a project we do not serve from being switched off at the other end.
"""


def signature_for(secret: str, body: bytes) -> str:
    """The signature these bytes carry when they come from a configured origin."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"{PREFIX}{digest}"


def authenticated(secret: str, offered: str, body: bytes) -> bool:
    """Whether this notification's origin is the configured one.

    A constant-time comparison, and a configured secret that is empty
    authenticates nothing — an unset secret must not become an open endpoint.
    """
    if not secret or not offered:
        return False
    return hmac.compare_digest(signature_for(secret, body), offered.strip())


def notified(body: bytes) -> tuple[str, str]:
    """The project and ref a notification names, or two empty strings.

    Two fields read out of a payload whose remaining shape differs by host and
    is none of our business. A body this cannot read is *unreadable*, which is
    the one case that is neither a refresh nor a silent discard.
    """
    try:
        payload = json.loads(body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return "", ""
    if not isinstance(payload, dict):
        return "", ""
    return str(payload.get(PROJECT_FIELD, "")), str(payload.get(REF_FIELD, ""))


def names_branch(ref: str, branch: str) -> bool:
    """Whether that ref is the project's configured branch, however it was spelled."""
    return ref in {branch, f"{BRANCH_REFS}{branch}"}


def classify(
    *,
    secret: str,
    offered: str,
    body: bytes,
    branches: Mapping[str, str],
) -> tuple[Notice, str]:
    """What this notification is, and which project it concerns.

    Pure, and the whole decision. The router below turns the answer into a
    refresh and a status code and does nothing else, so the four specified cases
    are exercised without a transport.
    """
    if not authenticated(secret, offered, body):
        return Notice.UNAUTHENTICATED, ""
    project, ref = notified(body)
    if not project:
        return Notice.UNREADABLE, ""
    branch = branches.get(project)
    if branch is None:
        return Notice.UNKNOWN_PROJECT, project
    if not names_branch(ref, branch):
        return Notice.OTHER_BRANCH, project
    return Notice.REFRESHED, project


@dataclass(frozen=True)
class RepositoryNotifications:
    """What the endpoint needs: a secret, the configured branches, and a refresh.

    `refresh` is the use case, handed in by the composition root, so this module
    reaches no port and imports no outbound adapter — the rule the layering
    contract enforces for the whole inbound package.
    """

    secret: str
    branches: Mapping[str, str]
    refresh: Callable[[str], object]


def register(app: FastAPI, notifications: RepositoryNotifications | None = None) -> None:
    """Add the notification endpoint, when this deployment has one configured.

    A deployment with no webhook secret has no endpoint at all rather than an
    endpoint that refuses everything: the scheduler is the guarantee, so a
    service configured without a hook is fully correct and simply slower.
    """
    if notifications is None:
        return

    @app.post(WEBHOOK_PATH, tags=[HOOK_TAG])
    async def repository_notified(request: Request) -> JSONResponse:
        """One notification: classified, acted on when it says to, always answered."""
        body = await request.body()
        notice, project = classify(
            secret=notifications.secret,
            offered=request.headers.get(SIGNATURE_HEADER, ""),
            body=body,
            branches=notifications.branches,
        )
        if notice.refreshes:
            notifications.refresh(project)
        return JSONResponse(
            status_code=STATUSES[notice],
            content={"outcome": notice.value, PROJECT_FIELD: project},
        )


__all__ = [
    "ACCEPTED",
    "ALGORITHM",
    "HOOK_TAG",
    "MALFORMED",
    "PREFIX",
    "SIGNATURE_HEADER",
    "STATUSES",
    "UNAUTHORIZED",
    "WEBHOOK_PATH",
    "Notice",
    "RepositoryNotifications",
    "authenticated",
    "classify",
    "names_branch",
    "notified",
    "register",
    "signature_for",
]
