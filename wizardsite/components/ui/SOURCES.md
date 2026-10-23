# Reused sidebar components

Selected from the shadcn Sidebar listing on 21st.dev:
https://21st.dev/@shadcn/components/sidebar

The 21st CLI catalog search failed and its registry endpoint returned HTTP 403.
Source was retrieved from the listing's official public upstream registry:
https://ui.shadcn.com/r/styles/new-york/sidebar.json

Reused components: sidebar, button, separator, sheet, tooltip, input, skeleton,
and hooks/use-mobile.tsx. Each file includes its exact registry source URL.
MIT license: SHADCN-LICENSE.txt.

Local adaptations: React 18 ref prop types, Tailwind 4 CSS variable syntax,
and the existing Wizard ice tokens. Wizard account and navigation integration
is project-specific; no placeholder accounts, usage, or investigation data.


## App1 dashboard
The App1 layout and shadcn dependency code were supplied by the user from the
21st.dev shadcnstore App Dashboard Layout. The cards, chart, progress, activity
and sidebar composition are retained; all metrics use saved Wizard results.
No demo projects, team members, notifications or profile photos are presented
as real account data. Missing helper files connect the supplied layout to Wizard.

## Sankey
Bklit MIT chart root/context fetched from https://ui.bklit.com/r/sankey-chart.json.
The named-shape node renderer and relationship interaction adapt the supplied
Sankey composition for software components instead of traffic bars. Source/target
ports reference canonical component IDs to preserve cyclic relationships.
