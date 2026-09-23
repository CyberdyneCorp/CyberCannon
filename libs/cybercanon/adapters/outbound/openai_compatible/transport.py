"""The Chat Completions request, built by hand, and what went wrong (D1, D5).

Split from :mod:`~cybercanon.adapters.outbound.openai_compatible.models` for the
reason `ArcheTransport` is split from the platform it serves: everything that
**decides** anything — what the body looks like, what a status code means, what
an exception's name says about which reason it is — runs against values with no
socket anywhere, and what is left is one request and a timeout.

Three decisions live here.

* **The body is the documented minimum** (`llm-integration`: *"SHALL NOT depend
  on features absent from that interface"*). A model identifier and one user
  message. No temperature, no seed, no `response_format`, no tools, no streaming
  — every one of those is a field some compatible proxy answers `400` to, and
  none of them is needed.
* **Two identifiers produce two requests differing only in that field.**
  :func:`chat_body` takes the identifier and places it, and nothing else in this
  module reads it. There is no branch on a model's name anywhere in this
  package, which is what makes *"a new model is a configuration change"* true
  rather than aspirational.
* **Every way of not answering maps onto exactly one reason.** A timeout is
  `TIMEOUT`, anything else the client raises is `UNREACHABLE`, `401`/`403` is
  `REJECTED` and not retried, `408`/`429`/`5xx` are transient, any other status
  is `REJECTED`, and a success whose body is not the shape this adapter was
  written against is `MALFORMED` — which is a different sentence from *the
  gateway is down*, and the difference is what tells a person which team to talk
  to.

No provider SDK is imported here or anywhere else, and `httpx` is imported
*inside* the function that sends, so this module can be exercised — body
shapes, status mapping, media sniffing — with no HTTP library involved at all.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from cybercanon.application.ports.llm import Unavailability

COMPLETIONS_PATH = "/chat/completions"
"""The one path this system speaks. Appended to whatever base URL was configured."""

JSON_CONTENT = "application/json"

TIMEOUT_NAMES = ("timeout", "timedout", "readtimeout", "connecttimeout", "pooltimeout")
"""Exception type names that mean *the budget ran out*, whichever client raised.

Matched by name rather than by class so this module imports no HTTP library at
module scope — the same reason the import below is inside a function.
"""

TRANSIENT_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
"""Statuses worth trying again: a wait, a rate limit, a gateway having a moment.

`llm-integration` requires a rate limit to degrade like every other failure and
requires that authentication failures and invalid requests are **not** retried.
Those two sets are disjoint and both are written down, so neither is inferred
from a range somebody widened later.
"""

REJECTING_STATUSES = frozenset({401, 403})
"""The credential was refused. Exactly one attempt, and the reason is `rejected`."""

MEDIA_TYPES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
    (b"RIFF", "image/webp"),
)
"""How an image's media type is read: from the bytes, never from a file name.

