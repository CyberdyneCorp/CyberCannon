# Proposal

## Why

The hosted asset viewer uses only a narrow strip of a desktop screen. A fixed-width canvas and vertically stacked tools make artists scroll past large unused areas before reaching parts, animation, and discussions.

## What Changes

- Let the model viewport fill the available main column on wide screens.
- Place parts and animation beside the viewport and keep annotation discussions in a readable two-column area.
- Reduce spacing in the asset heading, surface tabs, and overview, while retaining the current visual language and content order.
- Collapse to one column on narrower screens without hiding controls or data.

## Capabilities

### New Capabilities

- `asset-workspace-layout`: Responsive, space-efficient presentation of asset surfaces.

### Modified Capabilities

None. Existing asset and viewer behavior remains as specified.

## Impact

Web asset page and viewer layout, scoped CSS, browser layout coverage, and roadmap documentation. No API or data changes.
