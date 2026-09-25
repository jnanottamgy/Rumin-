# Encoding

The 3D universe uses the knowledge graph's own marks (`features/graph/encoding.ts`, the 2D
explorer's), in three dimensions. Nothing new is encoded, and nothing is encoded twice in a
way that could disagree.

## Height is kind — strata

Each kind of record sits on a horizontal layer, 70 world units apart, labelled at its edge:

| Stratum (top to base) | Kinds |
|---|---|
| **Data** | Data series, instruments, markets (what RUMIN stores or describes values for) |
| **Drivers** | Economic variables |
| **Industries** | Sectors and industries |
| **Companies** | Companies |
| **Places** | Countries and currencies |

The order follows the Phase 1 network's columns (drivers → industries → companies → places)
turned upright, so an assumed effect reads downwards: a variable affects an industry's or a
company's costs. **Height never encodes size, importance, a value or a probability.** Kind
is also given by shape, in every panel and in the list, so position is never the only channel.

Within a stratum, a seeded force layout places connected records near each other. The same
data always gives the same picture; when the view grows (an expansion), records already
placed keep their positions and new ones start beside the record that brought them in.

## Marks

| Channel | Encodes | 3D form |
|---|---|---|
| Shape | Kind | company sphere · industry hollow sphere · sector hexagonal prism · country cube · currency ring with a core · economic variable octahedron · data series capsule · instrument pyramid · market inverted pyramid |
| Fill | Hollow kinds, and series or instruments with no stored values, are outlines | light fill with a dark outline hull |
| Halo | Nature | dashed ring: fictional record · dotted ring: sample data · none: real |
| Line pattern | Evidence status | solid: evidence-backed · dashes: analyst-created · dash-dot: model assumption · dots: unverified |
| Line weight | Category | economic relationships heavier than structural ones |
| Arrowhead | Direction | a cone near the target |
| Sky blue | **Emphasis only** | the selection and what it touches; in an overlay, the modelled pathway |
| Dimming | Set back | everything outside the emphasis, when there is one |

**Size is by kind only.** The 2D explorer also grows a node gently with its number of edges;
in 3D, perspective already changes apparent size, so a second size channel would be
unreadable and is not used. Line patterns are measured in screen pixels, so a dashed line
reads the same near and far.

## Names on the canvas

Names are written in a layer above the canvas (so they stay crisp and use the product's type)
and placed greedily by priority (`labels.ts`):

1. the strata's names, shifted inside the canvas rather than left out;
2. the selection, the node under the pointer, the focus and an overlay's records — these
   **essential** names may sit a line above or below their node, or cover another node, when
   no free place exists;
3. the selection's neighbours;
4. the most connected records — a legibility choice when space runs out, **not** a claim that
   they matter more.

A name starts just beyond its node's edge (its projected radius), on the right if it fits and
on the left otherwise, and is left out if it would overlap another name, cover another node
or leave the canvas. At most 36 node names are written; every name is always readable in the
side panel and the list.

## Colour

Colours are read from the design tokens at run time (`--color-surface`, `--viz-node`,
`--viz-node-hollow`, `--viz-edge-structural`, `--viz-edge-economic`, `--viz-dimmed`,
`--color-accent`, `--color-line`) and read again when the theme changes, so the scene
follows light and dark with the rest of the product. The palette is neutral — bone, charcoal
and greys — with **one** accent, sky blue, used only for emphasis. There is no categorical
colour: kind is shape, evidence is pattern, nature is a halo. That is also why the scene
needs no colour-vision validation beyond contrast: no information is carried by hue alone.

## The legend

*How to read the universe* (under the canvas) lists the strata with their kinds, the shapes
present in the view with their 3D forms, the nature halos, the evidence patterns and the
emphasis rules. *Moving around* lists the pointer and keyboard controls.

## How the `dataviz` skill was applied

The installed `dataviz` skill's procedure was followed for a form that is not a chart:

- **Form**: a network; the job is identity and connection, not magnitude — so no size,
  height or brightness encodes a quantity.
- **Colour by job**: status-free, category-free; one accent for emphasis, never for a series;
  text in ink tokens, never in the accent.
- **Marks**: thin lines (1.4–2 px; at most 4.2 px, for a selected propagated edge), selective direct labels
  with collision management, never a name on every node.
- **Hover layer**: a tooltip on every node and line (name, kind, nature or evidence status).
- **Accessibility**: a legend is always available, identity is never colour alone, and a
  table view (the list) exists.
- **Look at it**: the view was rendered in Chromium at three widths in both themes and fixed
  where names collided, clipped or covered nodes (see the Phase 8 report).
