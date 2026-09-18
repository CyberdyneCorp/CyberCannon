# Generated from openspec/changes/add-cyberarche-integration/specs/document-platform/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-cyberarche-integration @capability:document-platform @spec:openspec/changes/add-cyberarche-integration/specs/document-platform/spec.md
Feature: document-platform

  Rule: A linked document is a reference, never a mirror

    Scenario: Only the reference is authored
      Given a document containing several pages of prose
      When it is linked to an asset
      Then the asset's specification file SHALL contain only the reference and its authorship
      And it SHALL NOT contain any of the document's body text

    Scenario: Resolved display data is disposable
      Given an asset with linked documents whose titles have been resolved
      When all rebuildable storage is deleted and rebuilt
      Then the same links SHALL be listed with the same references
      And their titles SHALL be resolved again from the document platform

    Scenario: Editing happens elsewhere
      When a person acts on a linked document from within the system
      Then the only available actions SHALL be opening it at the document platform and removing the link
      And no interface for editing the document's contents SHALL be offered

  Rule: Documents link to an asset or to a project

    Scenario: Asset link is versioned with the asset
      When a person links a document to an asset
      Then the change SHALL appear as a modification to that asset's specification file attributed to that person

    Scenario: Project link is visible from every asset
      Given a document linked at project scope
      When any asset in that project is viewed
      Then that document SHALL be listed as a project-scoped link, distinguished from the asset's own links

    Scenario: Removing a link leaves the document untouched
      When a person removes a document link
      Then the reference SHALL be removed from the specification
      And the document at the document platform SHALL NOT be modified or deleted

  Rule: A link resolves to a readable title and short summary

    Scenario: Link list reads as documents
      Given an asset with two linked documents the viewer may read
      When the viewer lists the asset's links
      Then each SHALL be shown with its current title and summary

    Scenario: Title follows a rename at the source
      Given a linked document whose title was resolved previously
      When the document is renamed at the document platform and the link is viewed again
      Then the newly displayed title SHALL be the current one

    Scenario: Unresolved link is still usable
      Given a reference whose title cannot be resolved
      When the link is displayed
      Then it SHALL be shown with its address and marked as unresolved
      And it SHALL remain openable

  Rule: Unreachable, deleted and forbidden are distinguishable

    Scenario: Service unavailable
      Given the document platform is unreachable
      When an asset with three linked documents is displayed
      Then all three SHALL be listed as temporarily unresolvable
      And the rest of the asset's specification SHALL display normally

    Scenario: Deleted document
      Given a linked document that has been deleted at the document platform
      When the link is displayed
      Then it SHALL be marked as no longer existing
      And the reference SHALL remain in the specification until a person removes it

    Scenario: Viewer not permitted
      Given a linked document the viewer has not been granted access to
      When the link is displayed
      Then it SHALL be marked as not accessible to this viewer
      And no title, summary or other content of that document SHALL be shown

    Scenario: One broken link does not break the list
      Given an asset with one readable link and one forbidden link
      When the asset's links are listed
      Then the readable link SHALL be shown resolved
      And the forbidden link SHALL be shown in its state

  Rule: Listing the documents linked to an asset

    Scenario: Deterministic ordering
      Given an asset with several linked documents
      When its links are listed twice without any change to the specification
      Then both listings SHALL contain the same links in the same order

    Scenario: Scope is visible
      When an asset with both asset-scoped and project-scoped links is listed
      Then each entry SHALL state which scope it came from

  Rule: Creating a pre-titled document for an asset

    Scenario: One action produces a linked document
      Given an asset named `mech_scout`
      When a person creates a design document for it
      Then a document SHALL exist at the document platform whose title identifies that asset
      And the asset's specification SHALL contain a reference to it attributed to that person

    Scenario: Creation refused leaves no link
      Given a person without permission to create documents in the target workspace
      When they attempt to create a design document for an asset
      Then the attempt SHALL be refused with the reason
      And the asset's specification SHALL be unchanged

    Scenario: Link write failure names the created document
      Given a document that was created successfully
      When writing the reference into the specification fails
      Then the failure SHALL be reported
      And the report SHALL name the created document and its address

  Rule: Checkable facts live in the specification, rationale lives in the document

    Scenario: No field is generated from a document
      Given a linked document describing a socket in prose
      When the link is created and the asset is displayed and compiled
      Then no `design` field SHALL have been added or altered
      And validation of an export SHALL be unaffected by that document's contents

    Scenario: Guidance at the point of authoring
      When a person is offered the choice of where to write a statement
      Then the system SHALL state that constraining or checkable statements belong in the specification and that rationale belongs in the document

    Scenario: Document contents are not constraints
      Given a linked document stating a triangle budget in prose
      When an export exceeding that number but within the specification's declared budget is validated
      Then no violation SHALL be reported

  Rule: A compiled specification carries the link, never the document

    Scenario: Compiled output does not vary with platform reachability
      Given an asset carrying document links
      When it is compiled with the platform reachable and again with it unreachable
      Then the two outputs SHALL be byte-identical

    Scenario: Compilation is not blocked by the platform
      Given the document platform is unreachable
      When an asset's specification is compiled
      Then compilation SHALL succeed
      And each document link SHALL appear as its address

    Scenario: No prose is compiled in
      Given a linked document of several thousand words
      When the asset's specification is compiled
      Then the compiled output SHALL grow by at most the link's own line

  Rule: Resolved titles and summaries are display-only cache

    Scenario: Resolved content never reaches authored or compiled artifacts
      Given a resolved title and summary held for a document link
      When the asset's specification file and its compiled briefing are examined
      Then neither SHALL contain the resolved title or summary

  Rule: Validation never contacts the document platform

    Scenario: Offline validation is unaffected
      Given an asset carrying document links and no network access
      When its export is validated
      Then validation SHALL complete
      And its report SHALL be identical to the report produced with the platform reachable

    Scenario: Malformed reference is a specification violation
      When a specification contains a document reference that is not well formed
      Then specification linting SHALL report it
      And the report SHALL name the offending reference

  Rule: The integration degrades to absent

    Scenario: Unconfigured deployment works
      Given no document platform configuration in the environment
      When assets are browsed, specifications compiled and exports validated
      Then all SHALL behave exactly as with the platform configured

    Scenario: Creating a link reports unavailability
      Given no document platform configuration in the environment
      When a person attempts to create a design document for an asset
      Then the feature SHALL report itself unavailable and name the reason
      And no specification SHALL be modified

    Scenario: Existing references survive
      Given an asset carrying document references and no platform configuration
      When the asset's links are listed
      Then each reference SHALL be listed with its address and marked unresolved
