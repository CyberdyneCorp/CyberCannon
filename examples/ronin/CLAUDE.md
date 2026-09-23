# Agent instructions

## The canon of this project

Every asset in this repository has a **specification** next to it —
`<asset directory>/asset.yaml` — which says what it looks like, what it does and
what it must respect technically. The compiled, readable form is `art-spec.md`
beside it, and the project-wide defaults are in `.canon/project.yaml`.

**Read the specification before changing, exporting or describing an asset.**
It is the contract; the mesh, the engine path and the concept art are what
follow from it.

A CyberCanon MCP server is configured for this repository. Prefer its tools over
searching the tree by hand:

| Question | Tool |
|---|---|
| Where does this asset live? | `where_is` |
| What must an export satisfy? | `get_constraints` |
| What is the whole contract? | `get_asset_spec` (optional `lens`: design, art, modeling, code) |
| Which assets exist? | `list_assets` |
| What is this thing called? | `search_assets` |
| What is still being argued about? | `get_open_annotations` |
| Has the contract moved? | `diff_spec` |
| Does my export pass? | `validate_export` |

Two tools record something, and both are proposals rather than edits:

| Situation | Tool |
|---|---|
| A constraint cannot be met, and you can say why | `add_annotation` |
| You validated an export and the outcome should be reported | `report_export` |

Without the server, `canon check` and `canon validate <export>` answer the
technical half from the command line, and `art-spec.md` beside each `asset.yaml`
is the readable contract.

**Agents read constraints. Agents never write constraints.** If a constraint
looks unattainable, say so with `add_annotation` — do not edit `asset.yaml` so
your output passes. Your observation is recorded open, marked as
agent-authored, and left for a person to promote into a rule or resolve as an
issue; you can do neither, and there is no tool that could.
