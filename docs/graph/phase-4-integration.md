# Phase 4 integration

How the simulation engine (Phase 4) may use the knowledge graph, and what it must not
assume. This page was written in Phase 3, before the engine existed, as a proposal. **Phase
4 implemented it**: see [how Phase 4 followed it](#how-phase-4-followed-it), and for the
engine's side, [graph integration](../simulation/graph-integration.md).

## Graph edges are not equations

An edge says that a source **states** a relationship: its type, direction, evidence
status and provenance. It gives a simulation none of what an equation needs:

| A simulation needs | Does an edge provide it? |
|---|---|
| Which entities exist and how records identify them | **Yes.** Nodes, keys and identifiers |
| Which relationships are stated, in which direction | **Yes.** Edge type, source and target |
| How well supported each relationship is | **Yes, as a label.** The evidence status, never a probability |
| Where each statement came from | **Yes.** Evidence records, datasets and versions |
| When a relationship applies | **Only if a source states it.** `valid_from` / `valid_to`; none in the sample |
| The sign of an effect | **Only as an assumption.** `qualifiers.polarity`, labelled "assumed" |
| The size of an effect (elasticity, pass-through, share) | **No.** Nothing is measured. `strength` is an illustrative ordinal label |
| Timing (lags) and functional form | **No** |
| Uncertainty (ranges, distributions) | **No** |

So the simulation must define, parameterise and validate **every relationship it
simulates** in its own model. It can cite the graph edge that motivated a relationship,
but the edge does not stand in for the model.

## The interface

`app/graph/store.py` provides `GraphReader`, the read interface the API already uses.
Nodes, edges and evidence come back as frozen, typed records, never ORM objects, and
retired rows are excluded.

| Method | Returns |
|---|---|
| `latest_build()` | The latest completed build's row (`GraphBuild`): its ID, status, source fingerprint, the datasets and versions it read, and its metrics |
| `node(key)`, `nodes(keys)` | `NodeRecord`: type, name, subtitle, nature, quality status, degree, component, attributes, sources, build IDs |
| `edge(key)`, `edges(keys)` | `EdgeRecord`: type, category, source, target, direction, evidence status, illustrative flag, quality status, validity period, qualifiers (`attributes`), build IDs. `is_historical(on)` says whether its stated validity ended before a date |
| `evidence(edge_keys)` | `EvidenceRecord`s: rule, source kind, source table and record, dataset and version, statement, transformation, derivation, citation, retrieval and recording times |
| `identifiers(key)` | (scheme, value, stating record) for a node |
| `subgraph(keys)` | Every current edge whose two ends are both in `keys` |
| `neighborhood(center, depth=, max_nodes=, edge_filter=)` | `Subgraph`: nodes, edges, hop distances, what the node budget left out, and queries used |
| `paths(source, target, max_depth=, limit=, edge_filter=, max_nodes=)` | `PathsResult`: shortest paths in hops, with their nodes and edges |
| `exposures(key)` | For a company or industry: the variables linked to it by assumed-effect edges, direct or via its industry, each with its edge |

Traversals take an `EdgeFilter` (`app/graph/algorithms.py`): edge types, direction,
node types, evidence statuses and whether to include illustrative data. Keys are
deterministic: a scenario shock on the economic variable `var_brent_crude` corresponds
to the node `node_key(GraphNodeType.ECONOMIC_VARIABLE, "var_brent_crude")`, which is
`variable:var_brent_crude` (`app/graph/drafts.py`).

## A suggested way to use it

This is a proposal for Phase 4, not a design decision:

1. **Pin the build.** Record the graph build ID (and its source fingerprint) with every
   simulation run, so the run can be reproduced and explained. Refuse to run, or warn
   loudly, when the overview reports the graph as **stale**.
2. **Start from the scenario's shocks.** Scenarios already store shocks on economic
   variables (`scenario_shocks.variable_id`). Map each to its variable node.
3. **Find candidate channels, not answers.** Traverse outwards from each shocked variable
   with `direction=out` and only the assumed-effect and `influences` types. Each edge found
   is a *candidate* channel that the model may choose to specify. It is not a result.
4. **Choose by evidence status, explicitly.** Decide which statuses the model accepts,
   and record that choice with the run. Suggested: exclude `unverified`, and label any
   result that depends on a `model_assumption` edge as assumption-driven. Never upgrade a
   status.
5. **Parameterise outside the graph.** Store each simulated relationship's parameters
   (magnitude, unit, lag, functional form, uncertainty, source, validation) in the
   simulation's own tables. Link them to the graph edge ID for provenance. Do not write
   parameters back onto graph edges, and never derive a magnitude from `strength`.
6. **Respect time and fiction.** Use `EdgeRecord.is_historical(on)` for as-of runs.
   Anything touching illustrative edges (the fictional sample network) must be labelled
   illustrative in its results.
7. **Explain every result.** A result should list the relationships it used, each with
   its graph edge, evidence status and the simulation parameters applied.

## What Phase 4 must not do

- Treat an edge, a path or a path's length as a transmission mechanism or its strength.
- Infer a company's exposure from its industry's assumed effects without saying so. The
  graph already separates "direct" from "via its industry" for this reason.
- Put simulation logic in the graph modules, the graph API or the explorer's rendering
  code. The graph stays a read-only, rebuildable projection of the sources.
- Present a simulated outcome as a forecast or as a measured fact.

## How Phase 4 followed it

| Proposal | What the engine does |
|---|---|
| 1. Pin the build | Every run stores a graph snapshot: the build ID, its finish time, source fingerprint and freshness, and each edge it relied on. A stale graph is reported on the run with the build used. Verification re-uses the snapshot, never the current graph |
| 2. Start from the scenario's shocks | Each scenario input of a model names the variable node it changes (Brent crude, jet fuel, the exchange rate). Phase 1 scenario drafts are not connected yet (Phase 5) |
| 3. Candidate channels, not answers | Nothing is discovered by traversal. A model **declares** its transmission rules; only those are followed. The graph's other relationships around the model's variables are listed as "not used by this model" |
| 4. Choose by evidence status, explicitly | A rule is followed only along a current edge that passed the graph's validation (a flagged edge is refused). The one rule, T1, follows an `influences` edge, which the graph records only as a model assumption, so every run that depends on it carries the warning `assumption_based_channel`. No status is upgraded |
| 5. Parameterise outside the graph | The elasticity and the lag are model inputs (assumptions with defaults and rationales) stored with the run. Nothing is written back to the graph, and `strength` is never read |
| 6. Respect time and fiction | Only current edges of the latest completed build are used. Fictional entities and illustrative edges are labelled on every run that uses them |
| 7. Explain every result | The explanation's pathway lists each relationship used with its graph edge, evidence status, coefficient and lag, and links to it in the explorer |

None of the "must not" items above happens: the graph modules, API and explorer are
unchanged apart from being read, an airline's exposure comes from the figures the user
enters (the graph only confirms that the chosen company is in air transport), and every
result is labelled as a calculation, not a forecast.

## What is ready and what is not

| Item | Status |
|---|---|
| Typed read interface (`GraphReader`) with bounded traversals and filters | **Implemented and tested** (used by the API) |
| Deterministic keys linking scenario variables to graph nodes | **Implemented** |
| Build IDs and fingerprints to pin a run to a graph | **Implemented** (stored per build) |
| Evidence status, validity and illustrative flags on every edge | **Implemented** |
| Simulation engine, parameters, runs and results | **Implemented** in Phase 4 ([the engine](../simulation/README.md)) |
| Parameter sources (estimation from Phase 2 series, published studies) and validation method | **Not decided.** Parameters are stated assumptions with defaults; estimation and validation are Phase 9 |
