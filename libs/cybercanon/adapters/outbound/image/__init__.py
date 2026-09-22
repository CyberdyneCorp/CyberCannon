"""Image reading and thumbnail derivation — the one place Pillow is imported.

D1 for images, exactly as `mesh/` is D1 for meshes: the library lives here, the
value object crosses the boundary, and the domain decides. Swapping Pillow for
anything else touches these two modules and nothing above them.
"""
