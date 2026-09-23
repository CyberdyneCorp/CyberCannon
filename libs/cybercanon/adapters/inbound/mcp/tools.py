"""The FastMCP stdio server — eight read tools and two writes, over one container.

This is the second inbound adapter, and it is the first real test of the "one
core, three surfaces" claim: if anything below decided something the command
line does not, the claim was false and the product would have acquired the bug
it exists to prevent. So the module is deliberately shaped so that there is
nothing here to disagree with.

* **Every tool is three lines**: take the arguments, call one method on the
  :class:`~cybercanon.adapters.wiring.container.Container`, hand the result to a
  renderer. `validate_export` calls the same use case `canon validate` calls, so
  the agent and the artist cannot receive different verdicts.
* **The advertised surface is a literal** — :data:`TOOL_NAMES`. A test asserts
  the server advertises exactly that set, so adding a tool fails the build until
  somebody edits this list and explains themselves (D6). That is how the
  prohibition on a promotion tool is *enforced* rather than merely intended:
  promotion writes durable constraints, and an agent that could raise a budget
  until its own output passed is how trust in the system dies in week two.
* **Nothing takes an identity.** No tool has an actor, a role or an entitlement
  parameter. Identity comes from the credential the process was launched with
  and the chain that ends in a local unauthenticated actor, so a read works with
  no credential, no network and no services — and a caller cannot claim to be
  anybody.
* **A lens is a free parameter carrying no authority.** Authorization is decided
  before the lens is looked at (D3), inside the use case, which is what makes it
  safe to let a caller send any lens string it likes.
* **The two write tools are proposals** (`add-mcp-writes`). They record an
  observation and report a verdict, and the list of them is
  :data:`WRITE_TOOL_NAMES` — two entries, and the number is the requirement
  rather than a starting point. Nothing here promotes, resolves, edits a
  constraint or creates an asset, because there is no tool that could.

Failures are answers, and since D10 they are answers *by construction*: a use
case returns one of seven outcomes rather than raising, so an unknown
identifier, a malformed specification or a revision the repository cannot reach
arrives here as a value and leaves as prose naming the cause and, where one
exists, the action that resolves it. Nothing below raises out of a tool, because
an exception would end an agent's session over a typo — and nothing below
catches one either.

The transport is standard input and output, and there is no other. The server
never opens a listening port: hosting it would mean CORS, an open socket and a
network threat model, all of which local-first exists to avoid.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from fastmcp import FastMCP

from cybercanon.adapters.inbound.mcp import rendering, writes
from cybercanon.adapters.inbound.mcp.writes import WRITE_TOOL_NAMES
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.results import Result, succeeded
from cybercanon.application.use_cases.index_assets import UnreadableSpec
from cybercanon.application.use_cases.spec_lens import Lens
from cybercanon.domain.annotations import AnnotationKind, ObservationKind

SERVER_NAME = "cybercanon"
STDIO = "stdio"

IN_THREAD = False
"""Tools run on the event loop's own thread.

One agent, one process, one request at a time — the design's explicit non-goal
about concurrency. Answering on the calling thread is what lets the outbound
adapters be ordinary single-threaded objects: SQLite hands out a connection
bound to the thread that opened it, and a worker pool would turn every read into
a cross-thread use of it.
"""

INSTRUCTIONS = """\
CyberCanon — the canon of this game project, local and mostly read-only.

Every tool reads the repository's `asset.yaml` specifications and answers in
prose. Specifications, constraints and rules are changed by people, on
human-facing surfaces: no tool here edits one, and none ever will.

`get_asset_spec` accepts an optional lens — design, art, modeling or code —
which narrows what a response shows and never widens what it may show. A lensed
answer says so and says that the full specification exists.

Two tools record something, and both are proposals rather than edits.
`add_annotation` records an observation — typically that a declared constraint
cannot be met, and why. It changes no constraint: a person promotes it into a
rule or resolves it as an issue, and you can do neither. `report_export`
delivers a validation verdict that was produced locally; the verdict stands
whether or not the report is delivered. Both need a signed-in person
(`canon auth login`) and an agent identifier in this server's launch
configuration; without either, every read still works.
"""

READ_TOOL_NAMES: tuple[str, ...] = (
    "where_is",
    "list_assets",
    "search_assets",
    "get_asset_spec",
    "get_constraints",
    "get_open_annotations",
    "diff_spec",
    "validate_export",
)
"""The eight tools that change nothing. Every one of them leaves the tree clean."""

TOOL_NAMES: tuple[str, ...] = (*READ_TOOL_NAMES, *WRITE_TOOL_NAMES)
"""The advertised surface, exactly (D6, D3).

