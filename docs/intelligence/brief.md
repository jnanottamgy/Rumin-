# The entity brief

The brief is the structured object a future **AI Analyst** (Phase 7) would receive about one
entity: everything Financial Intelligence knows about it, as data with references, with
rules for how it may be put into words. The brief itself contains no generated text. RUMIN
computes every number in it, and a language model may phrase those numbers but never
calculates them.

`GET /api/v1/intelligence/entities/{key}/brief` returns it. The dossier's *Brief* tab shows
it as data, with its narration rules, and can download it as JSON.

## Format `rumin.intelligence.brief/1`

| Field | Contents | Grade |
|---|---|---|
| `format`, `engine_version`, `generated_at` | the format's name and version, the engine's version, when it was generated | |
| `entity`, `build`, `thresholds` | the entity (graph node), the graph build read and its freshness, every threshold used | |
| `observations` | for each related series: the latest change, whether it meets its threshold (and which), the signals (trend, volatility, anomaly) with their values, and the revisions | observed |
| `exposures`, `counterparties`, `context` | the exposure paths with every edge; supply and credit relationships; industry, sector, country, currency, competitors | per edge |
| `relationships` | every edge cited above, once, with its evidence status, caveat, polarity, strength and rationale | per edge |
| `drivers` | the headline, each line's contributions and unattributed amount, the stored sensitivity ranking and the method (*Shapley credits of the stored model runs, per scenario change*) | simulated |
| `simulation_results` | the latest execution, its changes, lines (baseline, change, scenario value, percent), metrics, what is not modelled, unstated exposures and model interpretations | simulated |
| `figures_entered` | the figures the user typed, with units: inputs, not RUMIN data | |
| `assumptions` | the runs' stated assumptions and the insights' assumptions, deduplicated | |
| `evidence` | every insight: id, rule, kind, statement, grade, whether it is conditional on a simulation, facts and chain | per insight |
| `limitations` | every insight's limitations, deduplicated | |
| `next_steps` | the gathered analytical next steps | |
| `narration_rules` | how the brief may be phrased (below) | |

Values are exact decimal strings, as everywhere in the API. The captured example is
`frontend/tests/fixtures/intelligence/brief.json`: Aerisca Airways after the reference
execution, with **hypothetical** figures.

## Narration rules

The brief carries its own rules, so that any consumer receives them with the data:

1. Quote numbers only from the facts, steps and values given here; never compute,
   extrapolate or round them into new figures.
2. Keep each statement's evidence grade beside it, and say "simulated" for every value that
   comes from a model run: such values hold only under the scenario's inputs and assumptions
   and are not forecasts.
3. A relationship in the knowledge graph says that an entity is exposed, never how much; do
   not describe it as a cause or give it a size.
4. Do not add entities, relationships, data or assumptions that are not listed here; say what
   is not known instead.
5. Recommendations are out of scope: next steps are the analytical checks listed here.

A test (`test_the_brief_carries_evidence_and_rules_not_prose`) checks several things: the
format; that `evidence` lists exactly the dossier's insights, in order and each with its
chain; that the simulation results are graded *simulated*; that every edge of every exposure
path is among the relationships; that figures, assumptions and limitations are present; and
that the narration rules are included.

## For Phase 7

The brief is designed so that an AI Analyst can be checked mechanically. Every number in its
answer must appear in the brief, and every sentence must cite an insight id, whose chain
leads to stored records. Phase 7 should add that check before anything is shown. The format
is versioned (`/1`): a change that removes or renames a field needs a new version.
