# Garmin Health Sync design system

## Direction

`Calm performance / Atlas`: a serious private health cockpit where recovery is
the first decision, supporting metrics stay quiet, and provenance remains
visible. The interface is inspired by Garmin's restrained blue-on-neutral
palette but never claims affiliation or uses Garmin branding.

## Tokens

- UI font: Instrument Sans Variable, locally bundled.
- Numeric font: IBM Plex Mono 400, locally bundled.
- Background: `#F4F7F9`; surface: `#FFFFFF`; ink: `#101820`.
- Navigation: `#0A0F13`; primary action blue: `#007EAE`. Garmin Candy Blue
  `#6DCFF6` is a restrained accent, not a page background or a brand claim.
- Sleep: `#6256B8`; heart: `#1687B7`; stress: `#A65F00`;
  destructive or extreme values: `#B23838`.
- Spacing scale: 4, 8, 12, 16, 24, 32 and 48 pixels.
- Default radius: 18px for panels, 8px for controls.
- Shadows are quiet and optional; dark mode uses borders instead.

## Interaction rules

- Mutating health operations always show preview or confirmation.
- Every remote write ends as verified, conflict, uncertain or error.
- Source and availability are visible next to derived values.
- Charts provide a semantic table fallback and do not depend on color alone.
- Every chart has an explicit unit-aware axis. Incompatible units are separate
  panels; timelines use real timestamps, gaps remain gaps, and one sample is a point.
- Mobile touch targets are at least 44px; motion respects reduced-motion settings.
- Motion is functional only: press feedback (100ms), sheets/dialogs (200ms),
  no chart draw animations, no animated health values and no transitions for
  repeated keyboard-driven actions.
- Browser storage contains UI preferences only, never health measurements.