An exact-match test turns "we decided not to expose promotion" into "you must
edit this tuple and explain yourself". `add-mcp-writes` grew it by exactly two
entries — *"the exact-match tool-surface test from the read change grows by
exactly two names, which is the point of it existing"* — and the two halves are
named apart so the number of tools that change recorded state can be asserted on
its own. A third entry in :data:`WRITE_TOOL_NAMES` is a defect rather than an
addition, in this version and in every later one.
"""


@dataclass
class ReadSurface:
    """The container, plus the specifications the index could not read.

    The server indexes once when it starts. That is a maintenance call at a
    moment which is not a read, which is what keeps D8 true — no lookup triggers
    a rebuild — while still letting a listing report a malformed file beside the
    assets it did manage to read.
    """

    container: Container
    unreadable: tuple[UnreadableSpec, ...] = field(default_factory=tuple)

    def refresh(self) -> None:
        """Rebuild the derived index and remember what would not parse.

        A container with no index answers a refusal rather than a report, and
        the server still starts: the index is how lookups are answered, not what
        makes the process viable.
        """
        rebuilt = self.container.rebuild_index()
        self.unreadable = rebuilt.value.unreadable if succeeded(rebuilt) else ()

    def answer[T](self, result: Result[T], render: Callable[[T], str], asset_id: str = "") -> str:
        """One tool's response: what the renderer produced, or why it could not.

        The one place an outcome becomes prose, and there is no `except` in it
        any more — the use case handed back a refusal, so the adapter reads it
        the way it reads a report.
        """
        if succeeded(result):
            return render(result.value)
        return rendering.render_failure(result, self.nearest(asset_id))

    def nearest(self, asset_id: str) -> tuple[str, ...]:
        """The indexed identifiers closest to one nobody recognised.

        An empty tuple when there is no index or nothing close: a suggestion is
        a courtesy on top of a refusal, and a refusal is never worsened by one
        being unavailable.
        """
        if not asset_id:
            return ()
        nearest = self.container.nearest_assets(asset_id)
        return nearest.value if succeeded(nearest) else ()


def build_server(container: Container, *, name: str = SERVER_NAME) -> FastMCP:
    """The server an agent client spawns, wired to one container.

    The container is a parameter for the same reason the command line's is: it
    is what lets every tool be exercised against in-memory fakes with no
    repository on disk, no identity provider and no network.
    """
    surface = ReadSurface(container)
    surface.refresh()
    server: FastMCP = FastMCP(name=name, instructions=INSTRUCTIONS)
    for register in _REGISTRARS:
        register(server, surface)
    return server


def serve(container: Container, *, name: str = SERVER_NAME) -> None:
    """Run the server over standard input and output, and over nothing else."""
    build_server(container, name=name).run(transport=STDIO)


def advertised(server: FastMCP) -> tuple[str, ...]:
    """Every tool this server advertises, sorted — what the D6 test compares."""
    return tuple(sorted(tool.name for tool in asyncio.run(server.list_tools())))


# --------------------------------------------------------------------------
# The tools — arguments in, one container call, prose out
# --------------------------------------------------------------------------


def _lookup_tools(server: FastMCP, surface: ReadSurface) -> None:
    container = surface.container

    @server.tool(run_in_thread=IN_THREAD)
    def where_is(asset_id: str) -> str:
        """Where an asset's directory, source file, export and engine path live."""
        return surface.answer(container.where_is(asset_id), rendering.render_location, asset_id)

    @server.tool(run_in_thread=IN_THREAD)
    def list_assets(
        status: str | None = None,
        owner: str | None = None,
        tag: str | None = None,
    ) -> str:
        """The project's assets as a compact table, filtered by status, owner or tag."""
        return surface.answer(
            container.list_assets(status=status, owner=owner, tag=tag),
            lambda listing: rendering.render_listing(listing, surface.unreadable),
        )

    @server.tool(run_in_thread=IN_THREAD)
    def search_assets(term: str) -> str:
        """Assets matching a term by identifier, name, alias, tag or description."""
        return surface.answer(
            container.search_assets(term),
            lambda found: rendering.render_search(found, surface.nearest(term)),
        )


