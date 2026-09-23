# Graph concepts, with examples

A short guide to the ideas the knowledge graph uses, each with an example from the
illustrative sample graph (50 nodes, 97 edges). Every company in that graph is
**fictional**; the countries, industries, currencies, variable definitions and series
definitions are real reference data.

## The building blocks

**Node.** One entity RUMIN holds a record for: a country, a currency, an ISIC sector or
industry, a company, an economic variable's definition, a data series, an instrument or
a market. *Example:* `company:co_deltrin_refining` — Deltrin Refining, a fictional
Indian refiner.

**Edge.** One stated relationship between two nodes, of one type, with an evidence
status and at least one evidence record. It reads as a sentence:
*"Deltrin Refining — operates in → Refined petroleum products"* (type `in_industry`,
analyst-created, from Deltrin's company record).

**Direction.** Most edge types have a direction — "Deltrin supplies Aerisca Airways" is
not the same statement as "Aerisca supplies Deltrin". `competes_with` has none: it is
stored once and read both ways.

**Degree.** The number of edges touching a node. India has 19 (its companies, the
variables measured for it, the series covering it and its currency). *Degree measures
how much RUMIN's data says about a node, not how important the node is* — a hub such as
a country is highly connected by construction.

**Neighbourhood.** The nodes within *n* hops of a node, and every edge among them.
Deltrin's 1-hop neighbourhood has 9 nodes and 18 edges; the explorer shows it on a
radial layout, with distance from the centre meaning hops.

**Path.** A chain of edges from one node to another. The shortest path from Aerisca
Airways to the Brent crude oil price has 3 hops:

```
Aerisca Airways  ← supplies —  Deltrin Refining  — operates in →  Refined petroleum products
                                                   ← affects costs of —  Brent crude oil price
```

It shows how *records* are linked. It does **not** say that Brent affects Aerisca
through Deltrin, or that a shorter path is a stronger relationship.

**Connected component.** A set of nodes that can all reach each other along edges
(direction ignored). The sample graph is one component, because countries and currencies
link almost everything. That says nothing about economic integration.

## A connection is not an exposure, a correlation or a cause

These six ideas are easily confused. The graph holds only the first, and labels which
of the last two supports each edge.

| Idea | What it means | In RUMIN | Example |
|---|---|---|---|
| **Graph connection** | Two records are linked by at least one stated relationship, of any type | Every edge | Deltrin — *operates in* → Refined petroleum products |
| **Financial exposure** | A *measured* sensitivity of an entity's finances to something, with a size (e.g. "a 10 % rise in crude raises costs by 4 %") | **Not measured.** The node panel lists variables linked by *assumed-effect* edges, labelled "direct" or "via its industry" — never a size | Brent crude — *affects costs of* → Refined petroleum products (an assumption, no magnitude) |
| **Correlation** | Two measured series moved together over a period; a statistical property of data | **Not computed.** No edge was derived from data | — |
| **Causation** | A change in one thing produces a change in another; needs evidence beyond co-movement | **Never claimed.** "Affects" and "influences" edges are assumptions about direction, not findings | — |
| **Model assumption** | A relationship RUMIN's model *assumes*, with a written rationale; not tested | Evidence status `model_assumption` (41 edges) | Brent crude — *influences* → Jet fuel price, rationale: jet fuel is refined from crude |
| **Evidence-backed relationship** | Stated by a cited external source or standard, and transcribed by RUMIN | Evidence status `evidence_backed` (24 edges) | Refined petroleum products (ISIC division 19) — *belongs to* → Section C, per ISIC Rev. 4 |

Two more statuses complete the picture: **analyst-created** (32 edges — written by a
RUMIN curator, such as a fictional company's industry) and **unverified** (declared by an
importer in a price-file manifest; none in the sample graph).

"Evidence-backed" means *a source states it*, not *it has been validated*: RUMIN
transcribed the classification or code, and did not test it. No edge in the graph is
empirically validated.

### Direct and indirect assumed effects

For a company, the node panel separates:

- **Stated for it (direct)** — an assumed-effect edge whose target is the company itself,
  e.g. *USD/INR exchange rate — affects costs of → Deltrin Refining*.
- **Stated for its industry (indirect)** — an edge whose target is the company's
  industry, e.g. *Brent crude — affects costs of → Refined petroleum products*, shown for
  Deltrin *via* its industry.

An industry-level assumption does **not** mean every company in the industry is
affected, or affected equally. RUMIN never infers a company's suppliers, customers or
lenders from its industry: a `supplies_to` edge exists only where a record states it.

### Illustrative and historical

- **Illustrative** edges touch the fictional sample network or sample data (65 of 97 in
  the sample graph). They demonstrate the model and say nothing about the real world.
  The explorer can hide them ("Include illustrative").
- **Historical** edges have a validity period that has ended. None of the sample
  relationships states a validity period, so none is historical; the explorer says so on
  every edge ("No validity period is stated").
