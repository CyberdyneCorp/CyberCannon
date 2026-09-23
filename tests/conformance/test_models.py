"""Task 1.3 — the model contract, against the fakes and against the real adapter.

The real adapter runs over a stub HTTP client rather than over a gateway, which
is deliberate: `llm-integration` requires model-backed features to be *"testable
with no endpoint reachable"*, and a conformance suite that needed one would be a
suite CI never really runs. The suite that *does* need one is opt-in and lives
in `tests/integration/test_model_endpoint.py`.
"""

from __future__ import annotations

from pathlib import Path

from contract import implementation_fixture
from model_contract import FakeModels, ModelContract, RealModels


def fake(directory: Path) -> FakeModels:
    return FakeModels()


def real(directory: Path) -> RealModels:
    return RealModels()


implementation = implementation_fixture(fake=fake, real=real)


class TestModels(ModelContract):
    """The contract, against the in-memory ports and `OpenAICompatibleModels`."""