def _spec_tools(server: FastMCP, surface: ReadSurface) -> None:
    container = surface.container

    @server.tool(run_in_thread=IN_THREAD)
    def get_asset_spec(asset_id: str, lens: str | None = None) -> str:
        """An asset's compiled specification, optionally narrowed to one discipline."""
        return surface.answer(container.asset_spec(asset_id, lens), rendering.render_spec, asset_id)

    @server.tool(run_in_thread=IN_THREAD)
    def get_constraints(asset_id: str) -> str:
        """What an export of this asset must satisfy, including its required sockets."""
        return surface.answer(
            container.asset_spec(asset_id, Lens.MODELING), rendering.render_spec, asset_id
        )

    @server.tool(run_in_thread=IN_THREAD)
    def get_open_annotations(asset_id: str) -> str:
        """The threads still open on an asset. Resolved and promoted ones are absent."""
        return surface.answer(container.open_annotations(asset_id), rendering.render_spec, asset_id)

    @server.tool(run_in_thread=IN_THREAD)
    def diff_spec(asset_id: str, revision: str) -> str:
        """How an asset's specification has changed since a revision."""
        return surface.answer(
            container.diff_spec(asset_id, revision), rendering.render_difference, asset_id
        )


def _validation_tools(server: FastMCP, surface: ReadSurface) -> None:
    container = surface.container

    @server.tool(run_in_thread=IN_THREAD)
    def validate_export(export: str) -> str:
        """Validate an export against its specification — the same check `canon` runs."""
        return surface.answer(container.validate_export(export), rendering.render_validation)


def _write_tools(server: FastMCP, surface: ReadSurface) -> None:
    """The two tools that change recorded state, and there is no third.

    Both are the same three lines every read tool is: arguments in, one
    container call, prose out. Neither takes an actor, an agent or an author —
    the write session the container assembles carries both parties, from the
    credential and from the launch configuration — so there is no signature here
    through which a caller could claim to be somebody.
    """
    container = surface.container

    @server.tool(run_in_thread=IN_THREAD)
    def add_annotation(
        asset: str,
        target: str,
        text: str,
        kind: str = AnnotationKind.TECHNICAL.value,
        observation_kind: str = ObservationKind.UNATTAINABLE_CONSTRAINT.value,
    ) -> str:
        """Record an observation on an asset — for example that a constraint cannot be met.

        `kind` is the discipline speaking (art-direction, technical, design) and
        `observation_kind` is what you found (unattainable_constraint,
        ambiguity, defect). The entry is recorded open, attributed to you and to
        this agent, and left for a person to promote or resolve. It changes no
        constraint, rule, budget, status or owner.
        """
        return surface.answer(
            container.record_observation(
                writes.observation_from(asset, target, text, kind, observation_kind)
            ),
            rendering.render_observation,
            asset,
        )

    @server.tool(run_in_thread=IN_THREAD)
    def report_export(asset: str, path: str, result: str = "") -> str:
        """Report the outcome of validating an export. The verdict is produced locally.

        `result` is your own account of the run and is recorded nowhere: the
        outcome reported is the one this machine's validator produces from the
        file at `path`, which is the same verdict `canon validate` prints. A
        destination that cannot be reached does not change it and does not fail
        this call — the report is kept and delivered later.
        """
        return writes.answer_report(container, container.validate_export(path), path, asset)


_REGISTRARS: Sequence[Callable[[FastMCP, ReadSurface], None]] = (
    _lookup_tools,
    _spec_tools,
    _validation_tools,
    _write_tools,
)


__all__ = [
    "INSTRUCTIONS",
    "READ_TOOL_NAMES",
    "SERVER_NAME",
    "STDIO",
    "TOOL_NAMES",
    "WRITE_TOOL_NAMES",
    "ReadSurface",
    "advertised",
    "build_server",
    "serve",
]
