# Graph integration

The knowledge graph states which relationships RUMIN's sources record; it says nothing
about their size, timing or form ([Phase 3: graph edges are not equations](../graph/phase-4-integration.md#graph-edges-are-not-equations)).
So a simulation may use the graph, but only in a controlled way: **a shock never travels
along an arbitrary graph relationship.**

## The rules

A shock travels along a relationship only when all four hold:

1. **A model rule declares it.** A transmission rule names the edge type, source node and
   target node, and the model parameters that give it a coefficient and a lag. The airline
   model has one: **T1**, Brent crude → *influences* → jet fuel, with coefficient β
   (`crude_pass_through`) and lag L (`crude_pass_through_lag`), in log-linear form.
2. **The latest graph build confirms it** as a current edge whose quality status is
   *validated*. An edge the graph's validation flagged is treated as absent.
3. **The shock needs it.** Rules are checked only along paths from the variables a
   scenario actually changes.
4. **Its size and timing come from the model**, never from the graph: β and L are stated
   assumptions with defaults and rationales. The edge's `strength` label is never read.

If a change needs a rule the graph does not confirm, the run is refused with the reason
(`channel_confirmed`), naming the relationship ("Brent crude oil price — influences → Jet
fuel price", rule T1) and whether the graph is unbuilt or lacks the edge. Changes that act
directly on a variable (the additional jet fuel change, the exchange-rate change) need no
relationship and run without a graph.

When the confirmed edge is recorded as a **model assumption** rather than evidence-backed,
the run carries a note (`assumption_based_channel`): results that depend on it are
assumption-driven. In the sample graph, T1's edge is a model assumption on illustrative
data.

**Supporting relationships** are cited, not followed:

| Rule | Relationship | Role |
|---|---|---|
| S1 | jet fuel → *affects costs of* → air transport | Why the fuel bill belongs in an airline's operating costs |
| S2 | the chosen airline → *in industry* → air transport | Required when an airline is chosen: the entity must be a company in air transport |
| S3 | USD/INR → *affects costs of* → the chosen airline | Cites the currency channel |

Every other relationship around the model's variables (Brent → India CPI, the fed funds
rate → USD/INR, …) is **listed and not used**: the run's graph snapshot records how many
there were and the first 30, so it is visible that a graph connection is not a simulation
rule.

## The transmission engine

`app/simulation/transmission.py` is a general, pure propagation engine. A *shock* is a
permanent step change in a node's level, expressed as a log-change, from a given month. A
*link* is a confirmed rule with its coefficient and lag. A shock reaches a node along every
**simple path** of links from the shocked node:

  ℓₙ(m) = Σ over paths p from a shock s to n with startₛ + lagₚ ≤ m of (Π βₑ for e in p) · ℓₛ

so coefficients multiply and lags add along a path, and paths add up at a node. The
shocked node itself is the zero-length path (coefficient 1, lag 0).

| Safeguard | Behaviour |
|---|---|
| Direction | Links are followed from source to target only |
| Cycles | Only simple paths count: a node never appears twice on a path, so a cycle of relationships cannot feed a shock back into itself |
| Depth | At most `max_depth` links per path (4 for the airline model; 6 for any model) |
| Path budget | At most 500 paths per run (5,000 for any use); more raises an error instead of silently dropping paths |
| Order | Links and shocks are sorted first, so the result does not depend on the order they were given in |
| Lags beyond the horizon | The path is still listed (with the month it would start) and counted in the steady state, not in the horizon |

Every path is returned with its contribution — input, nodes, rules, graph edge keys,
coefficient, lag, first month and log-change — and stored with the run, so each number can
be traced back to the change and the relationships that carried it.

## What a run records about the graph

| Field | Meaning |
|---|---|
| `build_id`, `build_finished_at`, `source_fingerprint` | The build the run used, and its sources' fingerprint |
| `freshness` | `current`, `stale` (the sources changed after the build; the run warns) or `not_built` |
| `transmission` | For each rule: the confirmed edge (key, type, ends, evidence status, illustrative flag) or `null` |
| `supporting` | The same for the supporting relationships that apply |
| `entity` | The chosen airline: key, name and nature (real, fictional or sample) |
| `unused`, `unused_total` | Relationships around the model's variables that no rule accepts |
| `names` | The names of every node mentioned, as the build recorded them |

Verification re-executes a run from this snapshot, not from the current graph, and reports
separately whether each edge the run used is still current in the latest build. A graph
rebuild never changes a stored run.

## The graph is not changed

The engine reads the graph through `GraphReader` (Phase 3's typed, read-only interface).
It writes nothing to the graph tables, adds no parameters to edges, and puts no simulation
logic in the graph modules or the graph explorer.
