# Tasks

## 1. The registry

- [ ] 1.1 `ProjectRegistry` port: list, get, register, amend, remove, with a value object that carries no credential
- [ ] 1.2 `credential_for(project)` as a separate call, so reading settings and presenting a credential are different questions
- [ ] 1.3 `SecretBox` port, an environment-keyed implementation and an in-memory fake, with a conformance suite over both
- [ ] 1.4 PostgreSQL implementation and its migration
- [ ] 1.5 A test asserting the stored credential is not the plaintext, without knowing the algorithm

## 2. Authorization

- [ ] 2.1 `Role.PROJECT_ADMIN`, and `CANON_AUTH_GROUP_ROLES` mapping `project_admin=PROJECT_ADMIN`
- [ ] 2.2 `Operation.REGISTER_PROJECT` in `HUMAN_ONLY`
- [ ] 2.3 The policy function: one of three roles **and** membership of the deployment's organisation
- [ ] 2.4 Tests for each half refusing alone, and for automation refused whatever it holds

## 3. Serving many projects

- [ ] 3.1 Build one `HostedProject` per registry entry in the composition root
- [ ] 3.2 Rebuild that mapping when the registry changes, without interrupting a project already serving
- [ ] 3.3 A newly registered project reports `provisioning` until its clone completes
- [ ] 3.4 Per-project fetch schedules
- [ ] 3.5 Test: registering a second project leaves the first answering throughout

## 4. The seed

- [ ] 4.1 Register the configured repository when the registry is empty
- [ ] 4.2 Test: a deliberately removed project is not restored by a restart

## 5. Export and import

- [ ] 5.1 Export carrying stored ciphertext, requiring no key
- [ ] 5.2 Import restoring projects, and reporting credentials unusable when the key differs
- [ ] 5.3 The HTTP operations, authorized as registration is
- [ ] 5.4 Document the recovery procedure in `deploy/README.md` beside the one for a lost working copy

## 6. The surfaces

- [ ] 6.1 HTTP: list, register, amend, remove, export, import
- [ ] 6.2 Web: a project list, and a registration form for somebody who may
- [ ] 6.3 The project a person is looking at becomes part of the address rather than the deployment
