# Model registry, and adding a model

## Registered models

`REGISTRY` (`app/simulation/registry.py`) holds five models, one of them in two versions.
Every version is `preview`: usable, with equations and assumptions that may still change.

| Model | Version | Name | Changes it takes | Timing | Page |
|---|---|---|---|---|---|
| `airline_fuel_cost` | 1.0.0 | Airline fuel-cost shock | `crude_oil_change`, `jet_fuel_margin_change`, `usd_change` (`percent_change`) | permanent from month 1 | [Airline fuel cost](airline-fuel-cost.md) |
| `airline_fuel_cost` | 1.1.0 | Airline fuel-cost shock | the same | start month and duration | [Version 1.1.0](airline-fuel-cost.md#version-110) |
| `fx_exposure` | 1.0.0 | Foreign-currency revenue and costs | `fx_change` (`percent_change`) | start month and duration | [Foreign-currency revenue and costs](fx-exposure.md) |
| `floating_rate_interest` | 1.0.0 | Floating-rate interest costs | `repo_rate_change`, `us_rate_change` (`percentage_points`) | start month and duration | [Floating-rate interest costs](floating-rate-interest.md) |
| `crude_linked_costs` | 1.0.0 | Crude-oil-linked costs | `crude_oil_change` (`percent_change`) | start month and duration | [Crude-oil-linked costs](crude-linked-costs.md) |
| `gas_linked_costs` | 1.0.0 | Natural-gas-linked costs | `gas_price_change` (`percent_change`) | start month and duration | [Natural-gas-linked costs](gas-linked-costs.md) |

The modules are in `app/simulation/models/`: `airline_fuel_cost.py` (1.0.0),
`airline_fuel_cost_1_1.py` (1.1.0), `fx_exposure.py`, `floating_rate_interest.py`, and
`commodity_linked_costs.py`, which builds both commodity models from one template with
separate definitions and definition hashes. `common.py` defines the inputs and statements
several models share. A request that names no version runs the latest runnable one, so
`airline_fuel_cost` runs 1.1.0 by default; 1.0.0 stays registered so that its runs can
still be verified, and runs when a request names it.

## Definitions

A model is **code**: a frozen, typed `ModelDefinition` (`app/simulation/definitions.py`),
a cross-field `check` function and a `compute` function, registered together in
`app/simulation/registry.py`. There is no formula language and nothing is ever evaluated
from text.

| Part | Contents |
|---|---|
| Identity | `id` (`^[a-z][a-z0-9_]{2,63}$`), `version` (MAJOR.MINOR.PATCH), `name`, `summary`, `description`, `domain`, `status` (`preview`, `active`, `deprecated`) |
| Inputs | Each: ID, label, category (scenario input, market baseline, company input, assumption, setting), kind (decimal, integer, quantity, currency, graph node), description, unit or unit choices, minimum and maximum (inclusive or exclusive), decimal places, required, default with rationale, the graph variable it changes, the stored series it may come from, its default sensitivity variation. A scenario input that changes a graph variable has the unit `percent_change` (a price or an exchange rate) or `percentage_points` (a rate) |
| Equations | Each: ID, name, formula (for people), output term, input terms (symbol, meaning, unit), explanation, scope (annual, monthly, horizon, steady state), the assumptions and limitations it rests on |
| Outputs | Each: ID, label, unit, `derived` or `simulated`, description, the equation that produces it, whether contributions are attributed to it; also the monthly series |
| Graph | Transmission rules (edge type, source, target, coefficient and lag inputs, form) and supporting relationships (cited, not followed; some required when an entity is chosen) |
| Statements | Assumptions, limitations, validation rules (with severity) and references |
| Presentation hints | The pathway (links between inputs, graph variables and outputs, with their equations), the accounting bridge and its total, the headline outputs, the default sensitivity inputs and metric |
| Limits | Time step (month), maximum horizon, maximum propagation depth |
| Timing | `shock_start_input` and `shock_duration_input` (optional, added in Phase 5): the integer settings that time every change of a run. Unset, a run's changes are permanent from month 1 |

The definition checks itself when it is built: IDs are valid and unique; every rule, bridge
item, headline output, sensitivity default, pathway end, equation reference and statement
reference points to something that exists; the timing inputs are integer inputs; a scenario
input that changes a graph variable is in `percent_change` or `percentage_points`; and no
transmission rule starts or ends at a node shocked in percentage points, because
log-linear rules carry percentage changes only. An inconsistent definition cannot be
registered.

Its **canonical JSON** (sorted keys, decimals as plain strings) is stored with the first
run of each version, and its SHA-256 is the **definition hash**. Fields added after the
first release (the two timing fields) are left out of the canonical JSON while unset, so
every definition released before them keeps its hash.

## Versions

- The registry holds any number of versions of a model; the latest runnable one is the
  default, and a request may name a version (`model_version`). For `airline_fuel_cost`
  the default is 1.1.0.
- `deprecated` versions keep their runs readable and explainable, but no longer run.
- **A released version never changes.** The first run stores the definition and its hash;
  a later run whose code no longer matches is refused (409). A test
  (`test_the_released_definition_has_not_changed`) pins every released version's hash (all
  six registered versions), so an edit fails CI. Any change — an equation, a default, a
  range, even a description — is a new version.
