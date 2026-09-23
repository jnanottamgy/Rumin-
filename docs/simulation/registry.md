# Model registry, and adding a model

## Definitions

A model is **code**: a frozen, typed `ModelDefinition` (`app/simulation/definitions.py`),
a cross-field `check` function and a `compute` function, registered together in
`app/simulation/registry.py`. There is no formula language and nothing is ever evaluated
from text.

| Part | Contents |
|---|---|
| Identity | `id` (`^[a-z][a-z0-9_]{2,63}$`), `version` (MAJOR.MINOR.PATCH), `name`, `summary`, `description`, `domain`, `status` (`preview`, `active`, `deprecated`) |
| Inputs | Each: ID, label, category (scenario input, market baseline, company input, assumption, setting), kind (decimal, integer, quantity, currency, graph node), description, unit or unit choices, minimum and maximum (inclusive or exclusive), decimal places, required, default with rationale, the graph variable it changes, the stored series it may come from, its default sensitivity variation |
| Equations | Each: ID, name, formula (for people), output term, input terms (symbol, meaning, unit), explanation, scope (annual, monthly, horizon, steady state), the assumptions and limitations it rests on |
| Outputs | Each: ID, label, unit, `derived` or `simulated`, description, the equation that produces it, whether contributions are attributed to it; also the monthly series |
| Graph | Transmission rules (edge type, source, target, coefficient and lag inputs, form) and supporting relationships (cited, not followed; some required when an entity is chosen) |
| Statements | Assumptions, limitations, validation rules (with severity) and references |
| Presentation hints | The pathway (links between inputs, graph variables and outputs, with their equations), the accounting bridge and its total, the headline outputs, the default sensitivity inputs and metric |
| Limits | Time step (month), maximum horizon, maximum propagation depth |

The definition checks itself when it is built: IDs are valid and unique; every rule, bridge
item, headline output, sensitivity default, pathway end, equation reference and statement
reference points to something that exists. An inconsistent definition cannot be
registered.

Its **canonical JSON** (sorted keys, decimals as plain strings) is stored with the first
run of each version, and its SHA-256 is the **definition hash**.

## Versions

- The registry holds any number of versions of a model; the latest runnable one is the
  default, and a request may name a version.
- `deprecated` versions keep their runs readable and explainable, but no longer run.
- **A released version never changes.** The first run stores the definition and its hash;
  a later run whose code no longer matches is refused (409). A test
  (`test_the_released_definition_has_not_changed`) pins every released version's hash, so
  an edit fails CI. Any change — an equation, a default, a range, even a description — is
  a new version.
- The engine has its own version (`ENGINE_VERSION`), included in every inputs hash.

## Adding a model

1. **Choose a narrow question** with data RUMIN holds or the user can supply, and write
   down why ([the airline model's reasoning](airline-fuel-cost.md#why-this-domain)).
2. **Create `app/simulation/models/<model_id>.py`** with:
   - the inputs, each with its category, units, range, decimal places and, for every
     assumption, a neutral default and a written rationale;
   - the equations with their terms and units, citing assumptions and limitations;
   - the outputs (`derived` or `simulated`), the monthly series if any;
   - transmission rules for any shock that should travel through the knowledge graph, and
     supporting relationships to cite;
   - assumptions, limitations, validation rules and references;
   - `check(values) -> list[Issue]` for cross-field rules (errors refuse the run; warnings
     are recorded);
   - `compute(context) -> ModelResult`: exact arithmetic inside `arithmetic()`, every step
     recorded with `context.recorder.record(...)`, graph-carried changes read from
     `context.propagation`, never from the graph directly.
3. **Register it** in `REGISTRY` (`app/simulation/registry.py`) with `status="preview"`.
4. **Test it** like `backend/tests/test_simulation_model.py`: hand-calculated cases with
   round inputs, the invariants of the domain, every validation rule, the bridge, the
   contributions adding up, reproducibility, and its sensitivity defaults. Add its hash to
   `RELEASED` once it is released.
5. **Nothing else changes**: the API, persistence, explanations, sensitivity analysis and
   the Simulation page read the definition. The page's form, pathway, tables and charts
   are built from it (the headline, the baseline-and-scenario table from `baseline_x` /
   `scenario_x` output pairs, the monthly chart from `scenario_x` / `baseline_x` monthly
   series and the bridge total). An example for the page's "Fill a hypothetical example"
   button may be added to `frontend/src/features/simulation/examples.ts`, labelled
   hypothetical.
6. **Document it** in `docs/simulation/` like [the airline model](airline-fuel-cost.md).

## Changing a model

Copy the module (or parameterise it), give it a new version number, register both
versions, and keep the old one registered so that its runs can still be verified. Mark the
old version `deprecated` when it should no longer run.
