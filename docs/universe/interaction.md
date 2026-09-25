# Interaction

## Modes and history

The toolbar switches between **Universe** (the whole build, when it fits the budget),
**Neighbourhood** (a focus and its neighbours; available once a node is focused or
selected) and **Paths**. The exploration state is the 2D explorer's (`useGraphExplorer`):
depth (1–3 hops), the visible-node limit, expansions in order, filters, the selection and
**Back / Forward** over what was on screen. While the next view loads, the previous one stays
on screen and the status line says *Loading the next view*; the canvas keeps the keyboard
focus.

## Camera

| Action | Pointer | Keyboard (canvas focused) |
|---|---|---|
| Turn the view | drag | Shift + arrow keys |
| Move the view | right-drag or Shift + drag | — |
| Zoom | wheel or pinch | + and − |
| Bring a node to the centre | double-click it, or *Centre the view on it* in its panel | Enter (the selection) |
| Frame everything again | *Reset view* | R or Home |

The camera never moves by itself. It moves when the reader asks, and when the focus changes
(a fly-to of 480 ms, eased). *Reset view* and R move the camera only: what was expanded, the
depth and the selection stay as they are, and **Back** returns to earlier views. **Under reduced motion** — the system setting, or RUMIN's own
motion preference in *System* — the camera jumps instead of flying. The first view, and
*Reset view*, fit every node and the strata's rings from the default angle (`frameAll`).

## Selecting and inspecting

- **Hover** a node or a line: a tooltip names it (kind and nature, or the evidence status)
  and its relationships are emphasised.
- **Click** a node or a line to select it; the side panel opens the 2D explorer's **node
  panel** (identifiers, where it comes from, entity resolution, quality checks, relationships
  by type, assumed exposures) or **edge panel** (why the connection exists, the evidence
  records, the rule and dataset, qualifiers, and what the edge does not mean). Missing
  provenance is shown as unavailable, never filled in.
- A node's panel adds: *Centre the view on it*, *Open in the 2D explorer*, *Open in
  Financial Intelligence* (companies and industries), and *Ask the Analyst about it*, which
  opens the Analyst with a drafted question in the box — **never sent** until the reader
  sends it.
- **Click empty space** or press **Escape** to clear the selection.

Picking works in screen space: a node is hit within its drawn radius (at least 12 px), a
line within a few pixels of it; nearer nodes win ties.

## Keyboard

The canvas is one tab stop (`role="application"`, described by *Moving around*). With it
focused:

| Key | Action |
|---|---|
| ← → ↑ ↓ | Select the nearest node **on screen** in that direction |
| Enter | Bring the selection to the centre (in Neighbourhood, focus it) |
| E | Show the selection's neighbours (in Universe or Paths: open its neighbourhood) |
| C | Hide the neighbours an expansion of the selection added |
| Shift + arrows | Turn the view |
| + / − | Zoom |
| R or Home | Reset the view |
| Escape | Clear the selection |

Keys with Ctrl, Alt or Meta are left to the browser. The selection is announced politely
(for example *Selected: Aerisca Airways, company, fictional, 6 relationships shown.*) and is
always also in the side panel as text.

## Search, filters and paths

The 2D explorer's components, unchanged: search by name, code or identifier (in Universe
mode a result already on screen is selected and flown to; otherwise its neighbourhood
opens), filters by node type, evidence status, relationship type, direction and illustrative
relationships, and the path finder. Filters apply to the API requests in Neighbourhood and
Paths, and to the whole build in the browser in Universe mode — with the API's meaning: node
types keep nodes; relationship types, evidence statuses and *Include illustrative* keep
relationships (an illustrative relationship is left out, the records it joins are not);
direction, relative to a focus, does not apply to the whole build.

What the current view leaves out is said above the canvas, as in the 2D explorer: *Filters are
on: 50 of 50 nodes and 32 of 97 relationships shown* (Universe mode); no relationships around
the focus, or none matching the filters; a neighbourhood cut short by the node limit; nodes
not drawn; expansions hidden by the filters; an expansion that failed, with *Try again*.
*Reset filters* sits in the filter bar.

## Links

- **In**: the 2D explorer (*Open in 3D*, keeping focus or path), the Universe page, the
  Scenario Lab (*See it in the 3D universe*, with the execution), the Analyst's paths
  (*Shortest paths between them in 3D*).
- **Out**: the 2D explorer, Financial Intelligence, the Analyst (drafted question), the
  Scenario Lab (an overlay's execution).
