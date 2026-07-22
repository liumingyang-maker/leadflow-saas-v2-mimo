# Signal Workspace Design System

LeadFlow V2 uses Signal Workspace: a quiet B2B intelligence workspace for lead discovery, review, CRM follow-up, and inbound activity.

## Direction

- Professional, dense, and scannable rather than marketing-heavy.
- No purple AI gradients, decorative blobs, or hover scale everywhere.
- The signature element is a restrained cobalt/cyan signal layer used for actionable state, not decoration.
- Typography uses Inter or system sans with tabular numerals for data.

## Accessibility Contract

- Target WCAG 2.2 AA.
- Visible `focus-visible` treatment on controls and fields.
- Labels for form fields and accessible names for icon or compact buttons.
- State is never communicated by color alone.
- Empty, loading, and error states must be present for core surfaces.

## Motion Contract

- Corporate motion: quick, purposeful, and non-decorative.
- Hover/focus transitions use 120ms; larger state changes use 180ms.
- Use opacity/color/shadow transitions, not layout-shifting motion.
- Respect `prefers-reduced-motion`.

## Audit Contract

Each UI page needs desktop and 375px mobile screenshots, keyboard/focus checks, reduced-motion evidence, empty/loading/error state evidence, and console-clean browser verification.
