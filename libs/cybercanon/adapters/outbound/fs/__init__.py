"""Outbound adapters backed by the local filesystem.

`FsBlobStore` is the one the validator needs now: previews written next to the
working copy, with no service to be down and no credential to be missing.
`MinioBlobStore` joins it when a networked surface exists, implementing the same
port with the same association — asset id *and* source export — so nothing above
the port changes.
"""
