# Design

## What stays in the domain and what belongs to an adapter

The registry is **deployment state, not canon**. Nothing about which
repositories exist belongs in the domain: the domain decides what a
specification means and who may do what to an asset, and it has never known
where a repository lives. So the registry is an outbound port with a stored
implementation, and the only domain-shaped thing this change adds is the
authorization decision, which goes where every other one already is.

## Ports

**`ProjectRegistry` (new, outbound).** `list`, `get`, `register`, `amend`,
`remove`, `export`, `import`. It answers with a value object carrying the
project identifier, repository URL, branch, who registered it and when — and
**never the credential**. A separate `credential_for(project)` exists for the
one caller that needs it, the git adapter, so that "who may read a project's
settings" and "what may present its credential" are different questions with
different answers rather than one object everybody holds.

**`RepositoryHost` (unchanged).** Every method already takes a project. The
hosted implementation stops being constructed around one remote and is
constructed around the registry instead.

**`SecretBox` (new, outbound).** Seal and open bytes with a key the
composition root holds. One implementation over the environment's key, one
in-memory fake for tests. It exists as a port so the domain and application
layers never hold a key, and so a test can assert "the stored form is not the
plaintext" without knowing what algorithm produced it.

## Domain

**`Role.PROJECT_ADMIN` (new member).** The alternative was carrying the raw
role key beside `Actor.roles`, which keeps the enum about what a person may do
to content. It is rejected because it would mean two parallel notions of "what
this person holds", and a policy function reading one while a reviewer reasons
about the other is precisely the class of defect this branch has already fixed
twice. The cost is accepted and stated: `PROJECT_ADMIN` becomes a valid
`default_role` in `.canon/actors.yaml`, and it counts toward the membership
test that admits anyone holding at least one role key on this client — so
granting it alone also grants read. That is the intended reading, and it is
written here rather than discovered.

**`Operation.REGISTER_PROJECT` (new).** In `HUMAN_ONLY`, because registering a
repository supplies the credential the service commits with, and an agent that
could point a deployment at a repository of its choosing is the inversion of
the rule the product is built on. The policy function is
`_role_or_refuse(..., allowed=holds(ART_DIRECTOR) or holds(DESIGNER) or
holds(PROJECT_ADMIN))`, with tenancy checked as it already is for every other
project-scoped decision — except that the subject is the deployment's
organisation rather than a project, because the project does not exist yet.

## The seed, and why it is not a migration

An existing deployment carries `CANON_REPOSITORY_URL`. On start, when the
registry is empty, that repository is registered as a project. A migration that
copied the environment into the database once would do the same thing on the
day it ran and leave a deployment whose environment and registry disagree
afterwards; the seed is idempotent, self-describing, and leaves the variable
meaning exactly what it says — *the repository this deployment serves when it
has been told about no others*.

It fires only on an empty registry. A project removed on purpose must not
return at the next restart, which is the one behaviour a naive "ensure the
configured project exists" would get wrong.

## What the composition root does differently

`hosted.py` builds one `HostedProject` from configuration today. It will build
one per registry entry, and rebuild that mapping when the registry changes.
Each project keeps its own working copy directory — already
`self._root / project` — its own fetch schedule and its own index rows, all of
which are keyed by project already.

The working copy of a newly registered project does not exist yet, which is
what `ProjectState.PROVISIONING` is for. Registration returns immediately and
the clone happens on the background pass, so registering a large repository
does not block a request.

## Rejected alternatives

**Environment carries a list of projects.** Keeps both invariants and needs no
encryption, and was rejected because it does not remove the DevOps request —
which is the entire point. A designer would still wait for somebody with
deployment access.

**Credentials stay in the environment, referenced by alias.** No secret ever
enters the database, and a person can register a project against a credential
an operator already provisioned. Rejected as a half-measure that produces the
worst explanation: a person can add a project but only if somebody else has
already added its credential, which is the original wait with an extra step.

**A credential per person rather than per project.** Rejected: it would make
the commit author and the pushing identity the same, which `D8` deliberately
separates, and it would mean a person's departure silently breaking a
project's write-back.
