# Explainability and provenance

A run is stored with everything needed to explain it and to reproduce it. Explanations are
structured data built from what the run stored — never prose generated after the fact, and
never re-derived from current code or data.

## What a run stores

| Stored | Contents |
|---|---|
| Identity | Run ID (UUID), optional label, status (`completed`) |
| Model | Model ID and version, linked to the stored model version (its full definition and definition hash) |
| Inputs | Every input, including those left on their defaults: value, unit and unit label, category, **kind of knowledge** (`scenario_input`, `historical_data`, `user_input`, `assumption`, `setting`), **source** (`user`, `default`, `stored_observation`), default and rationale, and for a stored observation its full provenance |
| Assumptions and limitations | The model's statements, as they were |
| Graph snapshot | The build, its freshness, the relationships confirmed or missing, the entity, the relationships not used ([graph integration](graph-integration.md)) |
| Data snapshot | Each stored observation used: series, period, value as published, quality status, revision, last confirmed, capture and job, dataset version, licence, attribution |
| Steps | Every evaluated equation in order (`simulation_run_steps`): equation ID, label, month, output symbol, exact value and unit, and each input's symbol, value and unit — 99 steps for the airline example's 12-month run under version 1.0.0, 110 under 1.1.0 (which records the exchange rate for each month) |
| Outputs | Every output: value (10 decimal places), unit, `derived` or `simulated` |
| Monthly series | Each month's values of the model's monthly outputs |
| Contributions | Shapley credits of every attributable output across the non-zero changes |
| Bridge | The accounting bridge's steps and total (checked before storage) |
| Transmission | Every propagation path |
| Warnings | The notes raised for this run |
| Reproducibility | Inputs hash, result hash, engine version, random seed (`null`: the calculation is deterministic), start and finish times, duration |

Runs, their steps and sensitivity analyses are **append-only**: the API has no update or
delete for them (405), a sensitivity analysis keeps its run (a foreign key refuses to delete
a run with analyses), a run keeps its model version, and running the same inputs again
creates a new run with identical hashes.

## Hashes

- **Definition hash**: SHA-256 over the model definition's canonical JSON (sorted keys,
  decimals as plain strings). Any change to an equation, input, range, default,
  assumption, limitation or even a description changes it.
- **Inputs hash**: SHA-256 over the model ID, version, definition hash, engine version and
  every input's value, unit and source (with the stored observation's series, period and
  value). Equal numbers written differently (`10`, `10.00`) hash the same. The source is
  part of the hash: typing a default's value and leaving the input on its default give
  different inputs hashes (the run records who chose the value) but the same result hash.
- **Result hash**: SHA-256 over every output, monthly value and contribution, as stored.

Identical inputs give identical hashes on every machine, because the arithmetic is exact
and correctly rounded ([numbers](numbers-and-units.md)).

## Model versions cannot change silently

The first run of a model version stores its definition and definition hash
(`simulation_model_versions`). Every later run compares the code's definition hash with the
stored one; if they differ, the run is refused with **409 Conflict** ("a changed model needs
a new version number"). A test pins the hash of every released version, so a change to a
released definition fails CI until it is released as a new version. Old runs keep their
stored definition, so they stay explainable after the code moves on.

## Verification

`POST /api/v1/simulations/{id}/verify` rebuilds the run's preparation from its stored
snapshot alone — stored values, stored observation, stored graph snapshot, never a fresh
database lookup — executes it again and compares the hashes. It reports whether the run
was reproduced exactly, and separately whether each graph edge the run used is still
current in the latest build. It stores nothing. If the model version is no longer
registered with the same definition, verification says so instead of executing.

## The explanation

`GET /api/v1/simulations/{id}/explanation` returns:

| Part | Contents |
|---|---|
| `equations` | Every equation: formula, terms with meanings and units, explanation, scope, the assumptions and limitations it rests on (with their text), and whether this run used it |
| `steps` | Every calculation step in order |
| `pathway` | The input-to-output pathway: nodes (inputs, graph variables, outputs, each with its value and kind of knowledge) and links (with their equations, and for a transmission rule the graph edge, coefficient and lag used) |
| `contributions` | For every attributable output, each change's credit |
| `bridge` | The accounting bridge |
| `parameters` | Each assumption parameter: value used, default, whether it was changed, and the rationale |
| `assumptions`, `limitations`, `warnings` | As stored |
| `method` | How contributions and rounding work, in one sentence each |

`GET …/provenance` returns the model version and definition hash, the engine version, the
hashes, times, every input with its source, the stored observations used, the graph
snapshot and every transmission path.

## Contributions: Shapley values

When several changes act at once they interact: a weaker rupee makes a crude rise costlier.
Attributing the total by adding changes one after another would credit the interaction to
whichever came last. RUMIN uses **Shapley values**: the model is evaluated with every subset
of the non-zero changes (the others held at zero), and each change is credited with its
average marginal effect over all orders of adding them:

  φᵢ = Σ over S ⊆ F∖{i} of |S|! (n − |S| − 1)! / n! × [v(S ∪ {i}) − v(S)]

The credits add up to the total exactly (within the output rounding), whatever the
interaction, and no order is privileged. With crude +10 % and the dollar +10 % on a
5,000,000-a-month fuel bill, each alone costs 6,000,000 over a year and both together
12,600,000; each is credited 6,300,000. At most six changes are attributed at once
(2⁶ = 64 evaluations).

## Kinds of knowledge

Every value on the page and in the API is labelled with what it is:

| Label | Meaning |
|---|---|
| Scenario change | The change being explored |
| Historical data | A stored observation from a cited source, with its period and licence |
| Your figure | A figure the user entered; RUMIN does not check it |
| Assumption | A model parameter with a stated default and rationale |
| Setting | How the calculation is run (the horizon) |
| Derived | Calculated from the inputs alone; the same with or without the scenario |
| Simulated | Calculated under the scenario: a result of the stated assumptions, not a forecast |

Every run response carries the same one-sentence note: *a deterministic calculation from the
inputs and assumptions shown, holding everything else constant; not a forecast and not
investment advice.*
