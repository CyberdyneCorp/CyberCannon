# Spec Delta

## Purpose

The unmapped-person warning is an assertion about the person. It is made only
when the credential supports it, never because the credential is silent.

## ADDED Requirements

### Requirement: An unknown git mapping is not reported as an unmapped one

The application SHALL warn that a person has no mapped git identity only when
their credential states it: it carries the git identity claim and that claim
names nobody. When the credential carries no git identity claim at all, the
application SHALL NOT state that the person is unmapped. It SHALL NOT list
repository actions as unavailable on that basis.

#### Scenario: A credential silent about git identity raises no warning
- **GIVEN** a signed-in person whose credential carries no git identity claim
- **WHEN** they open any screen
- **THEN** the application SHALL NOT state that they have no mapped git identity

#### Scenario: A credential stating no git identity still raises the warning
- **GIVEN** a signed-in person whose credential carries an empty git identity claim
- **WHEN** they open any screen
- **THEN** the application SHALL state that actions writing to the repository are unavailable and why
