# Accessibility

A 3D canvas is not accessible by itself, so the universe is built so that **nothing depends
on seeing or pointing at the canvas**.

## The list is the twin

*List* (next to *3D* above the canvas) shows the same nodes and relationships as two tables
— the 2D explorer's `GraphTable`: name, kind, nature, hops from the centre (or position on a
path) and relationships shown, then source, relationship, target and evidence status. Every
row selects the record and opens the same panels as the canvas. The choice is remembered on
the device.

The list is also the **fallback**, with the reason stated above it:

- no WebGL 2 in the browser (checked before Three.js is downloaded);
- a lost graphics context (the browser or the device reclaimed it) — with *Try the 3D view
  again*;
- a renderer that fails to start.

## Keyboard

The canvas is **one tab stop** (`role="application"`, `aria-roledescription="3D knowledge
graph"`), named by what it shows (*3D knowledge graph: 50 nodes · 97 relationships: the whole
build*) and described by *Moving around*. The arrow keys move the selection to the nearest
node on screen in that direction; Enter, E, C, Shift + arrows, + / −, R and Escape are listed
in [interaction](interaction.md). Everything else on the page is ordinary controls.

- **Focus is visible**: a 2 px sky-blue outline drawn inside the canvas's edge. (An inset
  shadow was tried first: it is painted beneath the canvas and was invisible — found in the
  Chromium review.)
- **Focus is kept**: while the next view loads (after Enter or E), the previous view stays
  mounted and the canvas keeps the keyboard focus. (Before this was fixed, focus fell back to
  the page and Escape did nothing.)

## Announcements

- A polite live region announces the selection: *Selected: Trakvel Logistics, company,
  fictional, 5 relationships shown.*
- The status line (polite) says what is shown and when the next view is loading.
- Notices (WebGL unavailable, context lost, build truncated, filters on, a neighbourhood cut
  short, nodes not drawn, overlay states) use `role="status"`; a failed expansion uses
  `role="alert"`, with *Try again*.
- The names written on the canvas are decorative duplicates (`aria-hidden`): every name is in
  the panels and the list.

## Motion

The only motion is the camera's fly-to (480 ms) when the focus changes or the reader asks.
Under reduced motion — the system setting or RUMIN's own preference — the camera jumps.
Measured in Chromium: a fly-to draws 19 frames with motion allowed, and 1 under reduced
motion. Nothing moves by itself.

## Colour, contrast and themes

- No information is carried by hue alone: kind is shape, evidence is a line pattern, nature
  is a halo, emphasis is sky blue **and** weight, and every one of them is in the legend and
  in the panels as text.
- Colours come from the design tokens and follow the light and dark themes (re-read when the
  theme changes).
- Names on the canvas carry a halo in the surface colour so they stay legible over lines.

## Automated checks

`axe-core` 4.13 was run in Chromium (not added to the project) on the universe (light and
dark), an overlay (light and dark), a neighbourhood, a paths view and the list: **no
violations** after one fix — the overlay's results table scrolls sideways in the narrow
panel, and its scrolling region was not reachable from the keyboard (*scrollable region must
be focusable*, serious); it is now a named, focusable region.

## Screens

The side panel sits beside the canvas on wide screens and below it under 64 rem. At 390 px the
page has no horizontal overflow; the canvas stays the default (it was legible in the review),
and the list is one tap away. Strata names are kept inside the canvas on narrow screens.
