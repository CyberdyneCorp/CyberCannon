# Generated from openspec/changes/add-derived-metadata/specs/derived-metadata/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-derived-metadata @capability:derived-metadata @spec:openspec/changes/add-derived-metadata/specs/derived-metadata/spec.md
Feature: derived-metadata

  Rule: Generated content is a proposal, never authored content

    Scenario: Specification file untouched by generation
      Given a clean repository working tree
      When metadata is generated for every asset in the project
      Then the working tree SHALL remain clean

    Scenario: Generated content is labelled
      When generated metadata is presented anywhere
      Then it SHALL be identified as generated and not attributed to a person

  Rule: Generated content never enters the compiled specification

    Scenario: Compiled output identical with and without generation
      Given an asset with generated metadata present in the index
      When its specification is compiled
      Then the output SHALL be byte-identical to compiling the same asset with no generated metadata present

    Scenario: Lensed read excludes generated content
      When an asset is read under any lens
      Then no generated description, tag or alias SHALL appear

  Rule: Generation targets images only

    Scenario: Mesh is not described
      Given an asset with an exported mesh and no concept view
      When metadata generation is requested
      Then the system SHALL report that there is no describable source
      And SHALL NOT render or describe the mesh

  Rule: Derived rows are keyed by source content

    Scenario: Unchanged image is not regenerated
      Given a derived record for an image
      When generation is requested again for the same unchanged image
      Then the existing record SHALL be reused and no model call SHALL be made

    Scenario: Changed image produces a new record
      Given a derived record for an image
      When the image is replaced with different content and generation is requested
      Then a new record SHALL be created keyed by the new content hash

  Rule: Provenance is recorded

    Scenario: Provenance retrievable
      When a derived record is presented
      Then its model identifier, generation time and source content hash SHALL be available

  Rule: Suggested aliases are the primary output

    Scenario: Existing aliases are not re-suggested
      Given an asset already declaring the alias `mech`
      When aliases are suggested for it
      Then `mech` SHALL NOT appear among the suggestions

    Scenario: Suggestions are search-usable
      When aliases are suggested
      Then each SHALL be in the same normalised form that a specification's aliases take

  Rule: Suggested aliases do not affect ranked search until accepted

    Scenario: Accepted alias outranks a suggestion
      Given one asset with an accepted alias matching a term and another with only a suggested alias matching it
      When that term is searched
      Then the asset with the accepted alias SHALL rank first

    Scenario: Suggestion match is disclosed
      When a result is produced only by a suggested alias
      Then the result SHALL indicate that the match came from an unaccepted suggestion

  Rule: Derived content is disposable

    Scenario: Derived records deleted
      Given a project with derived records and accepted aliases
      When all derived records are deleted
      Then accepted aliases SHALL remain in their specification files
      And search SHALL continue to work

  Rule: Generation is explicitly requested, never automatic on read

    Scenario: Reads never generate
      Given an asset with no derived record
      When it is read, listed, searched, validated and compiled
      Then no model call SHALL be made

  Rule: Automated callers cannot trigger generation into the canon

    Scenario: Agent cannot accept a suggestion
      When an automated caller attempts to accept a suggested alias
      Then the attempt SHALL be refused regardless of the roles it acts under
