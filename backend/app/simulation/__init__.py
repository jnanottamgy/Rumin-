"""The simulation engine (Phase 4).

Versioned models turn validated inputs into explainable, reproducible outputs. The
modules, in the order a run uses them:

* ``decimal_math`` — the one exact-decimal context every calculation runs in.
* ``units`` — units and currencies, with exact conversion factors.
* ``definitions`` — typed model definitions: inputs, equations, assumptions, rules.
* ``registry`` — which models and versions exist.
* ``models`` — the models themselves (definition + compute function).
* ``validation`` — inputs checked against a definition; stored data resolved.
* ``graph_context`` — the knowledge-graph relationships a model may use, confirmed.
* ``transmission`` — propagation of shocks along accepted relationships (pure).
* ``engine`` — one run: validate, propagate, compute, attribute, hash.
* ``sensitivity`` — one-at-a-time sensitivity analysis.
* ``explain`` — structured explanations of a run.
* ``persistence`` — model versions, runs and analyses in the database (append-only).

Nothing here predicts the future: a run shows what the model's equations give for the
inputs and assumptions it was given, holding everything else constant.
"""
