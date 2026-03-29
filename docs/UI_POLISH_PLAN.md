# CleoClaw Deep UI Polish Plan

This plan drives EPIC `T030` (Deep dashboard UI polish and visual system).

## Visual Language Baseline (from jontsai command-center)

- Dark-first palette: `#0d1117` / `#161b22` / `#30363d` / `#c9d1d9` / `#58a6ff`
- Tight operator spacing rhythm for high information density
- High-contrast status badges and lightweight card borders
- Icon-forward nav with predictable active states
- Strong chart readability in dark mode

## Borrow Targets from robsannaa mission-control

- Thin-layer operator clarity: direct status and direct action, no hidden state
- Low-friction command surfaces and immediate feedback patterns
- Local-first semantics in language and controls
- Fast glanceability for sessions, health, and costs

## Implementation Waves

1. Tokenized surface system across shell/sidebar/cards/forms
2. Sidebar/nav hierarchy and icon treatment
3. Hero/landing command surface polish
4. Approval/dashboard panel contrast and chart tuning
5. Mobile pass for dropdowns, panels, and touch targets

## Acceptance Criteria

- No hardcoded light-only surfaces remain in primary flows
- Profile dropdown, approvals, dashboard, settings, organization use the same dark tokens
- Status chips, card borders, chart lines remain readable at a glance
- Visual drift between pages is eliminated
- Mobile widths (320/375/768) preserve usability and hierarchy
