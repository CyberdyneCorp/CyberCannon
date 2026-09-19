"""The FastMCP stdio server — eight read tools over one container (D1, D6).

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

Failures are answers. A recoverable failure — an unknown identifier, a malformed
specification, a revision the repository cannot reach — comes back as prose
naming the cause and, where one exists, the action that resolves it. Nothing
below raises out of a tool, because an exception would end an agent's session
over a typo.

The transport is standard input and output, and there is no other. The server
never opens a listening port: hosting it would mean CORS, an open socket and a
network threat model, all of which local-first exists to avoid.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from fastmcp import FastMCP

from cybercanon.adapters.inbound.mcp import rendering
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.errors import OperationFailed
from cybercanon.application.use_cases.index_assets import UnreadableSpec
from cybercanon.application.use_cases.spec_lens import Lens

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
CyberCanon — the canon of this game project, read-only and local.

Every tool reads the repository's `asset.yaml` specifications and answers in
prose. Nothing here writes: specifications, annotations and constraints are
changed by people, on human-facing surfaces.

`get_asset_spec` accepts an optional lens — design, art, modeling or code —
which narrows what a response shows and never widens what it may show. A lensed
answer says so and says that the full specification exists.
"""

TOOL_NAMES: tuple[str, ...] = (
    "where_is",
    "list_assets",
    "search_assets",
    "get_asset_spec",
    "get_constraints",
    "get_open_annotations",
    "diff_spec",
    "validate_export",
)
"""The advertised surface, exactly (D6).

An exact-match test turns "we decided not to expose promotion" into "you must
edit this tuple and explain yourself". No entry here mutates repository content,
and until the `mcp-write-surface` capability arrives none may.
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
        """Rebuild the derived index and remember what would not parse."""
        self.unreadable = self.container.rebuild_index().unreadable

    def answer(self, render: Callable[[], str], asset_id: str = "") -> str:
        """One tool's response: what the renderer produced, or why it could not.

        The only `except` in the adapter, and it is deliberately the only one: a
        tool that raised would end the session, and `mcp-server` requires a
        recoverable failure to leave it usable.
        """
        try:
            return render()
        except OperationFailed as failure:
            return rendering.render_failure(failure, self.nearest(asset_id))

    def nearest(self, asset_id: str) -> tuple[str, ...]:
        """The indexed identifiers closest to one nobody recognised."""
        try:
            return self.container.nearest_assets(asset_id) if asset_id else ()
        except OperationFailed:
            return ()


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
        return surface.answer(
            lambda: rendering.render_location(container.where_is(asset_id)), asset_id
        )

    @server.tool(run_in_thread=IN_THREAD)
    def list_assets(
        status: str | None = None,
        owner: str | None = None,
        tag: str | None = None,
    ) -> str:
        """The project's assets as a compact table, filtered by status, owner or tag."""
        return surface.answer(
            lambda: rendering.render_listing(
                container.list_assets(status=status, owner=owner, tag=tag), surface.unreadable
            )
        )

    @server.tool(run_in_thread=IN_THREAD)
    def search_assets(term: str) -> str:
        """Assets matching a term by identifier, name, alias, tag or description."""
        return surface.answer(
            lambda: rendering.render_search(container.search_assets(term), surface.nearest(term))
        )


def _spec_tools(server: FastMCP, surface: ReadSurface) -> None:
    container = surface.container

    @server.tool(run_in_thread=IN_THREAD)
    def get_asset_spec(asset_id: str, lens: str | None = None) -> str:
        """An asset's compiled specification, optionally narrowed to one discipline."""
        return surface.answer(
            lambda: rendering.render_spec(container.asset_spec(asset_id, lens)), asset_id
        )

    @server.tool(run_in_thread=IN_THREAD)
    def get_constraints(asset_id: str) -> str:
        """What an export of this asset must satisfy, including its required sockets."""
        return surface.answer(
            lambda: rendering.render_spec(container.asset_spec(asset_id, Lens.MODELING)), asset_id
        )

    @server.tool(run_in_thread=IN_THREAD)
    def get_open_annotations(asset_id: str) -> str:
        """The threads still open on an asset. Resolved and promoted ones are absent."""
        return surface.answer(
            lambda: rendering.render_spec(container.open_annotations(asset_id)), asset_id
        )

    @server.tool(run_in_thread=IN_THREAD)
    def diff_spec(asset_id: str, revision: str) -> str:
        """How an asset's specification has changed since a revision."""
        return surface.answer(
            lambda: rendering.render_difference(container.diff_spec(asset_id, revision)), asset_id
        )


def _validation_tools(server: FastMCP, surface: ReadSurface) -> None:
    container = surface.container

    @server.tool(run_in_thread=IN_THREAD)
    def validate_export(export: str) -> str:
        """Validate an export against its specification — the same check `canon` runs."""
        return surface.answer(
            lambda: rendering.render_validation(container.validate_export(export))
        )


_REGISTRARS: Sequence[Callable[[FastMCP, ReadSurface], None]] = (
    _lookup_tools,
    _spec_tools,
    _validation_tools,
)


__all__ = [
    "INSTRUCTIONS",
    "SERVER_NAME",
    "STDIO",
    "TOOL_NAMES",
    "ReadSurface",
    "advertised",
    "build_server",
    "serve",
]