- Verification re-executes a stored run with the version it names, so a version stays
  registered for as long as its runs should stay verifiable: `airline_fuel_cost` 1.0.0 is
  kept for this reason.
- The engine has its own version (`ENGINE_VERSION`, still `1.0.0` after Phase 5), included
  in every inputs hash.

## Scenario Lab profiles

The [Scenario Lab](../scenario-lab/README.md) runs several models on one scenario. It needs
three things from a model besides its equations.

**Shared inputs, defined once.** A scenario states each shared figure once and hands the
same value to every model that takes it. These inputs are defined in
`app/simulation/models/common.py` (`SHARED_INPUTS`): `entity`, `reporting_currency`,
`annual_revenue`, `annual_operating_costs`, `fx_rate`, `horizon_months`,
`shock_start_month` and `shock_duration_months`. A test
(`test_every_model_defines_the_shared_inputs_identically`) checks that every model version
that takes one defines it identically: unit, unit choices, kind, category, range, decimal
places, whether it is required, default and graph variable.

**Timing and kinds of change in the definition.** The latest version of every model names
`shock_start_month` and `shock_duration_months` as its timing inputs
(`test_every_model_is_timed_and_labels_each_output` checks it), and each change on a graph
variable states its kind in its unit: `percent_change` or `percentage_points`.

**A scenario profile** (`app/scenario_lab/profiles.py`). It sits beside the definition, not
inside it, so released definition hashes do not change; it has its own hash
(`profile_hash`), which every execution records with the model's version and definition
hash and includes in its inputs hash. It declares:

| Field | Meaning |
|---|---|
| `shocks` | The changes the model responds to: a graph variable, the kind of change (`percent_change`, or `absolute_change` in percentage points) and the model input it goes to. A change of another kind is refused, never converted |
| `lines` | Each output the model contributes to a line (`revenue`, `operating_costs` or `interest_expense`), with an item from a closed list (`ITEMS`), the horizon output, the monthly series and the variables that drive it |
| `exposures` | The relationship types and the variable the knowledge graph must state for the model to apply to a chosen company by default: variable → the company, or variable → an industry the company is in |
| `exposure_required` | `True`: a company whose exposure the graph does not state is outside the model's scope. `False`: the model can still be included by hand, and the result then rests on the user's figures |
| `operating_profit_output` | The model's operating-profit change, which the Lab checks its operating-profit line against; none for a model that does not change operating profit |
| `title`, `covers`, `key_outputs` | How the Lab names and describes the model, and the outputs it shows beside the lines |

`check_profiles` runs when the module is imported. It refuses a profile whose model is not
registered; a change bound to an input that is not a scenario input, is of another kind or
changes another variable; an unknown item; an output or monthly series the model does not
have; or a (line, item) that another profile already claims. Profiles are checked against
the latest runnable version of each model, which is the version the Lab runs.

| Model | Responds to | Lines (item from output) | Exposure the graph must state | Required |
|---|---|---|---|---|
| `airline_fuel_cost` | Brent crude, jet fuel and USD/INR (percent) | operating costs: `jet_fuel` from `fuel_cost_change`; revenue: `fuel_cost_recovery` from `fare_recovery` | jet fuel *affects costs of* | yes |
| `fx_exposure` | USD/INR (percent) | revenue: `usd_revenue` from `revenue_change`; operating costs: `usd_costs` from `cost_change` | USD/INR *affects costs of* or *affects revenue of* | no |
| `floating_rate_interest` | the RBI repo rate and the US effective federal funds rate (percentage points) | interest expense: `repo_linked_interest` from `repo_interest_change` and `us_rate_linked_interest` from `us_interest_change` | either rate *affects financing costs of* | no |
| `crude_linked_costs` | Brent crude (percent) | operating costs: `crude_linked_inputs` from `linked_cost_change`; revenue: `crude_cost_recovery` from `price_recovery` | Brent crude *affects costs of* | no |
| `gas_linked_costs` | Henry Hub natural gas (percent) | operating costs: `gas_linked_inputs` from `linked_cost_change`; revenue: `gas_cost_recovery` from `price_recovery` | Henry Hub natural gas *affects costs of* | no |

