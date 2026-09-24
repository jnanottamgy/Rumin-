"""The intelligence modules: what each asks, reads and computes, and where it stops.

The registry is the contract a new module must meet: an id, the question it answers, the
stores it reads, the method, what it produces and its limitations. The engine runs the
registered modules; ``GET /intelligence/methods`` serves this registry with the signal
definitions, the insight rules, the thresholds and the evidence grades, so every result can be
read against the method that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.intelligence import INTELLIGENCE_VERSION


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    title: str
    question: str
    reads: tuple[str, ...]
    method: str
    produces: tuple[str, ...]
    limitations: tuple[str, ...]
    version: str = INTELLIGENCE_VERSION


MODULES: tuple[ModuleSpec, ...] = (
    ModuleSpec(
        "change_detection",
        "Change detection",
        "What changed in the stored data and in RUMIN's records?",
        (
            "economic_observations",
            "price_bars",
            "graph_edges",
            "graph_builds",
            "scenario_executions",
        ),
        "Changes between consecutive current values (relative for levels, exchange rates and "
        "prices; percentage points for series already in percent), tested against configurable "
        "thresholds; superseded values against their revisions; edges the latest graph build "
        "added, changed or retired; the headline between two executions of a scenario.",
        ("observed changes", "data revisions", "relationship changes", "execution changes"),
        (
            "Only what is stored is analysed: nothing is fetched or filled in.",
            "Observed changes and model interpretations are separate findings.",
        ),
    ),
    ModuleSpec(
        "series_signals",
        "Trend, volatility and unusual change",
        "How has a series behaved over its latest window, against its own history?",
        ("economic_observations", "price_bars"),
        "Least-squares trend with a t test, standard deviation of changes ranked among earlier "
        "windows, modified z-score of the latest change (exact decimals).",
        ("trend", "volatility", "anomaly"),
        ("Descriptive statistics of the stored history; never a forecast.",),
    ),
    ModuleSpec(
        "exposure",
        "Exposure analysis",
        "Which economic variables reach an entity, through which validated relationships?",
        ("graph_edges", "graph_nodes", "economic_series"),
        "Direct, via-industry and upstream (at most two `influences` hops) paths over current, "
        "validated edges of the latest completed build; counterparties and context listed "
        "apart; the models able to simulate each path and the series that measure each "
        "variable.",
        (
            "exposure paths",
            "counterparties",
            "context",
            "series coverage",
            "exposure breadth",
            "dependency",
        ),
        (
            "A stated exposure says that an entity is exposed, never how much.",
            "Every sample relationship is a model assumption; none is evidence-backed.",
        ),
    ),
    ModuleSpec(
        "drivers",
        "Contribution analysis",
        "What drives a simulated result, and what does it rest on?",
        ("scenario_executions", "simulation_runs", "scenario_sensitivity_analyses"),
        "Each line's stored contributions per change (Shapley credits of the model runs), as "
        "amounts, points of the baseline and shares of the change; residual checked; per-unit "
        "effects; stored sensitivity rankings; the runs' assumptions and the user's figures.",
        ("contributions", "scenario sensitivity"),
        (
            "Conditional on the scenario's figures and assumptions: not a forecast.",
            "Ratios (margin, coverage) are not attributed.",
        ),
    ),
    ModuleSpec(
        "interpretation",
        "Observed change through the models",
        "What would the stored scenario's models say about the change just observed?",
        ("economic_observations", "scenario_versions", "model registry"),
        "The latest observed change of a series recorded as a related measure of a scenario "
        "variable, applied alone to the stored scenario version and run as a preview.",
        ("model interpretations",),
        (
            "Computed on request and never stored; the series and the variable differ, as the "
            "curator states.",
        ),
    ),
    ModuleSpec(
        "insights",
        "Insights and briefs",
        "What should a reader know, and what should they look at next?",
        ("all of the above",),
        "Documented rules fill sentence templates with computed values and attach the "
        "evidence chain, facts, assumptions, limitations and rule-based next steps; the "
        "entity brief gathers every finding about one entity as structured facts.",
        ("insights", "entity briefs", "next steps"),
        ("No insight without an evidence chain; no free text is generated.",),
    ),
)
MODULE_BY_ID = {module.id: module for module in MODULES}
