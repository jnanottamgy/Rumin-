"""The Scenario Lab (Phase 5): versioned scenarios executed through the model registry.

* ``spec`` — the scenario's content as a typed document, its canonical form and hash;
* ``profiles`` — what each model declares about the scenarios it applies to;
* ``templates`` — reusable starting points built on implemented models;
* ``graph`` — bounded reads of the knowledge graph (exposures, affected entities);
* ``planner`` — which models apply, what they need, and whether the scenario can run;
* ``executor`` — running a plan through the Phase 4 engine, stage by stage;
* ``aggregate`` — the lab's own equations: lines, margins, coverage, months, events;
* ``pathways``, ``explain``, ``comparison``, ``sensitivity`` — reading results;
* ``runner`` — the bounded background worker pool.

Every financial figure is computed here or by the Phase 4 models, never in the browser.
"""

# Recorded with every execution and part of its hashes: bump it when the planning or
# aggregation rules change.
LAB_VERSION = "1.0.0"
