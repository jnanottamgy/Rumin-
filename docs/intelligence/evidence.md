# Evidence

Every insight carries an **evidence chain**: the ordered steps that produced it, each with
its basis and references. Its **evidence grade** is the weakest step of that chain. The
grade says what kind of support a statement has. It is not a probability, a confidence
score or a ranking. The code is in `backend/app/intelligence/model.py`.

## References, steps and facts

- A **reference** points at a stored record or a calculation: `dataset`, `series`,
  `observation`, `instrument`, `price_bar`, `graph_build`, `graph_node`, `graph_edge`,
  `scenario`, `execution`, `run`, `sensitivity_analysis`, `template`, `catalogue`,
  `calculation` or `threshold`, with an id and a label.
- A **step** is one link of a chain. It has a basis, a sentence, its references, and, where
  it applies, the exact value and unit it contributes. A relationship step also carries the
  edge's evidence status.
- A **fact** is one supporting value, with its label, exact value, unit, basis, references
  and period.

| Basis | What the step is | Grade it gives |
|---|---|---|
| `observation` | a stored value (the current revision) or a stored revision | observed |
| `calculation` | an exact calculation on the steps before it (a change, a slope, a share) | observed |
| `record` | one of RUMIN's own records: a graph build, a catalogue count, the changes and models of an execution | observed |
| `relationship` | an edge of the knowledge graph, current and validated in the latest completed build | its evidence status, below |
| `simulation` | a stored model output (an execution, its contributions, a sensitivity analysis) or a preview run on request (S06) | simulated |
| `assumption` | figures the user entered, or how an observed change was applied (S06) | none: listed, never graded |
| `threshold` | the threshold that selected the finding, with its value | none: listed, never graded |

## The six grades

Strongest first. The statements are the ones the API returns (`GET /intelligence/methods`).

| Grade | From | Statement |
|---|---|---|
| **observed** | observations, calculations on them, RUMIN's records | Rests on stored observations, exact calculations on them and RUMIN's own records. |
| **documented** | a relationship with evidence status `evidence_backed` | Rests on relationships stated by a cited external source (evidence-backed); RUMIN transcribed them and did not measure them. |
| **curated** | `analyst_created` | Rests on relationships written by a RUMIN curator with their reasoning recorded; not an external source. |
| **simulated** | a simulation step | Rests on stored model outputs: deterministic results of the stated inputs and assumptions, not forecasts. |
| **assumed** | `model_assumption` | Rests on at least one relationship recorded as a model assumption: an assumed effect with a written rationale, not an empirical finding. |
| **unverified** | `unverified` | Rests on at least one relationship declared in supplied data that RUMIN could not check. |

**Why simulated sits between curated and assumed.** A simulated value is an exact
consequence of stated inputs and assumptions: it is reproducible and checkable, which an
assumed relationship is not. But it describes a hypothetical, which a curated fact about
the world does not. The order ranks the *kind* of support, not how likely the statement is
to be true.

## The weakest-link rule

`evidence_of(chain)` grades every observation, calculation, record, relationship and
simulation step, and takes the weakest. If two steps share the weakest grade, the earlier
one is taken, and its position is returned as `weakest_step`. The interface marks that step
*Sets the grade*. In addition:

- `conditional_on_simulation` is true when any step is a simulation. If the grade is not
  *simulated* itself (for example *assumed*), the statement adds: *"Its figures are
  simulated: they hold only under the scenario's inputs and assumptions."*
- `includes_observations` is true when any step is an observation.
- A chain with no step at all, or with only assumptions and thresholds, raises `ChainError`.
  So does a relationship step without a known evidence status. **An insight cannot be built
  without a chain.**

Example (E01, from the sample): *Aerisca Airways is exposed to Brent crude oil price*

| # | Basis | Step | Grade |
|---|---|---|---|
| 0 | record | Knowledge-graph build #1 | observed |
| 1 | relationship | Brent crude oil price influences Jet fuel price (U.S. Gulf Coast), `model_assumption` | **assumed**, sets the grade |
| 2 | relationship | Jet fuel price (U.S. Gulf Coast) affects costs of Air transport, `model_assumption` | assumed |
| 3 | relationship | Aerisca Airways operates in Air transport, `analyst_created` | curated |

## Invariants, and the tests that hold them

| Invariant | Where it is enforced |
|---|---|
| No insight without a chain; every relationship step has a known evidence status | `InsightDraft.build` → `evidence_of`; `test_an_insight_without_a_chain_cannot_exist` |
| The grade is the weakest step, and `conditional_on_simulation` matches the steps | `test_the_grade_is_the_weakest_step`; `assert_grounded` checks every insight the API returns |
| Every simulated insight says it is not a forecast | `assert_grounded` |
| No statement contains " will ", "caused", "guarantee", "recommend", "should buy" or "should sell" | `assert_grounded` |
| Every record an insight cites exists (edges, executions, runs) | `test_every_insight_rests_on_an_evidence_chain` |
| An insight's id is stable: the same rule, subject and key always give the same id | `insight_id` = `ins-` + the first 16 hex digits of the SHA-256 of rule, subject and key; `test_insight_ids_are_stable_and_chains_hold_each_link_once` |
| A chain holds each link once (a repeated relationship adds nothing) | `InsightDraft.build` removes duplicates in order |
| A finding shared by the workspace and a dossier is identical in both | `test_a_finding_reads_the_same_in_the_workspace_and_the_dossier` |

## What a grade is not

- **Not a probability.** "Observed" means that the statement rests on stored values. It
  does not mean the values are right: the provider can revise them, and D06 reports it
  when it does.
- **Not a measure of size.** An *assumed* exposure can matter more than a *curated* one.
  The graph states that an entity is exposed, never how much.
- **Not a recommendation.** Nothing is ranked by grade. The ledger can be filtered to a
  minimum grade, which hides findings and orders nothing.

On the sample network every exposure relationship is a model assumption, so every finding
that uses one is graded *assumed*. That is the honest grade of the illustrative data, and
the next step these findings suggest is `find_evidence`: look for a cited source before
relying on the relationship.
