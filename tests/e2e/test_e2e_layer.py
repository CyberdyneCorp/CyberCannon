"""Task 1.1 — the end-to-end layer exists, is selectable, and is opt-in.

D6 keeps e2e out of `just check`: it needs a compose stack and browsers, and
`just check` is specified as the thing whose green state means a green pipeline,
so it must stay fast enough to run constantly. The e2e suites themselves belong
to tasks 6.1-6.4; this asserts only that the layer is marked, which is what
`just test` uses to exclude it.
"""

from __future__ import annotations

import pytest


def test_the_harness_marks_this_layer(request: pytest.FixtureRequest) -> None:
    assert request.node.get_closest_marker("e2e") is not None
