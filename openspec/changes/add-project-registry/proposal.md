# Proposal

## Why

A deployment serves exactly one game repository. `CANON_REPOSITORY_URL` is one
remote, `CANON_PROJECT` is the identifier it is served as, and both are
environment variables. Adding a second project therefore means asking whoever
holds the deployment credentials to stand up a second deployment — a DevOps
request to begin work on a new game.

That is the wrong shape for the people this product is for. A game designer
starting a project should not be blocked on an infrastructure ticket, and a
studio running four games should not run four deployments to see four canons.

**The code is already multi-project; only the configuration is not.**
`Surface.projects` is a mapping, every `RepositoryHost` operation takes a
project, the notification endpoint carries a project-to-branch map, index rows
and working copies are keyed by project, and `project.md` already specifies "a
persistent working copy **per project**" with "disk **per project**" as an
accepted cost. One wiring function collapses all of it to a single entry read
from the environment.

## What Changes

- A **project registry**: several projects per deployment, each with its own
  repository URL, branch and push credential.
- Projects are **registered through the service** by a person, not set as
  environment variables, and the credential is stored encrypted at rest.
- `CANON_REPOSITORY_URL` becomes a **seed**: when the registry is empty the
  configured repository is registered as the first project, so an existing
  deployment keeps working with no migration and no operator action.
- Registration is **authorized**: ART_DIRECTOR, DESIGNER or a new
  `project_admin` role, **and** membership of the deployment's organisation.
- An **export and import** of the registry, because the registry is the one
  thing a repository cannot rebuild.

## Two decisions this change reverses, deliberately

Both were recorded, both are being dropped **for the registry only**, and the
scope of each reversal matters more than the reversal.

**"Configuration is environment variables, with no file fallback."** Projects
become runtime data. The environment keeps every *deployment* setting — issuer,
audience, database, object store, the encryption key — and stops carrying the
list of repositories.

**"PostgreSQL is a rebuildable cache/index, not a source of truth."** The
registry is authoritative: it is what tells the service which git to read, so
it cannot be derived from git. **Everything inside a project stays git-sourced
and rebuildable** — `asset.yaml`, annotations, concept views, statuses. Dropping
every table other than the registry and rebuilding from the working copies must
still lose no answer, exactly as today. A reader who cites this change to put
asset data in PostgreSQL has misread it.

The cost is real and is accepted rather than hidden: losing the database now
loses the project list and every stored credential, and no repository brings
them back. That is why export/import is part of this change rather than a later
convenience, and why `add-web-backend`'s D9 — notification dismissals as "the
single deliberate exception" — is amended here rather than quietly outgrown.

## Non-goals

- **Not multi-tenancy.** One deployment serves one organisation, with many
  projects inside it. Roles are scoped to the CyberCanon client rather than to
  an organisation, so a `project_admin` holds it in every organisation they
  belong to; single-org is what keeps the membership conjunct exact. Per-org
  administration needs either a client per organisation or a feature
  CyberdyneAuth does not have, and this change does not pretend otherwise.
- **Not a credential manager.** One push credential per project, replaceable,
  never readable back. No rotation schedule, no per-person credentials, no
  fine-grained scopes.
- **Not deleting a project's history.** Removing a project from the registry
  stops the service serving it; it does not touch the repository, and the
  working copy is reclaimed rather than erased as a statement.
- **Not changing how a project is read or written** once registered. The
  working copy, the pinned-revision reads, the direct-commit write-back and the
  actor mapping are untouched.

## Roadmap position

**Position 11** in `project.md`'s table, after `add-coolify-deployment`: it
changes how a deployment is configured, so it follows the change that decided
how a deployment is built. It comes now because the first hosted deployment made the limitation concrete:
adding a second game to CyberCanon currently requires a person with Coolify
access and a redeploy. Everything else about the hosted surface works.
