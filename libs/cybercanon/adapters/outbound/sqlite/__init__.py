"""Outbound adapters backed by SQLite — the derived index, as one local file.

`SqliteSearchIndex` is the real `SearchIndex` for a local-first surface: the
standard library, a single file under `.canon/`, no server to run and no
credential to be missing. It is deliberately disposable, because the
specification says so — deleting it and rebuilding from the repository is always
a complete recovery.

`PostgresSearchIndex` replaces it behind the same port when a hosted surface
exists (D7). Nothing above the port changes, which is the whole reason the
ranking cascade is a pure function in the port rather than a query each
implementation writes for itself.
"""
