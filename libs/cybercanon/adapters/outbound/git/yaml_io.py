"""Round-trip YAML — the loader that does not eat the artist's comments (D4).

`asset.yaml` is a human-authored file living in a git diff. A writer that
reorders keys and drops comments produces unreviewable diffs and destroys trust
in the tool on the first write, so the loader chosen here is `ruamel.yaml` in
round-trip mode from the beginning: this change only reads, but annotation
promotion will write, and a reader that throws the comments away before the
writer exists guarantees the rewrite.

The property is mechanical, not aspirational: :func:`dump` of :func:`load` is
byte-for-byte the input, and `tests/unit/test_adapter_yaml_round_trip.py`
asserts it over a commented specification.

Nothing here knows what a specification *is*. Shapes and their meaning are
:mod:`cybercanon.adapters.outbound.git.schema`'s business; this module is the
file format and nothing else.
"""

from __future__ import annotations

import io
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError


class YamlUnreadable(ValueError):
    """The bytes are not YAML, or are YAML that is not a mapping."""


def _reader() -> YAML:
    """A round-trip parser configured to change nothing it was not asked to change.

    `preserve_quotes` keeps `"12"` from becoming `12`, and the width is set
    high enough that no long line is re-wrapped on the way out — both are ways a
    dump can differ from its source while parsing identically, and both would
    show up as noise in a review.
    """
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def load(text: str) -> Any:
    """Parse YAML, keeping comments, key order and quoting for the eventual write."""
    try:
        return _reader().load(text)
    except YAMLError as error:
        raise YamlUnreadable(str(error)) from error


def dump(data: Any) -> str:
    """Serialise what :func:`load` returned, preserving everything it carried."""
    stream = io.StringIO()
    _reader().dump(data, stream)
    return stream.getvalue()


def load_mapping(text: str, *, subject: str) -> dict[str, Any]:
    """Parse and insist on a mapping, because every spec file is one.

    An empty file yields an empty mapping rather than an error: a file with
    nothing in it is a specification that declares nothing, which the schema
    then reports field by field.
    """
    document = load(text)
    if document is None:
        return {}
    if not isinstance(document, dict):
        raise YamlUnreadable(f"{subject} is not a mapping; a specification file declares fields")
    return dict(document)


__all__ = ["YamlUnreadable", "dump", "load", "load_mapping"]