The port hands over bytes and nothing else, which is the point — a caller has no
parameter to smuggle a path through — so the type is sniffed here, in the
adapter, exactly as `ImageInspector` reads a format from content rather than
from an extension.
"""

DEFAULT_MEDIA_TYPE = "application/octet-stream"
"""What unrecognised bytes are sent as. The endpoint decides whether it can read them."""


class TransportFailure(Exception):
    """The endpoint did not answer usefully, and this is which way it did not.

    Carries the reason and whether trying again could plausibly help, so the
    retry loop is a property of the failure rather than a table the caller keeps
    in step with this module.
    """

    def __init__(self, reason: Unavailability, detail: str = "") -> None:
        super().__init__(detail or str(reason))
        self.reason = reason
        self.detail = detail

    @property
    def is_transient(self) -> bool:
        return self.reason.is_transient


# --------------------------------------------------------------------------
# The request body — pure, and the whole of the wire format
# --------------------------------------------------------------------------


def text_message(instruction: str) -> dict[str, Any]:
    """One user turn carrying an instruction and nothing else."""
    return {"role": "user", "content": instruction}


def image_message(image: bytes, instruction: str) -> dict[str, Any]:
    """One user turn carrying the image and the fixed instruction. Nothing else.

    The multimodal shape every compatible endpoint implements: a content list of
    an `image_url` part whose URL is a `data:` URI, and a `text` part. There is
    no third part and no parameter that could add one, which is what makes
    *"only that image and a fixed instruction SHALL be transmitted"* structural.
    """
    return {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": data_uri(image)}},
            {"type": "text", "text": instruction},
        ],
    }


def chat_body(model: str, message: Mapping[str, Any]) -> dict[str, Any]:
    """The documented minimum: which model, and one message. Verbatim, both.

    The identifier is placed and never inspected — no allow-list, no enum, no
    branch — so two configured identifiers produce bodies that differ in exactly
    one value.
    """
    return {"model": model, "messages": [dict(message)]}


def data_uri(image: bytes) -> str:
    """The image as a `data:` URI, with its media type read from its own bytes."""
    encoded = base64.b64encode(image).decode("ascii")
    return f"data:{media_type(image)};base64,{encoded}"


def media_type(image: bytes) -> str:
    """What these bytes are, by signature. Unrecognised bytes are sent as opaque."""
    for signature, declared in MEDIA_TYPES:
        if image.startswith(signature):
            return declared
    return DEFAULT_MEDIA_TYPE


def first_text(payload: Any) -> str | None:
    """The assistant's text, or ``None`` when the answer is not one this reads.

    Defensive by requirement (D10): an answer with no choices, a choice with no
    message, a message with no string content and a body that is not a mapping
    are all *malformed*, which the caller reports rather than partially
    accepting.
    """
    if not isinstance(payload, Mapping):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
    content = message.get("content") if isinstance(message, Mapping) else None
    return content if isinstance(content, str) and content.strip() else None


# --------------------------------------------------------------------------
# Sending it
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Answer:
    """One HTTP answer, reduced to the two things any decision here needs."""

    status: int
    payload: Any = None

    @property
    def is_ok(self) -> bool:
        return 200 <= self.status < 300


@dataclass
class ChatTransport:
    """Sends one Chat Completions request to a configured endpoint.

    `client` exists so a suite can hand in a recorder and assert what actually
    went out — the model, the message, the absence of everything else — rather
    than what the code appears to send. It defaults to `httpx`, which is the
    only thing this adapter would otherwise need at import time.
    """

    base_url: str
    api_key: str = field(default="", repr=False)
    timeout: timedelta = timedelta(seconds=30)
    client: Any | None = None
    sent: list[dict[str, Any]] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{self.base_url.rstrip('/')}{COMPLETIONS_PATH}"

    def headers(self) -> dict[str, str]:
        """The configured credential, or none at all when there is none.

        A request with no key carries no `Authorization` header rather than an
        empty one: a private gateway that accepts unauthenticated calls is a
        real deployment, and `Bearer ` would be a credential it had to reject.
        """
        headers = {"Content-Type": JSON_CONTENT, "Accept": JSON_CONTENT}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def send(self, body: Mapping[str, Any]) -> str:
        """The assistant's text, or :class:`TransportFailure` saying why there is none."""
        self.sent.append(dict(body))
        answer = self._answer(body)
        _raise_for(answer)
        text = first_text(answer.payload)
        if text is None:
            raise TransportFailure(
                Unavailability.MALFORMED, "the answer carried no assistant message"
            )
        return text

    def _answer(self, body: Mapping[str, Any]) -> Answer:
        client = self._client()
        try:
            response = client.request(
                "POST",
                self.url,
                headers=self.headers(),
                json=dict(body),
                timeout=self.timeout.total_seconds(),
            )
        except Exception as failure:  # every HTTP client raises its own family
            raise _unreachable(failure) from failure
        return Answer(status=response.status_code, payload=_decoded(response))

    def _client(self) -> Any:
        if self.client is not None:
            return self.client
        import httpx

        return httpx


def _raise_for(answer: Answer) -> None:
    """The status line as one reason, or nothing at all when it succeeded."""
    if answer.is_ok:
        return
    if answer.status in REJECTING_STATUSES:
        raise TransportFailure(
            Unavailability.REJECTED, f"the endpoint refused the credential ({answer.status})"
        )
    if answer.status in TRANSIENT_STATUSES:
        raise TransportFailure(Unavailability.UNREACHABLE, f"the endpoint answered {answer.status}")
    raise TransportFailure(
        Unavailability.REJECTED, f"the endpoint rejected the request ({answer.status})"
    )


def _unreachable(failure: Exception) -> TransportFailure:
    """A client's own exception as one of the two reasons a call can not arrive."""
    name = type(failure).__name__.lower()
    if any(marker in name for marker in TIMEOUT_NAMES):
        return TransportFailure(Unavailability.TIMEOUT, "the request budget ran out")
    return TransportFailure(Unavailability.UNREACHABLE, type(failure).__name__)


def _decoded(response: Any) -> Any:
    """The body as data, or ``None`` when it is not JSON.

    A failing status with an HTML body is not malformed — it is a refusal the
    status line already says — so the parse failure is swallowed and the status
    decides. A *successful* answer that is not JSON falls through to
    :func:`first_text`, which reports it as malformed.
    """
    try:
        return response.json()
    except Exception:  # a proxy answering HTML, a gateway answering nothing
        return None


__all__ = [
    "COMPLETIONS_PATH",
    "DEFAULT_MEDIA_TYPE",
    "MEDIA_TYPES",
    "REJECTING_STATUSES",
    "TIMEOUT_NAMES",
    "TRANSIENT_STATUSES",
    "Answer",
    "ChatTransport",
    "TransportFailure",
    "chat_body",
    "data_uri",
    "first_text",
    "image_message",
    "media_type",
    "text_message",
]
