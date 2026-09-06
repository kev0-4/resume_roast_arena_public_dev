# Design notes — palette tracking

This project intentionally allows multiple visual "skins" across surfaces while
we're still iterating on frontend design. Don't force these into one palette
without asking — record new ones here instead.

## Palette A — "Ash & Ember"

Used by: the roast card itself (`workers/renderer/pipeline/templates/roast_card.html`),
shipped, not easily changed without re-rendering every existing card.

- `ash-bg` (background) `#F6F1E7`
- `paper` `#F1E9D8`
- `paper-line` `#D8CBAA`
- `ink` (text) `#211C16`
- `smoke` (secondary text) `#8C8474`
- `ember-deep` `#C1121F`
- `ember` `#FF6B35`
- Fonts: Anton (display) + JetBrains Mono (labels/stats)

## Palette B — "Blue & Lime"

Used by: the landing page (`frontend/src/app/page.tsx`), as of the current
reference-driven pass. Source: a reference component the user supplied,
adapted (not copied) — see git history on `frontend/src/app/globals.css`.

- `brand-blue` (background) `#0038FF`
- `brand-blue-deep` (headline drop-shadow) `#001A99`
- `brand-lime` (accent) `#CCFF00`
- `paper` (bottom section cards) `#F8F9FA`
- `smoke` (secondary text) `#6B6B6B`
- `tier-mid` (leaderboard MID stamp badge) `#EF9F27`
- `tier-roasted` (leaderboard ROASTED stamp badge) `#E24B4A`
- background/foreground for bottom section: white / black
- Fonts: same as Palette A (Anton + JetBrains Mono) — only the color palette
  changed, not the typography

Stamp tiers everywhere else in this build (score-banner.tsx, the landing
page's example cards) still use a uniform lime outline regardless of tier —
`tier-mid`/`tier-roasted` are used only by the leaderboard's `StampBadge`
(2026-09-06 redesign, per user reference) so far. Worth unifying later if the
tri-color treatment reads better everywhere, not decided yet.

## Status

These two palettes currently disagree on purpose — not yet resolved, not
currently a problem. Expect 2-3 named variants like this to exist at once
while reference components keep coming in per page/section. When a page's
palette is decided, add it here (name it, list its tokens, say what uses it)
rather than letting it live only in code comments or memory. Revisit
unification (or a deliberate decision to keep several) once more pages exist.
