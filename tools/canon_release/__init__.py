"""The release ledger: which artifact digest a revision was built as.

`deployment-operations` requires that identity be *"verifiable by a content
digest recorded at build time"*, that promotion preserve it, and that a rollback
deploy *"a previously built artifact"* with *"no rebuild required"*. All three
are questions about a record, so the record is a file in the repository and the
answers are the functions in :mod:`canon_release.digests`.
"""

from canon_release.digests import (
    Build,
    Ledger,
    Promotion,
    Rollback,
    promotion,
    rollback,
)

__all__ = ["Build", "Ledger", "Promotion", "Rollback", "promotion", "rollback"]
