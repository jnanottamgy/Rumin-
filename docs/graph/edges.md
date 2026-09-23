# Edge model

An edge is one stated relationship between two nodes. It has a type from the
[relationship dictionary](relationship-types.md), an evidence status, and at least one
evidence record that says why it exists ([provenance](provenance.md)). The graph never
creates an edge because two records merely appear in the same dataset.

## Fields

| Field | Meaning |
|---|---|
| `id` | `e-` + the first 16 hex characters of SHA-256 over *type \| source key \| target key*. The same relationship always has the same ID |
| `type`, `category` | The edge type and its category: `economic` (curated or assumed relationships) or `structural` (classifications and record fields) |
| `source`, `target` | Node keys. For undirected types the smaller key is stored as the source |
| `directed` | Whether the edge has a direction (every type except `competes_with`) |
| `label` | How it reads: "*source* **label** *target*", e.g. "Deltrin Refining **operates in** Refined petroleum products" |
| `description` | One sentence from the source record or the construction rule |
| `evidence_status` | What supports it — see below |
| `is_illustrative` | True when the edge touches a fictional or sample node, or comes from illustrative data |
| `quality_status` | `validated`, or `warning` when a validation rule flagged it |
| `valid_from`, `valid_to` | The validity period, only when a source states one. Never guessed |
| `historical` | True when `valid_to` is before today (computed when served) |
| `qualifiers` | Type-specific statements kept from the source: assumed `polarity`, illustrative `strength`, Phase 1 `evidence_level`, `rationale`, and for series links the `stated_difference` |
| `first_build_id`, `changed_build_id`, `retired_build_id` | Build history, as for nodes |

There is **no confidence score**. A number such as "0.8" would need a defined meaning
and a method to estimate it, and none exists for these records; the evidence status is
the honest summary. Likewise `strength` (weak / moderate / strong) is ordinal and
illustrative — written by a curator, not measured — and the interface says so wherever
it appears.

## Evidence status

| Status | Label | Definition | Edges in the sample graph |
|---|---|---|---|
| `evidence_backed` | Evidence-backed | Stated by a cited external source or standard (a classification, an ISO code, a provider's metadata). RUMIN transcribed it; it did not measure or validate it. | 24 |
| `analyst_created` | Analyst-created | Written by a RUMIN curator, with its reasoning recorded — for example a fictional company's industry, or a series recorded as a related measure of a variable. | 32 |
| `model_assumption` | Model assumption | An assumed economic relationship with a written rationale. It is not an empirical finding and has not been validated. | 41 |
| `unverified` | Unverified | Declared in data supplied to RUMIN (for example a price-file manifest). Recorded as declared; RUMIN could not check it. | 0 |

Each edge type allows only some statuses ([dictionary](relationship-types.md)); a
variable-to-variable `influences` edge, for example, can only be a model assumption. The
status comes from the construction rule, never from the edge's appearance.

Three further properties are kept separate from the status, because they answer
different questions:

- **Illustrative** — is this about the fictional sample network or sample data?
- **Historical** — has its stated validity period ended?
- **Quality** — did a validation rule flag it?

## Direction

Direction follows the edge type's definition ("a company *operates in* an industry", "a
variable *affects the costs of* a company"). The validator rejects an edge that points
the wrong way (`reversed_direction`) or joins kinds its type does not allow
(`endpoint_types_not_allowed`). Traversal can follow edges both ways (the default),
outgoing only or incoming only; undirected edges are followed both ways in every mode.

## Parallel and duplicate edges

Two nodes can be joined by edges of different types (a company can both supply and lend
to another). Two records stating the *same* relationship (same type, source and target)
produce one edge with both records as evidence, and the build notes it
(`duplicate_edge`).

## Example

```
USD/INR exchange rate — affects costs of → Deltrin Refining
id                e-dff724fccf21ee64
category          economic
evidence_status   model_assumption            is_illustrative  true
qualifiers        polarity positive (assumed) · strength strong (illustrative)
                  rationale "Deltrin (fictional) imports crude oil priced in U.S. dollars,
                  so a weaker rupee raises its input costs in rupees."
valid_from/to     not stated
evidence          R01 curated_relationship ← relationships/rel_usd_inr_costs_deltrin
                  (dataset rumin-sample 1.0.0)
```

`GET /api/v1/graph/edges/e-dff724fccf21ee64` returns this with the full evidence record,
the status definition and the caveat: *"An assumed effect, not a measured one: it says
nothing about size or timing, and entities of the same kind can be affected very
differently. A connection is not evidence of causation."*
