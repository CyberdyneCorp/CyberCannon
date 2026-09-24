"""Write a game repository somebody can actually look at.

`examples/ronin` is the worked example, and it is **source only**: an
`asset.yaml`, a compiled `art-spec.md`, a project file. It carries no export
and no concept view, because `tools/canon_fixtures` states the rule this
repository keeps — *"fixtures are built from code at test time and nothing
binary lives in git, which is the right trade for review"*. A `.glb` committed
here would be a blob nobody can review, diff or explain.

That trade is right for the tool's own repository and wrong for a **game**
repository, which is exactly where art belongs. The first hosted deployment
made the difference visible: ronin was seeded from `examples/ronin`, so the
browser correctly reported an asset with no export, no triangles, no clips and
no mirrored views — every one of those an honest answer about a contract with
no art attached to it.

This script closes that gap without breaking the rule. It writes the example's
source files **and** generates the binaries beside them, from the same fixture
code the suites use, into a directory outside this repository. The output is a
complete, validating game repository: `canon validate` passes 15 rules against
it, which is the point — the content is not decorative, it satisfies the
contract the specification states.

    just seed /path/to/game-repo

What it writes, and why each one earns its place:

* `SM_mech_scout_LOD0.glb` — skinned, two clips, the socket the design block
  declares and the material the naming rule expects. `write_skinned_glb` builds
  it, so it carries the same facts the validator's own suites assert against.
* two concept views — so the model sheet has something to pin an annotation to,
  and the mirrored-image path has an image to mirror.

Everything else is copied from `examples/ronin` unchanged, so the example stays
the single description of what an asset's contract looks like.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from canon_fixtures import image, mesh

REPOSITORY = Path(__file__).resolve().parent.parent.parent
"""This repository's root: `tools/canon_fixtures/seed.py` is three levels down."""

EXAMPLE = REPOSITORY / "examples" / "ronin"
ASSET = "characters/mech_scout"
EXPORT = f"{ASSET}/exports/SM_mech_scout_LOD0.glb"
VIEWS: tuple[tuple[str, int], ...] = (
    (f"{ASSET}/concept/mech_scout_front.png", 11),
    (f"{ASSET}/concept/mech_scout_three_quarter.png", 23),
)


def seed(destination: Path) -> list[str]:
    """Write the example and its generated content, answering what it wrote."""
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(EXAMPLE, destination, dirs_exist_ok=True)

    written = []
    export = destination / EXPORT
    export.parent.mkdir(parents=True, exist_ok=True)
    mesh.write_skinned_glb(export)
    written.append(EXPORT)

    for path, seed_value in VIEWS:
        view = destination / path
        view.parent.mkdir(parents=True, exist_ok=True)
        image.write_image(view, seed=seed_value)
        written.append(path)

    return written


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m canon_fixtures.seed <destination>", file=sys.stderr)
        return 2
    destination = Path(argv[1]).expanduser().resolve()
    if destination.is_relative_to(REPOSITORY):
        print(
            "refusing to seed inside this repository: the generated files are "
            "binaries, and nothing binary lives in this git history. Seed a "
            "game repository somewhere else.",
            file=sys.stderr,
        )
        return 2
    for path in seed(destination):
        print(f"wrote {path}")
    print(f"\nseeded {destination}")
    print("verify with: cd <destination> && canon validate " + EXPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
