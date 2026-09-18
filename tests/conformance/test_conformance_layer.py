"""Task 1.1 — the port-conformance layer exists and is selectable.

The suites themselves belong to task 5.1: one parametrised suite per port, run
against the in-memory fake *and* every real adapter. What this asserts is the
harness contract they will rely on — a test filed here is a conformance test,
because the layer is the directory and nothing else.
"""

from __future__ import annotations

import pytest


def test_the_harness_marks_this_layer(request: pytest.FixtureRequest) -> None:
    assert request.node.get_closest_marker("conformance") is not None
