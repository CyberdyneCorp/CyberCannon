"""Unwrapping a use case's outcome in a test, with the assertion built in (D10).

Every use case now returns one of seven answers rather than raising, so a suite
that is about *what a use case produced* has to get past the wrapper first. Two
helpers, and they are deliberately the only two:

* :func:`ran` — the operation ran; hand me the value. It asserts first, so a
  test that stopped producing a value fails on that rather than on an
  `AttributeError` three lines later, naming the refusal it got instead.
* :func:`refused` — the operation did not run; hand me the refusal. It asserts
  the same thing in the other direction, so a test about a refusal cannot pass
  because the call silently started succeeding.

They live beside the in-memory fakes for the same reason those do: the unit
suite, the BDD steps and the conformance suites all need them, and a copy per
directory is three chances for "ran" to start meaning something slightly
different.
"""

from __future__ import annotations

from cybercanon.application.results import Refusal, Result, succeeded


def ran[T](result: Result[T]) -> T:
    """The value of an outcome that succeeded, or a failure naming the refusal."""
    assert succeeded(result), f"the operation did not run: {result!r}"
    return result.value


def refused[T](result: Result[T]) -> Refusal:
    """The refusal of an outcome that did not run, or a failure saying it did."""
    assert not succeeded(result), f"the operation ran and produced {result!r}"
    return result


__all__ = ["ran", "refused"]
