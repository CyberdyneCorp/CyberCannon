"""The `canon` binary — build the container, run the app, and nothing else.

D11 in three lines: the composition root builds the adapters, the inbound CLI
translates arguments, and this module is only the process entry point. It is
deliberately the one place that knows a working directory exists.

`canon` runs as the installed console script and as ``python -m cybercanon.cli``,
which is what the subprocess tests use and what a hook falls back to on a machine
where the package is on the path but nothing was installed. Both reach this
function, so the two ways of starting the tool cannot diverge.

The exit code is click's to set, from the single seam in
:mod:`cybercanon.adapters.inbound.cli.app`: this function raises `SystemExit`
rather than returning one, and adds no code of its own.
"""

from __future__ import annotations

from pathlib import Path

from cybercanon.adapters.inbound.cli.app import build_app
from cybercanon.adapters.wiring.build import build_container


def main(argv: list[str] | None = None) -> None:
    """Run `canon` over the repository the current working directory belongs to."""
    build_app(build_container(Path.cwd()))(args=argv)


if __name__ == "__main__":  # pragma: no cover — exercised as a subprocess
    main()
