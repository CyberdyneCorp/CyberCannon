"""`just deploy-check` — is what we deploy what the specification says we deploy?

One command, one exit code. Zero is a conforming declaration; non-zero prints
every non-conforming thing about it, one per line, and is what a release
pipeline stops on.

It reads three things and reaches nothing: the manifest, the settings the
service declares, and the variables the web application reads. The platform is
not consulted on purpose — the question has to stay answerable from a checkout,
including on the day the platform is what is broken.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from canon_deploy.inventory import MANIFEST_PATH, findings, load

CHECK = "check"
NON_CONFORMING = 1

WEB_CONFIG = Path("apps") / "cybercanon" / "web" / "src" / "lib" / "config.ts"
PUBLIC_VARIABLE = re.compile(r"\b(PUBLIC_[A-Z0-9_]+)\b")

CONFORMS = "the declared deployment conforms: four components, and no fifth"


def web_variables(root: Path) -> tuple[str, ...]:
    """What the web application reads, from the one module that reads them."""
    source = (root / WEB_CONFIG).read_text(encoding="utf-8")
    return tuple(sorted(set(PUBLIC_VARIABLE.findall(source))))


def check(root: Path, manifest: Path, out: TextIO) -> int:
    """Every clause of the specification, over the declaration. Exit code included."""
    from cybercanon.adapters.wiring.configuration import OPTIONAL, REQUIRED

    found = findings(
        load(manifest),
        required=REQUIRED,
        optional=OPTIONAL,
        web_required=web_variables(root),
    )
    for line in found:
        print(line, file=out)
    if found:
        return NON_CONFORMING
    print(CONFORMS, file=out)
    return 0


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(prog="canon_deploy", description=__doc__)
    parser.add_argument("command", choices=[CHECK])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, default=None)
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    root = arguments.root
    manifest = arguments.manifest or root / MANIFEST_PATH
    return check(root, manifest, out or sys.stdout)


if __name__ == "__main__":  # pragma: no cover — exercised through main()
    raise SystemExit(main())