Each exposure may be stated for the company itself or for its industry.

**How the Lab's plan uses a profile.** A model that the scenario's changes reach is
included by default when a company is chosen and the graph states its exposure as a
current, validated edge. Without that statement, a model with `exposure_required` does not
apply to the company, and including it by hand blocks the plan (`exposure_required`);
any other model is `available` and can be included by hand, with a warning that the result
rests on the user's figures (`exposure_not_stated`). With no company chosen, a model runs
only when included. The statement decides whether a model applies, never how much. Two
included models may not claim the same item of the same line (`double_counting`), and some
pairs carry a caution when both are included (`CAUTIONS`): the airline model with the
currency model (leave jet fuel out of the US-dollar costs) or with the crude-linked model
(leave jet fuel out of the crude-linked costs), and the currency model with either
commodity model (the small cross effect of the two changes is left out). A registered model
without a profile is not offered by the Lab.

## Adding a model

1. **Choose a narrow question** with data RUMIN holds or the user can supply, and write
   down why ([the airline model's reasoning](airline-fuel-cost.md#why-this-domain)).
2. **Create `app/simulation/models/<model_id>.py`** with:
   - the inputs, each with its category, units, range, decimal places and, for every
     assumption, a neutral default and a written rationale; the shared inputs it needs,
     taken from `models/common.py` rather than redefined;
   - the timing inputs `shock_start_month` and `shock_duration_months`, named in the
     definition's `shock_start_input` and `shock_duration_input`, and each change on a
     graph variable in `percent_change` or `percentage_points`;
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
4. **Test it** like `backend/tests/test_simulation_model.py` and
   `backend/tests/test_simulation_models.py`: hand-calculated cases with round inputs, the
   invariants of the domain, every validation rule, the bridge, the contributions adding
   up, reproducibility, and its sensitivity defaults. Add its hash to `RELEASED` once it is
   released. Add its **verification register** entry to `CHECKS` in
   `app/simulation/verification.py` — the model page's worked example, the bridge, a cause
   and effect for the linearity and direction checks, units if it accepts several — so the
   product can show what has been checked
   ([the verification register](verification.md)); `test_every_registered_model_has_checks`
   fails until it exists.
5. **Give it a scenario profile** in `app/scenario_lab/profiles.py` if the Scenario Lab
   should offer it: the changes it responds to, the lines and items it contributes to
   (adding an item to `ITEMS` if none fits), the exposure that makes it apply and whether
   it is required. The Lab's timeline events are listed per model in `events()` in the
   same module.
6. **Nothing else changes**: the API, persistence, explanations, sensitivity analysis and
   the Simulation page read the definition. The page's form, pathway, tables and charts
   are built from it (the headline, the baseline-and-scenario table from `baseline_x` /
   `scenario_x` output pairs, the monthly chart from `scenario_x` / `baseline_x` monthly
   series and the bridge total). An example for the page's "Fill a hypothetical example"
   button may be added to `frontend/src/features/simulation/examples.ts`, labelled
   hypothetical.
7. **Document it** in `docs/simulation/` like the other model pages
   ([the airline model](airline-fuel-cost.md),
   [foreign-currency revenue and costs](fx-exposure.md)).

## Changing a model

Copy the module (or parameterise it), give it a new version number, register both
versions, and keep the old one registered so that its runs can still be verified. Mark the
old version `deprecated` when it should no longer run.

`airline_fuel_cost` 1.1.0 was made this way: `models/airline_fuel_cost_1_1.py` builds its
definition from 1.0.0's with `dataclasses.replace`: it replaces five equations (E6, E8,
E10, E17, E19), assumption A4, three input descriptions and three output labels with their
descriptions, extends the model's description, adds two inputs, a monthly series and a
validation rule, and brings its own `check` and `compute`. Both versions are registered,
and each version's hash is pinned ([what changed](airline-fuel-cost.md#version-110)).
