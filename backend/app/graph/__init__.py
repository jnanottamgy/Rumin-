"""The financial knowledge graph (Phase 3).

``python -m app.graph build`` turns the Phase 1 reference data and the Phase 2 series and
instruments into a graph of typed nodes and edges, each edge with its evidence. The
modules, in pipeline order:

* ``sources`` — reads the source tables into plain records (the only database reads).
* ``rules`` — construction rules: which record field states which relationship.
* ``resolution`` — entity resolution: identifiers, merges, name candidates, audit log.
* ``validation`` — the rules every node and edge must pass.
* ``assemble`` — runs rules, resolution and validation into a draft graph (pure).
* ``persist`` — writes a draft into the graph tables: add, change, retire, never delete.
* ``build`` — one build run: record, assemble, persist, report.
* ``algorithms`` — traversal, paths, components, degree (pure, storage-agnostic).
* ``store`` — reads the stored graph for the API and later phases.
"""
