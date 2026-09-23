repo: CyberdyneCorp/CyberCannon
branch: main
path: apps/cybercanon/web

## Last sync
date: 2026-09-23T02:52:37Z

### Updated in this project
- Clickable prototype of all routes and route states in the Broadsheet system
- Sample data from examples/ronin (mech_scout)

## Screen map
| Screen | Repo files |
|---|---|
| Sign-in | apps/cybercanon/web/src/routes/sign-in/+page.svelte |
| Project picker | apps/cybercanon/web/src/routes/+page.svelte, lib/components/ProjectBar.svelte |
| Asset browser + states | lib/components/AssetListing.svelte, SemanticResults.svelte, RouteScreen.svelte |
| Asset overview | lib/components/AssetSurface.svelte, AssetOverview.svelte, DocumentLinks.svelte |
| Model sheet / 3D viewer | lib/components/ThreadPanel.svelte, SheetView.svelte, Viewer3D.svelte |
| Triage | lib/components/TriagePass.svelte |
| Session expiry | lib/components/ReauthenticatePrompt.svelte |
