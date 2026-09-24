# Annotation authoring

## ADDED Requirements

### Requirement: Contextual annotation composer

The shared composer SHALL identify the image view or model part receiving a new annotation, SHALL indicate when the annotation is being saved, and SHALL offer Save only when it has nonempty text and no write is pending.

#### Scenario: 2D placement

- **WHEN** an author places an annotation on an image view
- **THEN** the composer names that view and focuses its text field

#### Scenario: 3D placement

- **WHEN** an author places an annotation on a model part
- **THEN** the composer names that part and focuses its text field

#### Scenario: Save readiness

- **WHEN** a draft has empty text or its write is pending
- **THEN** Save is disabled and the pending write is announced
