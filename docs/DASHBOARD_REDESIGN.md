# Heliox dashboard redesign

The dashboard now uses a dark-default, high-density operations-console visual
language. Shared tokens live in
`apps/app/styles/design-tokens.css`; shared layout, cards, KPI widgets, charts,
and tables consume those variables.

## Visual verification

The repository's original overview reference remains at
`qa-screenshots/01-dashboard-initial-load.png`.

Current browser-verified captures:

- `docs/screenshots/redesign/after-overview.png`
- `docs/screenshots/redesign/after-analytics.png`
- `docs/screenshots/redesign/after-opportunities.png`

The captures use demo mode so chart, metric, status, and dense-data treatments
can be reviewed without external cloud credentials.

## Interaction and accessibility checks

- Dark mode is the default; the header control switches to the light token set.
- The global time-range selector updates the shared dashboard date range.
- Navigation and status information remain accessible through semantic links,
  buttons, headings, tables, and status text.
- Numeric metrics use tabular monospace figures.
- Semantic status colors are reinforced by labels and values, not color alone.
