# Garmin Health Sync design system

## Direction

`Light Garmin`: a serious private health cockpit with quiet neutral surfaces,
clear data provenance and restrained semantic color. Health signals lead;
controls and explanation remain available without competing for attention.

## Tokens

- UI font: Instrument Sans Variable, locally bundled.
- Numeric font: IBM Plex Mono 400, locally bundled.
- Background: `#F5F7F8`; surface: `#FFFFFF`; ink: `#111820`.
- Navigation: `#0B0F12`; primary action blue: `#006F9E`. Garmin Candy Blue
  `#6DCFF6` is a restrained accent, not a page background or a brand claim.
- Sleep: `#6256B8`; heart: `#1687B7`; stress: `#A65F00`;
  destructive or extreme values: `#B23838`.
- Spacing scale: 4, 8, 12, 16, 24, 32 and 48 pixels.
- Default radius: 16px for panels, 10px for controls.
- Shadows are quiet and optional; dark mode uses borders instead.

## Interaction rules

- Mutating health operations always show preview or confirmation.
- Every remote write ends as verified, conflict, uncertain or error.
- Source and availability are visible next to derived values.
- Charts provide a semantic table fallback and do not depend on color alone.
- Every chart has an explicit unit-aware axis. Incompatible units are separate
  panels; timelines use real timestamps, gaps remain gaps, and one sample is a point.
- Mobile touch targets are at least 44px; motion respects reduced-motion settings.
- Browser storage contains UI preferences only, never health measurements.
