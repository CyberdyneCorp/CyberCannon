# Spec Delta

## Purpose

Generates descriptions, tags and suggested aliases for a concept view and holds
them as clearly-marked proposals in the rebuildable index — improving search
recall for assets nobody has described, without ever becoming the art direction
that people and agents read.

## ADDED Requirements

### Requirement: Generated content is a proposal, never authored content

Generated descriptions, tags and aliases SHALL be stored only in the rebuildable
index. The system SHALL NOT write generated content into a specification file, and
SHALL NOT present it as authored by any person.

#### Scenario: Specification file untouched by generation
- **GIVEN** a clean repository working tree
- **WHEN** metadata is generated for every asset in the project
- **THEN** the working tree SHALL remain clean

#### Scenario: Generated content is labelled
- **WHEN** generated metadata is presented anywhere
- **THEN** it SHALL be identified as generated and not attributed to a person

### Requirement: Generated content never enters the compiled specification

The compiled `art-spec.md` and every lensed specification read SHALL exclude
generated content entirely, in any form, including as a separately labelled
section.

#### Scenario: Compiled output identical with and without generation
- **GIVEN** an asset with generated metadata present in the index
- **WHEN** its specification is compiled
- **THEN** the output SHALL be byte-identical to compiling the same asset with no
  generated metadata present

#### Scenario: Lensed read excludes generated content
- **WHEN** an asset is read under any lens
- **THEN** no generated description, tag or alias SHALL appear

### Requirement: Generation targets images only

The system SHALL generate metadata from an asset's concept views. It SHALL NOT
generate metadata from a mesh, and SHALL NOT render a mesh in order to describe
it. Facts about a mesh SHALL come from mesh inspection.

#### Scenario: Mesh is not described
- **GIVEN** an asset with an exported mesh and no concept view
- **WHEN** metadata generation is requested
- **THEN** the system SHALL report that there is no describable source
- **AND** SHALL NOT render or describe the mesh

### Requirement: Derived rows are keyed by source content

Each derived record SHALL be keyed by the content hash of the image it was
generated from. Regenerating for an unchanged image SHALL be recognised as
unnecessary, and a changed image SHALL produce a distinct record rather than
overwriting the record of the previous image.

#### Scenario: Unchanged image is not regenerated
- **GIVEN** a derived record for an image
- **WHEN** generation is requested again for the same unchanged image
- **THEN** the existing record SHALL be reused and no model call SHALL be made

#### Scenario: Changed image produces a new record
- **GIVEN** a derived record for an image
- **WHEN** the image is replaced with different content and generation is requested
- **THEN** a new record SHALL be created keyed by the new content hash

### Requirement: Provenance is recorded

Every derived record SHALL record the model identifier that produced it, the time
of generation, and the content hash of its source. This provenance SHALL be
retrievable wherever the derived content is presented.

#### Scenario: Provenance retrievable
- **WHEN** a derived record is presented
- **THEN** its model identifier, generation time and source content hash SHALL be
  available

### Requirement: Suggested aliases are the primary output

Generation SHALL produce a set of suggested aliases — short human-usable search
terms for the asset — alongside the description and tags. Suggested aliases SHALL
be normalised to the form aliases take in a specification, and SHALL exclude terms
already present as the asset's identifier, name or existing aliases.

#### Scenario: Existing aliases are not re-suggested
- **GIVEN** an asset already declaring the alias `mech`
- **WHEN** aliases are suggested for it
- **THEN** `mech` SHALL NOT appear among the suggestions

#### Scenario: Suggestions are search-usable
- **WHEN** aliases are suggested
- **THEN** each SHALL be in the same normalised form that a specification's
  aliases take

### Requirement: Suggested aliases do not affect ranked search until accepted

Search ranking SHALL treat accepted aliases and suggested aliases differently: an
accepted alias SHALL rank as specified for aliases, while a suggested alias SHALL
be usable only as a lowest-priority fallback, and any result it produces SHALL be
marked as matched on an unaccepted suggestion.

#### Scenario: Accepted alias outranks a suggestion
- **GIVEN** one asset with an accepted alias matching a term and another with only
  a suggested alias matching it
- **WHEN** that term is searched
- **THEN** the asset with the accepted alias SHALL rank first

#### Scenario: Suggestion match is disclosed
- **WHEN** a result is produced only by a suggested alias
- **THEN** the result SHALL indicate that the match came from an unaccepted
  suggestion

### Requirement: Derived content is disposable

Deleting all derived records SHALL cause no loss of project information, and the
system SHALL continue to operate with search behaving as it did before any
generation occurred.

#### Scenario: Derived records deleted
- **GIVEN** a project with derived records and accepted aliases
- **WHEN** all derived records are deleted
- **THEN** accepted aliases SHALL remain in their specification files
- **AND** search SHALL continue to work

### Requirement: Generation is explicitly requested, never automatic on read

Generation SHALL occur only when explicitly requested by a person or by a
maintenance operation. Reading, listing, searching, validating or compiling SHALL
never trigger a model call.

#### Scenario: Reads never generate
- **GIVEN** an asset with no derived record
- **WHEN** it is read, listed, searched, validated and compiled
- **THEN** no model call SHALL be made

### Requirement: Automated callers cannot trigger generation into the canon

An automated caller SHALL NOT be able to cause generated content to become
accepted content. It MAY be shown existing derived records where its identity
permits.

#### Scenario: Agent cannot accept a suggestion
- **WHEN** an automated caller attempts to accept a suggested alias
- **THEN** the attempt SHALL be refused regardless of the roles it acts under
