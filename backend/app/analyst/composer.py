"""The grounded composer: RUMIN's own answer to each kind of question.

For each intent it calls the tools a careful analyst would (through the same registry a
language model uses, so every call is recorded), then writes the answer from what they
returned: short sentences, each citing the evidence it rests on, and the tables, series,
paths and scenario cards the tools rendered. No sentence is generated freely: each is a
template filled with values that are, by construction, in the evidence it cites — and the
grounding check verifies that anyway.

Wording follows the phrasing rules (``policy.FORBIDDEN``): results are "simulated under the
scenario's changes", exposure is "stated", nothing is predicted or advised.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.analyst import policy
from app.analyst.answer import (
    AnswerStatus,
    Block,
    ClarificationBlock,
    ClarificationOption,
    Column,
    NoticeBlock,
    NoticeKind,
    PathsBlock,
    SeriesBlock,
    TableBlock,
    TableRow,
    cite,
    text,
)
from app.analyst.evidence import Knowledge, SourceRef
from app.analyst.router import Route
from app.analyst.tools.registry import ToolCall, ToolRunner
from app.analyst.vocabulary import Term, Vocabulary, example_change, the
from app.intelligence import fmt

MINUS = fmt.MINUS
SEARCH_LIMIT = 20
SEARCH_NOUNS = {
    "company": ("company", "companies"),
    "industry": ("industry", "industries"),
    "variable": ("economic variable", "economic variables"),
    "series": ("stored series", "stored series"),
    "instrument": ("instrument", "instruments"),
}
HOW = {
    "direct": "directly",
    "via_industry": "through its industry",
    "upstream": "upstream, through another variable",
}
LINE_ORDER = (
    "revenue",
    "operating_costs",
    "operating_profit",
    "interest_expense",
    "profit_before_tax",
)


@dataclass
class Draft:
    status: AnswerStatus
    headline: str
    blocks: list[Block] = field(default_factory=list)
    follow_ups: list[str] = field(default_factory=list)
    focus: dict[str, Any] = field(default_factory=dict)


def _d(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except ArithmeticError:
        return None


def money(value: Any, currency: str, *, sign: bool = False) -> str:
    number = _d(value)
    return "—" if number is None else fmt.money(number, currency, sign=sign)


def pct(value: Any, *, sign: bool = True) -> str:
    number = _d(value)
    return "—" if number is None else fmt.percent(number, sign=sign)


def stored(value: Any) -> str:
    number = _d(value)
    return "—" if number is None else fmt.stored(number)


def possessive(name: str) -> str:
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def notice(kind: NoticeKind, title: str, body: str, *citations: str | None) -> NoticeBlock:
    return NoticeBlock(
        kind=kind, title=title, text=body, citations=[item for item in citations if item]
    )


class Composer:
    def __init__(self, route: Route, runner: ToolRunner, vocabulary: Vocabulary) -> None:
        self.route = route
        self.runner = runner
        self.vocabulary = vocabulary
        self.ledger = runner.ledger

    # --- plumbing ------------------------------------------------------------------------------

    def call(self, tool: str, **arguments: Any) -> ToolCall:
        return self.runner.call(tool, {k: v for k, v in arguments.items() if v is not None})

    def question_evidence(self) -> str | None:
        """The figures of the question itself, as read: a person's input, citable."""
        route = self.route
        values: dict[str, Any] = {}
        for change in route.changes:
            values[f"change.{change.variable.record_id}"] = change.value
            for key, value in change.figures.items():
                values[key] = value
        if route.horizon:
            values["horizon_months"] = route.horizon
        for year in route.periods.years:
            values[f"year.{year}"] = year
        if route.periods.last:
            values["last"] = route.periods.last
        for number, value in enumerate(route.untied_values, start=1):
            values[f"figure.{number}"] = value
        if not values:
            return None
        return self.ledger.add(
            tool="question",
            call=0,
            kind=Knowledge.USER_INPUT,
            title="Your question, as read",
            detail=policy.data_text(route.question, 300),
            source=SourceRef(kind="question", id="question", label="This question"),
            retrieved_at=self.runner.clock(),
            values=values,
        )

    def assumptions(self) -> list[Block]:
        if not self.route.assumptions:
            return []
        cited = self.question_evidence()
        return [
            notice(
                "assumption", "How the question was read", " ".join(self.route.assumptions), cited
            )
        ]

    def focus_note(self) -> list[Block]:
        if not self.route.from_focus:
            return []
        names = [term.label for term in self.route.entities[:1]] or [
            term.label for term in self.route.variables[:1]
        ]
        about = f" ({names[0]})" if names else ""
        return [
            notice(
                "assumption",
                "Taken from the conversation",
                f"This follow-up was read as being about the conversation's subject{about}.",
            )
        ]

    def failure(self, call: ToolCall, subject: str) -> Draft:
        status: AnswerStatus = "no_data" if call.status == "not_found" else "failed"
        headline = (
            f"RUMIN holds nothing to answer this about {subject}."
            if status == "no_data"
            else f"The Analyst could not read what it needs about {subject}."
        )
        return Draft(
            status=status,
            headline=headline,
            blocks=[
                notice(
                    "missing_data" if status == "no_data" else "limitation",
                    "What is missing" if status == "no_data" else "What went wrong",
                    call.error or "The tool returned nothing.",
                )
            ],
        )

    # --- dispatch ------------------------------------------------------------------------------

    def compose(self) -> Draft:
        handler = getattr(self, f"_{self.route.intent}", None)
        draft: Draft = handler() if handler is not None else self._unsupported()
        return draft

    # --- policy and conversation ---------------------------------------------------------------

    def _clarify(self) -> Draft:
        found = self.route.clarification
        question = found.question if found else "Which record do you mean?"
        options = [
            ClarificationOption(label=label, question=q)
            for label, q in (found.options if found else [])
        ]
        # A figure repeated from the question ("change by 30%?") is the person's input.
        self.question_evidence()
        return Draft(
            status="clarification",
            headline=question,
            blocks=[ClarificationBlock(question=question, options=options)],
        )

    def _injection(self) -> Draft:
        return Draft(
            status="declined",
            headline="The Analyst answers questions about RUMIN's records only",
            blocks=[text("policy", policy.DECLINED_INJECTION)],
            follow_ups=self.starters(),
        )

    def _secrets(self) -> Draft:
        return Draft(
            status="declined",
            headline="The Analyst has no access to keys, passwords or settings",
            blocks=[text("policy", policy.DECLINED_SECRETS)],
            follow_ups=self.starters(),
        )

    def _unsupported(self) -> Draft:
        return Draft(
            status="unsupported",
            headline="This is outside what RUMIN's records can answer",
            blocks=[text("policy", policy.UNSUPPORTED)],
            follow_ups=self.starters(),
        )

    def _capabilities(self) -> Draft:
        body = (
            "The Analyst answers from RUMIN's own records, through a fixed set of read-only "
            "tools, and cites the record behind every figure. It can say what RUMIN knows "
            "about a company or industry, which economic variables reach it and through "
            "which relationships, which companies a variable reaches, how two records are "
            "connected, what a stored series shows and how it changed between two periods, "
            "what changed recently, what the Financial Intelligence findings are, what a "
            "stored scenario simulated and why a line moved, and what the models compute "
            "for a what-if, without storing it."
        )
        limits = (
            "It does not forecast, does not hold live market data, and does not make "
            "investment decisions. When RUMIN lacks what a question needs, it says so."
        )
        return Draft(
            status="answered",
            headline="What the Analyst can answer",
            blocks=[text("detail", body), text("policy", limits)],
            follow_ups=self.starters(),
        )

    def starters(self) -> list[str]:
        company = next(iter(self.vocabulary.of_kind("company")), None)
        variable = self.vocabulary.by_record("var_brent_crude") or next(
            iter(self.vocabulary.of_kind("variable")), None
        )
        found = []
        if company is not None:
            found.append(f"What does RUMIN know about {company.label}?")
        if variable is not None:
            found.append(f"Which companies does {the(variable.label)} reach?")
        found.append("What data does RUMIN hold?")
        found.append("What changed recently?")
        return found

    # --- companies and industries --------------------------------------------------------------

    def _entity_overview(self) -> Draft:
        entity = self.route.entities[0]
        call = self.call("get_entity_dossier", entity_key=entity.key)
        if not call.ok or call.output is None:
            return self.failure(call, entity.label)
        facts = call.output.facts
        analysis = facts.analysis
        data = call.output.data
        record = data["entity"]["evidence"]
        exposure = data["exposure"]
        blocks: list[Block] = []
        kind = "company" if analysis.entity.node_type == "company" else "industry"
        fictional = analysis.entity.nature == "fictional"
        opening = (
            f"{entity.label} is a {'fictional ' if fictional else ''}{kind} in RUMIN's "
            f"knowledge graph{cite(record)}."
        )
        if facts.description:
            described = policy.data_text(facts.description).rstrip(". ")
            opening += f" RUMIN's record describes it as “{described}”{cite(record)}."
        blocks.append(text("answer", opening))
        paths, variables = exposure["paths"], exposure["variables"]
        if paths:
            channels = ", ".join(
                f"{count} through {channel}"
                for channel, count in sorted(exposure["by_channel"].items())
            )
            names = sorted({path.hops[0].name for path in analysis.exposure.paths})
            blocks.append(
                text(
                    "answer",
                    f"The graph states {plural(paths, 'path')} by which "
                    f"{plural(variables, 'economic variable')} reach it: {channels}"
                    f"{cite(exposure['evidence'])}. They start from "
                    f"{fmt.listing(names)}{cite(exposure['evidence'])}.",
                )
            )
        else:
            blocks.append(
                text(
                    "answer",
                    f"The graph states no exposure of {entity.label} to any economic "
                    f"variable{cite(exposure['evidence'])}.",
                )
            )
        latest = data.get("latest_execution")
        if latest is not None and analysis.drivers is not None:
            drivers = analysis.drivers
            head = (
                next((line for line in drivers.lines if line.id == "profit_before_tax"), None)
                or next((line for line in drivers.lines if line.id == "operating_profit"), None)
                or (drivers.lines[0] if drivers.lines else None)
            )
            sim = latest["evidence"][0]
            name = policy.data_text(drivers.execution.scenario_name, 120)
            if head is not None:
                blocks.append(
                    text(
                        "answer",
                        f"Its latest stored scenario execution, “{name}” (version "
                        f"{drivers.execution.version}), simulated {head.label.lower()} "
                        f"{'falling' if head.change < 0 else 'rising'} by "
                        f"{money(abs(head.change), head.currency)} over "
                        f"{drivers.execution.horizon_months} months{cite(sim)}. That is a "
                        "simulated result under the scenario's changes and entered figures, "
                        "not a forecast.",
                    )
                )
        else:
            blocks.append(
                text("detail", f"No completed scenario execution is stored for {entity.label}.")
            )
        findings = data.get("findings") or []
        if findings:
            top = findings[0]
            total = data["findings_total"]
            blocks.append(
                text(
                    "answer",
                    f"Financial Intelligence lists {plural(total['count'], 'finding')} "
                    f"for it{cite(total['evidence'])}; the first reads "
                    f"“{policy.data_text(top['headline'], 200)}” (evidence grade "
                    f"{top['grade']}){cite(top['evidence'])}.",
                )
            )
        blocks.extend(call.output.display)
        if fictional:
            blocks.append(
                notice(
                    "illustrative",
                    "Illustrative record",
                    f"{entity.label} is part of RUMIN's illustrative sample network: its "
                    "relationships say nothing about any real company.",
                    record,
                )
            )
        blocks.extend(self.focus_note())
        variable = analysis.exposure.paths[0].hops[0].name if analysis.exposure.paths else None
        follow = [
            f"Which variables affect {possessive(entity.label)} costs?",
            f"What did the latest scenario on {entity.label} show?",
        ]
        if variable:
            follow.append(f"How is {the(variable)} connected to {entity.label}?")
        follow.append(f"What are the findings for {entity.label}?")
        return Draft(
            status="answered",
            headline=f"What RUMIN holds on {entity.label}",
            blocks=blocks,
            follow_ups=follow,
            focus={"subject": entity.key, "entity": entity.key},
        )

    def _exposure(self) -> Draft:
        entity = self.route.entities[0]
        variable = self.route.variables[0] if self.route.variables else None
        channel = self.route.channel
        call = self.call(
            "get_exposure",
            entity_key=entity.key,
            channel=channel if channel in ("costs", "revenue", "financing") else None,
            variable_key=variable.key if variable else None,
        )
        if not call.ok or call.output is None:
            return self.failure(call, entity.label)
        exposure, paths = call.output.facts
        data = call.output.data
        summary = data["evidence"]
        scope = []
        if channel:
            scope.append(f"its {channel}")
        if variable:
            scope.append(variable.label)
        about = f" ({' and '.join(scope)})" if scope else ""
        blocks: list[Block] = []
        if not paths:
            blocks.append(
                text(
                    "answer",
                    f"The knowledge graph states no path by which an economic variable reaches "
                    f"{entity.label}{about}{cite(summary)}.",
                )
            )
            if exposure.paths:
                blocks.append(
                    text(
                        "detail",
                        f"It does state {plural(len(exposure.paths), 'path')} in all, through "
                        f"other channels or variables{cite(summary)}.",
                    )
                )
            status: AnswerStatus = "no_data"
            headline = f"No stated exposure of {entity.label}{about}"
        else:
            variables = len({node.key for path in paths for node in path.hops})
            channels = Counter(path.channel for path in paths)
            breakdown = (
                ": "
                + ", ".join(f"{count} through {name}" for name, count in sorted(channels.items()))
                if not channel and len(channels) > 1
                else ""
            )
            reach = (
                f"{the(variable.label)} reaches {entity.label}"
                + (f" (its {channel})" if channel else "")
                if variable
                else f"{plural(variables, 'economic variable')} reach {entity.label}{about}"
            )
            blocks.append(
                text(
                    "answer",
                    f"The knowledge graph states {plural(len(paths), 'path')} by which {reach}"
                    f"{breakdown}{cite(summary)}.",
                )
            )
            display = call.output.display
            items = display[0].paths if display and isinstance(display[0], PathsBlock) else []
            for path, item in list(zip(paths, items, strict=False))[:5]:
                chain = " → ".join(step.name for step in item.steps)
                between = [node.name for node in path.hops[1:]]
                if path.directness == "direct":
                    how = "directly"
                elif path.directness == "via_industry" and path.industry is not None:
                    how = (
                        f"through its industry, {path.industry.name} (a relationship stated for "
                        "the industry as a whole)"
                    )
                else:
                    how = f"upstream, through {fmt.listing(between)}"
                    if path.industry is not None:
                        how += f" and its industry, {path.industry.name}"
                models = (
                    f"Models that can simulate it: {', '.join(path.models)}."
                    if path.models
                    else "No registered model simulates this path."
                )
                blocks.append(
                    text(
                        "detail",
                        f"{path.origin.name} reaches its {path.channel} {how}: {chain} (weakest "
                        f"evidence: {path.evidence_status.replace('_', ' ')})"
                        f"{cite(*item.citations)}. {models}",
                    )
                )
            status = "answered"
            headline = (
                f"How {the(variable.label)} reaches {entity.label}: "
                f"{plural(len(paths), 'stated path')}"
                if variable
                else f"{plural(variables, 'economic variable')} reach {entity.label}{about} "
                f"through {plural(len(paths), 'stated path')}"
            )
        blocks.extend(call.output.display)
        blocks.append(
            notice(
                "limitation",
                "Stated, not sized",
                "These relationships say who is exposed and through what, never by how much. A "
                "scenario sizes an exposure under stated changes and figures.",
            )
        )
        blocks.extend(self.focus_note())
        first = paths[0].origin if paths else None
        follow = [f"What did the latest scenario on {entity.label} show?"]
        origin = self.vocabulary.get(first.key) if first is not None else None
        if origin is not None and origin.kind == "variable":
            follow.insert(
                0,
                f"What if {the(origin.label)} rises {example_change(origin)} for {entity.label}?",
            )
        for other in ("revenue", "financing", "costs"):
            if other != channel:
                follow.append(f"And {possessive(entity.label)} {other} exposure?")
                break
        return Draft(
            status=status,
            headline=headline,
            blocks=blocks,
            follow_ups=follow,
            focus={
                "subject": entity.key,
                "entity": entity.key,
                **({"variable": variable.key} if variable else {}),
            },
        )

    def _compare_exposure(self) -> Draft:
        entities = self.route.entities[:3]
        rows = []
        sentences = []
        variables_by: dict[str, set[str]] = {}
        for entity in entities:
            call = self.call("get_exposure", entity_key=entity.key)
            if not call.ok or call.output is None:
                return self.failure(call, entity.label)
            _exposure, paths = call.output.facts
            data = call.output.data
            names = {node.name for path in paths for node in path.hops}
            variables_by[entity.label] = names
            channels = Counter(path.channel for path in paths)
            rows.append(
                TableRow(
                    cells={
                        "entity": entity.label,
                        "paths": str(len(paths)),
                        "variables": str(len(names)),
                        "costs": str(channels.get("costs", 0)),
                        "revenue": str(channels.get("revenue", 0)),
                        "financing": str(channels.get("financing", 0)),
                    },
                    citations=[data["evidence"]],
                )
            )
            sentences.append(
                f"{entity.label}: {plural(len(paths), 'path')} from "
                f"{plural(len(names), 'variable')}{cite(data['evidence'])}"
            )
        shared = set.intersection(*variables_by.values()) if variables_by else set()
        blocks: list[Block] = [
            text("answer", "In the knowledge graph, " + "; ".join(sentences) + "."),
        ]
        if shared:
            blocks.append(
                text("detail", f"Variables that reach all of them: {fmt.listing(sorted(shared))}.")
            )
        else:
            blocks.append(text("detail", "No economic variable reaches all of them."))
        blocks.append(
            TableBlock(
                title="Stated exposure, side by side",
                columns=[
                    Column(key="entity", label="Company or industry"),
                    Column(key="paths", label="Paths", align="end"),
                    Column(key="variables", label="Variables", align="end"),
                    Column(key="costs", label="Costs", align="end"),
                    Column(key="revenue", label="Revenue", align="end"),
                    Column(key="financing", label="Financing", align="end"),
                ],
                rows=rows,
                note="Counts of stated relationship paths: who is exposed and through what, "
                "not how much.",
            )
        )
        return Draft(
            status="answered",
            headline="Stated exposure of " + fmt.listing([e.label for e in entities]),
            blocks=blocks,
            follow_ups=[
                f"Which variables affect {possessive(e.label)} costs?" for e in entities[:2]
            ],
            focus={"subject": entities[0].key, "entity": entities[0].key},
        )

    # --- variables and connections -------------------------------------------------------------

    def _variable_reach(self) -> Draft:
        variable = self.route.variables[0]
        call = self.call("get_variable_reach", variable_key=variable.key)
        if not call.ok or call.output is None:
            return self.failure(call, variable.label)
        data = call.output.data
        summary = data["evidence"]
        total = data["companies_total"]
        companies = data["companies"]
        blocks: list[Block] = []
        if total:
            names = [item["name"] for item in companies[:8]]
            more = f", and {total - len(names)} more" if total > len(names) else ""
            blocks.append(
                text(
                    "answer",
                    f"The knowledge graph states that {the(variable.label)} reaches "
                    f"{plural(total, 'company', 'companies')}{cite(summary)}: "
                    f"{', '.join(names)}{more}.",
                )
            )
            channels = Counter(
                channel.strip()
                for item in companies
                for channel in item["channels"].split(",")
                if channel.strip()
            )
            blocks.append(
                text(
                    "detail",
                    "By channel: "
                    + ", ".join(
                        f"{name} for {plural(count, 'company', 'companies')}"
                        for name, count in sorted(channels.items())
                    )
                    + f"{cite(summary)}.",
                )
            )
        else:
            blocks.append(
                text(
                    "answer",
                    f"The knowledge graph states no company that the "
                    f"{variable.label} reaches{cite(summary)}.",
                )
            )
        related = data["related_series"]
        if related:
            parts = [
                f"{item['name']} ({plural(item['stored_values'], 'stored value')})"
                f"{cite(item['evidence'])}"
                for item in related
            ]
            blocks.append(
                text("detail", f"Recorded as related measures of it: {'; '.join(parts)}.")
            )
        else:
            blocks.append(
                text(
                    "detail",
                    f"RUMIN stores no series recorded as a measure of the "
                    f"{variable.label}{cite(data['variable']['evidence'])}.",
                )
            )
        blocks.extend(call.output.display)
        blocks.append(
            notice(
                "limitation",
                "Stated, not sized",
                "The graph says who is exposed and through what, never by how much.",
            )
        )
        blocks.extend(self.focus_note())
        first = companies[0]["name"] if companies else None
        follow = []
        if first:
            follow.append(f"How is {the(variable.label)} connected to {first}?")
            follow.append(f"What if {the(variable.label)} rises {example_change(variable)}?")
        if related:
            follow.append(f"Show {related[0]['name']}.")
        return Draft(
            status="answered" if total else "no_data",
            headline=(
                f"The {variable.label} reaches {plural(total, 'company', 'companies')}"
                if total
                else f"No company is stated to be reached by {the(variable.label)}"
            ),
            blocks=blocks,
            follow_ups=follow,
            focus={"subject": variable.key, "variable": variable.key},
        )

    def _connection(self) -> Draft:
        route = self.route
        subjects: list[Term] = [*route.variables, *route.entities, *route.series, *route.countries]
        source, target = subjects[0], subjects[1]
        call = self.call("find_paths", from_key=source.key, to_key=target.key)
        if not call.ok or call.output is None:
            return self.failure(call, f"{source.label} and {target.label}")
        found = call.output.facts
        data = call.output.data
        blocks: list[Block] = []
        if not found.found:
            blocks.append(
                text(
                    "answer",
                    f"The knowledge graph holds no chain of up to 4 relationships "
                    f"between {source.label} and {target.label}"
                    f"{cite(data['evidence'])}.",
                )
            )
            status: AnswerStatus = "no_data"
            headline = f"No connection found between {source.label} and {target.label}"
        else:
            blocks.append(
                text(
                    "answer",
                    f"{source.label} and {target.label} are connected by "
                    f"{plural(len(found.paths), 'shortest path')} of "
                    f"{plural(found.length or 0, 'relationship')} each{cite(data['evidence'])}.",
                )
            )
            # The paths display draws each chain; without it, the chains are written out.
            if not any(isinstance(item, PathsBlock) for item in call.output.display):
                for path in data["paths"]:
                    chain = " → ".join(path["nodes"])
                    blocks.append(
                        text(
                            "detail",
                            f"{chain} ({', '.join(path['relationships'])})"
                            f"{cite(*path['evidence'])}.",
                        )
                    )
            status = "answered"
            headline = (
                f"{source.label} and {target.label} are "
                f"{plural(found.length or 0, 'relationship')} apart"
            )
        # The notice below says what a path is not; the display does not repeat it.
        blocks.extend(
            item.model_copy(update={"note": None}) if isinstance(item, PathsBlock) else item
            for item in call.output.display
        )
        blocks.append(
            notice(
                "limitation",
                "A connection, not a cause",
                "A path shows how records are connected. It is not an influence or causal "
                "chain, and a shorter path is not a stronger relationship.",
            )
        )
        focus_key = next(
            (term.key for term in (source, target) if term.kind in ("company", "industry")),
            source.key,
        )
        return Draft(
            status=status,
            headline=headline,
            blocks=blocks,
            follow_ups=[
                f"What does RUMIN know about {target.label}?",
                f"What does RUMIN know about {source.label}?",
            ],
            focus={
                "subject": focus_key,
                **(
                    {"entity": focus_key} if focus_key.startswith(("company:", "industry:")) else {}
                ),
            },
        )

    # --- data ----------------------------------------------------------------------------------

    def _no_series(self) -> Draft:
        variable = self.route.variables[0] if self.route.variables else None
        if variable is None:
            return self._clarify()
        call = self.call("get_variable_reach", variable_key=variable.key)
        cited = call.output.data["variable"]["evidence"] if call.ok and call.output else None
        return Draft(
            status="no_data",
            headline=f"RUMIN stores no series for {the(variable.label)}",
            blocks=[
                text(
                    "answer",
                    f"RUMIN holds no stored series recorded as a measure of the "
                    f"{variable.label}{cite(cited)}, so it has no values to show.",
                ),
                notice(
                    "missing_data",
                    "What would supply it",
                    "A provider series for this variable would need to be catalogued and "
                    "ingested (see the Data Explorer).",
                ),
            ],
            follow_ups=[
                "What data does RUMIN hold?",
                f"Which companies does {the(variable.label)} reach?",
            ],
            focus={"subject": variable.key, "variable": variable.key},
        )

    def _series_history(self) -> Draft:
        route = self.route
        if not route.series:
            return self._no_series()
        series = route.series[0]
        periods = route.periods
        start = periods.start or (min(periods.years) if periods.years else None)
        end = periods.end or (max(periods.years) if len(periods.years) > 1 else None)
        call = self.call(
            "get_series",
            series_id=series.record_id,
            start_year=start,
            end_year=end,
            last=periods.last,
        )
        if not call.ok or call.output is None:
            return self.failure(call, series.label)
        data = call.output.data
        evidence = data["evidence"]
        cited = evidence[0] if isinstance(evidence, list) else evidence
        if not data.get("stored_values"):
            return Draft(
                status="no_data",
                headline=f"No values of {series.label} are stored",
                blocks=[
                    text(
                        "answer",
                        f"{series.label} is catalogued, but no values are stored for "
                        f"it{cite(cited)}.",
                    ),
                    notice(
                        "missing_data",
                        "What would supply it",
                        "Ingesting it from its provider (see the Data Explorer) would store "
                        "its values.",
                    ),
                ],
                follow_ups=["What data does RUMIN hold?"],
                focus={"subject": series.key, "series": series.key},
            )
        latest, first = data["latest"], data["first"]
        unit = data["unit"]
        shown = data["shown"]
        blocks: list[Block] = [
            text(
                "answer",
                f"RUMIN stores {plural(data['stored_values'], data['frequency'] + ' value')} of "
                f"{series.label}, from {first['period']} to {latest['period']}{cite(cited)}. "
                f"The latest, for {latest['period']}, is {stored(latest['value'])} "
                f"({unit}){cite(cited)}.",
            )
        ]
        change = data.get("latest_change")
        if change is not None and change["value"] is not None:
            unit_word = "%" if change["unit"] == "percent" else "percentage points"
            blocks.append(
                text(
                    "detail",
                    f"The change from {change['from']} to {change['to']} is "
                    f"{fmt.signed(Decimal(change['value']))} {unit_word}{cite(cited)}.",
                )
            )
        if shown and (start or end or periods.last):
            low = min(shown, key=lambda item: Decimal(item["value"]))
            high = max(shown, key=lambda item: Decimal(item["value"]))
            blocks.append(
                text(
                    "detail",
                    f"Between {shown[0]['period']} and {shown[-1]['period']} it ranged from "
                    f"{stored(low['value'])} ({low['period']}) to {stored(high['value'])} "
                    f"({high['period']}){cite(cited)}.",
                )
            )
        if data.get("trend"):
            blocks.append(text("detail", f"{data['trend']}{cite(cited)}"))
        relation = data.get("relation_to_variable")
        # The notice below says it with a citation; the chart does not repeat it.
        blocks.extend(
            item.model_copy(update={"note": None})
            if relation and isinstance(item, SeriesBlock)
            else item
            for item in call.output.display
        )
        if relation:
            blocks.append(
                notice(
                    "limitation",
                    "Not the same measure as the variable",
                    f"RUMIN's catalogue says: “{data['relation_to_variable']}”",
                    cited,
                )
            )
        if data.get("illustrative"):
            blocks.append(
                notice(
                    "illustrative",
                    "Illustrative data",
                    "These values come from a dataset marked illustrative.",
                    cited,
                )
            )
        if route.alternatives:
            blocks.append(
                notice(
                    "assumption",
                    "Other series fit the question",
                    f"Also stored: {fmt.listing([t.label for t in route.alternatives])}. "
                    "Ask for one by name.",
                )
            )
        blocks.extend(self.assumptions())
        blocks.extend(self.focus_note())
        return Draft(
            status="answered",
            headline=f"{series.label}: {stored(latest['value'])} in {latest['period']}",
            blocks=blocks,
            follow_ups=[
                f"How much did it change between {first['period']} and {latest['period']}?",
                "What changed recently?",
            ],
            focus={
                "subject": series.key,
                "series": series.key,
                **({"variable": f"variable:{series.variable.lower()}"} if series.variable else {}),
            },
        )

    def _period_change(self) -> Draft:
        route = self.route
        if not route.series:
            return self._no_series()
        series = route.series[0]
        periods = route.periods
        years = sorted({*periods.years, *(y for y in (periods.start, periods.end) if y)})
        question = self.question_evidence()
        if len(years) < 2:
            probe = self.call("get_series", series_id=series.record_id)
            if not probe.ok or probe.output is None:
                return self.failure(probe, series.label)
            latest = probe.output.data.get("latest")
            if not latest or not years:
                return self._series_history()
            years = [years[0], int(str(latest["period"])[:4])]
        call = self.call(
            "compare_periods",
            series_id=series.record_id,
            from_period=str(years[0]),
            to_period=str(years[-1]),
        )
        if not call.ok or call.output is None:
            probe = self.call("get_series", series_id=series.record_id)
            stored_range = probe.output.data if probe.ok and probe.output else None
            blocks: list[Block] = []
            if stored_range and stored_range.get("stored_values"):
                cited = stored_range["evidence"][0]
                blocks.append(
                    text(
                        "answer",
                        f"RUMIN stores values of {series.label} from "
                        f"{stored_range['first']['period']} to "
                        f"{stored_range['latest']['period']}{cite(cited)}; there is no stored "
                        f"value for "
                        + " or ".join(str(y) for y in years)
                        + f"{cite(question)} to compare.",
                    )
                )
            else:
                blocks.append(text("answer", call.error or "No stored values to compare."))
            return Draft(
                status="no_data",
                headline=f"No stored values of {series.label} for those periods",
                blocks=blocks,
                follow_ups=[f"Show {series.label}."],
                focus={"subject": series.key, "series": series.key},
            )
        data = call.output.data
        cited = data["evidence"]
        earlier, later = data["earlier"], data["later"]
        unit_word = "%" if data["change_unit"] == "percent" else "percentage points"
        change = _d(data["change"])
        blocks = [
            text(
                "answer",
                f"{series.label} was {stored(earlier['value'])} in {earlier['period']} and "
                f"{stored(later['value'])} in {later['period']} ({data['unit']}){cite(cited)}: "
                + (
                    f"a change of {fmt.signed(change)} {unit_word}"
                    if change is not None
                    else "a change that cannot be expressed in percent"
                )
                + (
                    f", or {fmt.signed_stored(Decimal(data['difference']))} in its own unit"
                    if data["change_unit"] == "percent"
                    else ""
                )
                + f"{cite(cited)}.",
            ),
            text(
                "detail",
                f"Computed by RUMIN in exact decimals as {data['method']}; the "
                "exact figure is kept with the evidence.",
            ),
        ]
        blocks.extend(call.output.display)
        blocks.extend(self.assumptions())
        return Draft(
            status="answered",
            headline=(
                f"{series.label}: {fmt.signed(change)} {unit_word} from {earlier['period']} to "
                f"{later['period']}"
                if change is not None
                else f"{series.label}: {earlier['period']} to {later['period']}"
            ),
            blocks=blocks,
            follow_ups=[
                f"Show {series.label} since {earlier['period']}.",
                "What changed recently?",
            ],
            focus={"subject": series.key, "series": series.key},
        )

    def _live_data(self) -> Draft:
        route = self.route
        blocks: list[Block] = [text("policy", policy.LIVE_DATA)]
        if not route.series:
            if route.variables:
                draft = self._no_series()
                draft.blocks = blocks + draft.blocks
                draft.status = "partial"
                return draft
            return Draft(
                status="partial",
                headline="RUMIN holds stored values, not live data",
                blocks=blocks,
                follow_ups=["What data does RUMIN hold?"],
            )
        series = route.series[0]
        call = self.call("get_series", series_id=series.record_id, last=5)
        if not call.ok or call.output is None:
            return self.failure(call, series.label)
        data = call.output.data
        if not data.get("stored_values"):
            blocks.append(
                text("answer", f"No values of {series.label} are stored{cite(data['evidence'])}.")
            )
            return Draft(status="no_data", headline="RUMIN holds no values for this", blocks=blocks)
        cited = data["evidence"][0]
        latest = data["latest"]
        item = self.ledger.get(cited)
        retrieved = (
            item.provenance.get("retrieved_from_provider", "")[:10] if item is not None else ""
        )
        blocks.append(
            text(
                "answer",
                f"The latest stored value of {series.label} is {stored(latest['value'])} "
                f"({data['unit']}) for {latest['period']}, retrieved from its provider on "
                f"{retrieved}{cite(cited)}.",
            )
        )
        blocks.extend(call.output.display)
        return Draft(
            status="partial",
            headline=f"Latest stored: {stored(latest['value'])} for {latest['period']} (not live)",
            blocks=blocks,
            follow_ups=[f"Show {series.label}.", "What data does RUMIN hold?"],
            focus={"subject": series.key, "series": series.key},
        )

    def _changes(self) -> Draft:
        call = self.call("list_changes")
        if not call.ok or call.output is None:
            return self.failure(call, "recent changes")
        data = call.output.data
        found = call.output.facts
        blocks: list[Block] = []
        totals = data["totals"]
        observed = data["observed"]
        relationships = data["relationships"]
        total = totals["evidence"]
        blocks.append(
            text(
                "answer",
                f"In RUMIN's stored data, {plural(totals['observed'], 'latest change')} "
                f"{'meets' if totals['observed'] == 1 else 'meet'} the default thresholds, "
                f"{plural(totals['revisions'], 'stored value')} "
                f"{'was' if totals['revisions'] == 1 else 'were'} revised, and "
                f"{plural(totals['executions'], 'company', 'companies')} "
                f"{'has' if totals['executions'] == 1 else 'have'} a changed simulated headline "
                f"between two executions of the same scenario{cite(total)}.",
            )
        )
        for row in observed[:3]:
            value = Decimal(row["change"])
            unit_word = "%" if row["unit"] == "percent" else "percentage points"
            blocks.append(
                text(
                    "detail",
                    f"{row['what']}: {fmt.signed(value)} {unit_word} from "
                    f"{row['from']} to {row['to']}{cite(*row['evidence'])}.",
                )
            )
        counts = {key: value for key, value in relationships.items() if key != "evidence"}
        rel_total = sum(int(value) for value in counts.values() if str(value).isdigit())
        blocks.append(
            text(
                "detail",
                (
                    "Between the last two knowledge-graph builds, relationships changed: "
                    + ", ".join(f"{value} {key}" for key, value in counts.items())
                    if rel_total
                    else "No relationship changed between the last two knowledge-graph builds"
                )
                + f"{cite(relationships['evidence'])}.",
            )
        )
        blocks.extend(call.output.display)
        blocks.extend(
            notice("limitation", "What these are", policy.data_text(note, 300))
            for note in found.notes[:2]
        )
        return Draft(
            status="answered",
            headline=f"{plural(totals['observed'], 'observed change')}, "
            f"{plural(totals['revisions'], 'revision')}, "
            f"{plural(totals['executions'], 'simulated change')}",
            blocks=blocks,
            follow_ups=["What are the main findings?", "What data does RUMIN hold?"],
        )

    def _findings(self) -> Draft:
        entity = self.route.entities[0] if self.route.entities else None
        call = self.call("get_findings", entity_key=entity.key if entity else None)
        if not call.ok or call.output is None:
            return self.failure(call, entity.label if entity else "the workspace")
        data = call.output.data
        findings = data["findings"]
        where = f" for {entity.label}" if entity else ""
        blocks: list[Block] = []
        if not findings:
            summary = data["evidence"]
            blocks.append(
                text("answer", f"Financial Intelligence records no findings{where}{cite(summary)}.")
            )
            status: AnswerStatus = "no_data"
        else:
            blocks.append(
                text(
                    "answer",
                    f"Financial Intelligence records {plural(data['total'], 'finding')}{where}"
                    f"{cite(data['evidence'])}. The first, in the order Financial Intelligence "
                    "ranks them:",
                )
            )
            for item in findings[:3]:
                simulated = (
                    " It rests on a simulation, so it holds only under that scenario's "
                    "changes and figures."
                    if item["conditional_on_simulation"]
                    else ""
                )
                headline = policy.data_text(item["headline"], 200)
                kind = item["kind"].replace("_", " ")
                blocks.append(
                    text(
                        "detail",
                        f"“{headline}” — {kind}, evidence grade {item['grade']}"
                        f"{cite(item['evidence'])}." + simulated,
                    )
                )
            status = "answered"
        blocks.extend(call.output.display)
        blocks.append(
            notice(
                "limitation",
                "What a grade means",
                "An evidence grade is the weakest step of a finding's chain (observed, "
                "documented, curated, simulated, assumed, unverified). It is not a "
                "probability.",
            )
        )
        blocks.extend(self.focus_note())
        return Draft(
            status=status,
            headline=f"{plural(data['total'], 'finding')}{where}",
            blocks=blocks,
            follow_ups=(
                [
                    f"Which variables affect {possessive(entity.label)} costs?",
                    f"What did the latest scenario on {entity.label} show?",
                ]
                if entity
                else ["What changed recently?", "What data does RUMIN hold?"]
            ),
            focus={"subject": entity.key, "entity": entity.key} if entity else {},
        )

    # --- scenarios -----------------------------------------------------------------------------

    def _no_execution(self, entity: Term) -> Draft:
        call = self.call("list_scenarios", entity_key=entity.key)
        data = call.output.data if call.ok and call.output else {}
        cited = self.ledger.add(
            tool="list_scenarios",
            call=call.position,
            kind=Knowledge.RECORD,
            title=f"Stored scenarios for {entity.label}",
            source=SourceRef(
                kind="catalogue",
                id=f"scenarios:{entity.key}",
                label="Scenario Lab",
                link="/scenarios",
            ),
            retrieved_at=self.runner.clock(),
            values={"scenarios": data.get("matching", 0)},
        )
        return Draft(
            status="no_data",
            headline=f"No completed scenario execution is stored for {entity.label}",
            blocks=[
                text(
                    "answer",
                    f"RUMIN stores {plural(data.get('matching', 0), 'scenario')} for "
                    f"{entity.label} and no completed execution of one"
                    f"{cite(cited)}.",
                ),
                notice(
                    "missing_data",
                    "What would supply it",
                    f"A scenario for {entity.label}, with its figures entered and executed in "
                    "the Scenario Lab, would give results to read. The Analyst can preview a "
                    "what-if, but it never saves or executes one.",
                ),
            ],
            follow_ups=[
                f"What if Brent crude rises 20% for {entity.label}?",
                "What scenario templates are there?",
            ],
            focus={"subject": entity.key, "entity": entity.key},
        )

    def _scenario_results(self) -> Draft:
        entity = next((term for term in self.route.entities if term.kind == "company"), None)
        if entity is None:
            return self._list_stored()
        call = self.call("get_execution", entity_key=entity.key)
        if call.status == "not_found":
            return self._no_execution(entity)
        if not call.ok or call.output is None:
            return self.failure(call, entity.label)
        facts = call.output.facts
        drivers = facts.drivers
        data = call.output.data
        cited = data["evidence"]
        simulated = cited[0]
        user = cited[1] if len(cited) > 1 else None
        execution = drivers.execution
        changes = ", ".join(
            f"{change.name} {fmt.signed_stored(change.value)}"
            f"{' %' if change.change_type == 'percent_change' else ' ' + change.unit}"
            for change in drivers.changes
        )
        blocks: list[Block] = [
            text(
                "answer",
                f"The latest stored execution for {entity.label} is of “"
                f"{policy.data_text(execution.scenario_name, 120)}” (version {execution.version}),"
                f" simulating {execution.horizon_months} months under these changes: {changes}"
                f"{cite(simulated)}.",
            )
        ]
        ordered = sorted(
            drivers.lines,
            key=lambda line: LINE_ORDER.index(line.id) if line.id in LINE_ORDER else 99,
        )
        for line in ordered[:5]:
            percent = (
                f" ({fmt.percent(line.percent_change)})" if line.percent_change is not None else ""
            )
            blocks.append(
                text(
                    "detail",
                    f"{line.label}: {money(line.baseline, line.currency)} in the baseline, "
                    f"{money(line.change, line.currency, sign=True)} under the scenario"
                    f"{percent}{cite(simulated)}.",
                )
            )
        contributions = data["largest_contributions"]
        headline_line = next(
            (line for line in ordered if line.id == "profit_before_tax"), None
        ) or (ordered[-1] if ordered else None)
        if contributions:
            top = (
                contributions[-1]
                if headline_line is None
                else next(
                    (item for item in contributions if item["line"] == headline_line.label),
                    contributions[-1],
                )
            )
            share = (
                f", {fmt.percent(Decimal(top['share_of_change']), sign=False)} of that change"
                if top.get("share_of_change")
                else ""
            )
            credit = self.ledger.ids_for("execution", execution.id)
            blocks.append(
                text(
                    "detail",
                    f"The largest contribution to the change in {top['line'].lower()} comes from "
                    f"{top['largest_contribution']}: "
                    f"{money(top['value'], execution.currency, sign=True)}{share}"
                    f"{cite(*credit)}.",
                )
            )
        blocks.extend(call.output.display)
        blocks.append(
            notice(
                "limitation",
                "Simulated, not observed",
                "These are results of the registered models under the scenario's changes, "
                "entered figures and assumptions. They are not forecasts.",
                simulated,
            )
        )
        if user:
            blocks.append(
                notice(
                    "assumption",
                    "Figures a person entered",
                    "The results rest on company figures entered in the Scenario Lab, shown "
                    "with the evidence. They are not RUMIN data.",
                    user,
                )
            )
        blocks.extend(self.focus_note())
        head = headline_line
        return Draft(
            status="answered",
            headline=(
                f"{head.label} {money(head.change, head.currency, sign=True)} in "
                f"“{policy.data_text(execution.scenario_name, 80)}” (simulated)"
                if head is not None
                else f"Latest execution for {entity.label}"
            ),
            blocks=blocks,
            follow_ups=[
                f"Why did operating costs change for {entity.label}?",
                "What about 30%?" if drivers.changes else "What scenario templates are there?",
                f"Which variables affect {possessive(entity.label)} costs?",
            ],
            focus={
                "subject": entity.key,
                "entity": entity.key,
                "scenario_id": execution.scenario_id,
                "execution_id": execution.id,
                "intent": "what_if",
                "changes": [
                    {
                        "variable_id": change.variable_id,
                        "change_type": change.change_type,
                        "value": format(change.value.normalize(), "f"),
                    }
                    for change in drivers.changes
                ],
                "horizon": execution.horizon_months,
            },
        )

    def _list_stored(self) -> Draft:
        call = self.call("list_scenarios")
        if not call.ok or call.output is None:
            return self.failure(call, "stored scenarios")
        data = call.output.data
        cited = self.ledger.add(
            tool="list_scenarios",
            call=call.position,
            kind=Knowledge.RECORD,
            title="Stored scenarios",
            source=SourceRef(
                kind="catalogue", id="scenarios", label="Scenario Lab", link="/scenarios"
            ),
            retrieved_at=self.runner.clock(),
            values={"scenarios": data["total_stored"]},
        )
        blocks: list[Block] = [
            text(
                "answer",
                f"RUMIN stores {plural(data['total_stored'], 'scenario')}"
                f"{cite(cited)}. Name a company to read its latest execution.",
            ),
        ]
        blocks.extend(call.output.display)
        return Draft(
            status="answered" if data["total_stored"] else "no_data",
            headline=f"{plural(data['total_stored'], 'stored scenario')}",
            blocks=blocks,
            follow_ups=["What scenario templates are there?"],
        )

    def _explain_line(self) -> Draft:
        entity = next((term for term in self.route.entities if term.kind == "company"), None)
        line = self.route.line or "operating_profit"
        if entity is None:
            return Draft(
                status="clarification",
                headline="Which company's execution should be explained?",
                blocks=[
                    ClarificationBlock(
                        question="Which company's latest execution should be explained?",
                        options=[
                            ClarificationOption(
                                label=term.label,
                                question=f"Why did {line.replace('_', ' ')} "
                                f"change for {term.label}?",
                            )
                            for term in self.vocabulary.of_kind("company")[:4]
                        ],
                    )
                ],
            )
        execution_call = self.call("get_execution", entity_key=entity.key)
        if execution_call.status == "not_found":
            return self._no_execution(entity)
        if not execution_call.ok or execution_call.output is None:
            return self.failure(execution_call, entity.label)
        drivers = execution_call.output.facts.drivers
        execution = drivers.execution
        call = self.call("explain_line", execution_id=execution.id, line=line)
        if not call.ok or call.output is None:
            return self.failure(call, f"{line.replace('_', ' ')} of that execution")
        data = call.output.data
        cited = data["evidence"]
        simulated = execution_call.output.data["evidence"][0]
        target = next((item for item in drivers.lines if item.id == line), None)
        blocks: list[Block] = []
        if target is not None:
            blocks.append(
                text(
                    "answer",
                    f"In the latest stored execution for {entity.label}, “"
                    f"{policy.data_text(execution.scenario_name, 120)}” (version "
                    f"{execution.version}), the change in {target.label.lower()} is "
                    f"{money(target.change, target.currency, sign=True)}{cite(simulated)}.",
                )
            )
        credits = data["credit_by_change"]
        if credits:
            parts = [
                f"{item['change']} {money(item['credit'], execution.currency, sign=True)}"
                for item in credits
            ]
            blocks.append(
                text(
                    "answer",
                    "Contribution of each scenario change: "
                    + "; ".join(parts)
                    + f"{cite(cited)}. The contributions (the models' stored Shapley credits) "
                    "add up to the line's change.",
                )
            )
        blocks.append(
            text(
                "detail",
                f"The line is computed as {data['equation']}. The chain from each "
                f"change to the line, and the models' assumptions, are shown with the "
                f"evidence{cite(cited)}.",
            )
        )
        blocks.extend(call.output.display)
        blocks.append(
            notice(
                "limitation",
                "Simulated, not observed",
                "An explanation of a simulated result: it holds only under the scenario's "
                "changes, figures and assumptions.",
            )
        )
        return Draft(
            status="answered",
            headline=(
                f"What moves {target.label.lower()}: "
                f"{money(target.change, target.currency, sign=True)} (simulated)"
                if target is not None
                else f"Why {line.replace('_', ' ')} changed"
            ),
            blocks=blocks,
            follow_ups=[f"What did the latest scenario on {entity.label} show?", "What about 30%?"],
            focus={
                "subject": entity.key,
                "entity": entity.key,
                "scenario_id": execution.scenario_id,
                "execution_id": execution.id,
            },
        )

    def _what_if(self) -> Draft:
        route = self.route
        entity = next((term for term in route.entities if term.kind == "company"), None)
        industry = next((term for term in route.entities if term.kind == "industry"), None)
        changes = [
            {
                "variable_id": change.variable.record_id,
                "change_type": change.change_type,
                "value": format(change.value.normalize(), "f"),
            }
            for change in route.changes
        ]
        question = self.question_evidence()
        call = self.call(
            "preview_scenario",
            changes=changes,
            entity_key=entity.key if entity else None,
            horizon_months=route.horizon,
        )
        if not call.ok or call.output is None:
            draft = self.failure(call, "this what-if")
            draft.blocks.extend(self.assumptions())
            return draft
        data = call.output.data
        described = ", ".join(
            f"{change.variable.label} {fmt.signed_stored(change.value)}"
            f"{' %' if change.change_type == 'percent_change' else ' percentage points'}"
            for change in route.changes
        )
        blocks: list[Block] = []
        focus = {
            "intent": "what_if",
            "changes": changes,
            **({"subject": entity.key, "entity": entity.key} if entity else {}),
            **({"horizon": route.horizon} if route.horizon else {}),
        }
        if data.get("lines") is not None:
            preview, *rest = data["evidence"]
            figures = rest[0] if rest else None
            currency = data["currency"]
            blocks.append(
                text(
                    "answer",
                    f"Under {described}{cite(question)}, over {data['horizon_months']} months, "
                    f"the registered models compute for {data['company'] or 'the scenario'}"
                    f"{cite(preview)}:",
                )
            )
            ordered = sorted(
                data["lines"],
                key=lambda line: LINE_ORDER.index(line["id"]) if line["id"] in LINE_ORDER else 99,
            )
            for line in ordered:
                percent = (
                    f" ({pct(line['percent_change'])})"
                    if line["percent_change"] is not None
                    else ""
                )
                blocks.append(
                    text(
                        "detail",
                        f"{line['label']}: {money(line['change'], currency, sign=True)}"
                        f"{percent} against a baseline of "
                        f"{money(line['baseline'], currency)}{cite(preview)}.",
                    )
                )
            if figures and data.get("figures_from"):
                source = data["figures_from"]
                blocks.append(
                    text(
                        "detail",
                        f"The company figures are those a person entered in “"
                        f"{policy.data_text(source['scenario'], 120)}” (version "
                        f"{source['version']}){cite(figures)}.",
                    )
                )
            blocks.extend(call.output.display)
            blocks.append(
                notice(
                    "not_stored",
                    "Computed now, not stored",
                    "This preview was computed on request and is not saved. It is a "
                    "simulation under the changes asked about and the figures shown, not a "
                    "forecast. Open it in the Scenario Lab to save or execute it.",
                    preview,
                )
            )
            head = next((line for line in ordered if line["id"] == "profit_before_tax"), None) or (
                ordered[-1] if ordered else None
            )
            headline = (
                f"{head['label']} {money(head['change'], currency, sign=True)} under "
                f"{described} (preview, not stored)"
                if head
                else f"Preview under {described}"
            )
            status: AnswerStatus = "answered"
        else:
            plan = data["evidence"][0]
            missing = data.get("missing") or []
            subject = entity.label if entity else "a company"
            blocks.append(
                text(
                    "answer",
                    f"RUMIN cannot compute {described}{cite(question)} for {subject} yet: the "
                    f"models need figures only a person can enter"
                    f"{cite(plan)}. RUMIN never fills in company figures.",
                )
            )
            if missing:
                wanted = [policy.data_text(item, 160).rstrip(". ") for item in missing[:6]]
                blocks.append(text("detail", "Missing: " + "; ".join(wanted) + "."))
            if entity is None and route.changes:
                reach = self.call("get_variable_reach", variable_key=route.changes[0].variable.key)
                if reach.ok and reach.output is not None:
                    reached = reach.output.data
                    names = [item["name"] for item in reached["companies"][:6]]
                    if names:
                        blocks.append(
                            text(
                                "detail",
                                f"Companies the graph states the "
                                f"{route.changes[0].variable.label} reaches: "
                                f"{', '.join(names)}{cite(reached['evidence'])}.",
                            )
                        )
            if industry is not None:
                blocks.append(
                    notice(
                        "assumption",
                        "A company is needed",
                        f"Scenarios are run for a company, not an industry: name one in "
                        f"{industry.label}.",
                    )
                )
            blocks.extend(call.output.display)
            headline = f"{described}: the models need company figures first"
            status = "partial"
        blocks.extend(self.assumptions())
        blocks.extend(self.focus_note())
        follow = ["What about 30%?"] if len(route.changes) == 1 else []
        if entity:
            follow.append(f"Which variables affect {possessive(entity.label)} costs?")
        follow.append("What scenario templates are there?")
        return Draft(
            status=status, headline=headline, blocks=blocks, follow_ups=follow, focus=focus
        )

    # --- catalogue -----------------------------------------------------------------------------

    def _models(self) -> Draft:
        call = self.call("list_models")
        if not call.ok or call.output is None:
            return self.failure(call, "the models")
        models = call.output.data["models"]
        blocks: list[Block] = [
            text(
                "answer",
                f"RUMIN has {plural(len(models), 'registered simulation model')}"
                f"{cite(call.output.data['evidence'])}.",
            ),
        ]
        for model in models:
            responds = (
                f"responds to {fmt.listing(model['responds_to'])}"
                if model["responds_to"]
                else "responds to no scenario change"
            )
            blocks.append(
                text(
                    "detail",
                    f"{model['name']} ({model['version']}, {model['status']}) "
                    f"{responds}{cite(model['evidence'])}.",
                )
            )
        blocks.extend(call.output.display)
        return Draft(
            status="answered",
            headline=f"{plural(len(models), 'registered model')}",
            blocks=blocks,
            follow_ups=["What scenario templates are there?"],
        )

    def _templates(self) -> Draft:
        call = self.call("list_templates")
        if not call.ok or call.output is None:
            return self.failure(call, "the templates")
        data = call.output.data
        templates = data["templates"]
        blocks: list[Block] = [
            text(
                "answer",
                f"The Scenario Lab offers {plural(len(templates), 'template')}"
                f"{cite(data['evidence'])}.",
            ),
        ]
        for item in templates[:8]:
            blocks.append(
                text(
                    "detail",
                    f"{item['title']}: “{policy.data_text(item['question'], 200)}”"
                    f"{cite(item['evidence'])}",
                )
            )
        if data["unavailable"]:
            blocks.append(
                notice(
                    "limitation",
                    "Not yet supported",
                    "; ".join(f"{u['title']}: {u['reason']}" for u in data["unavailable"]),
                )
            )
        blocks.extend(call.output.display)
        return Draft(
            status="answered",
            headline=f"{plural(len(templates), 'template')}",
            blocks=blocks,
            follow_ups=["Which models are there?"],
        )

    def _data_coverage(self) -> Draft:
        call = self.call("get_data_coverage")
        if not call.ok or call.output is None:
            return self.failure(call, "RUMIN's data")
        data = call.output.data
        summary = self.ledger.get(data["evidence"])
        values = summary.values if summary else {}
        with_data = [item for item in data["series"] if item["stored_values"]]
        blocks: list[Block] = [
            text(
                "answer",
                f"RUMIN catalogues {plural(int(values.get('series', 0)), 'series', 'series')}, "
                f"of which {values.get('series_with_data', 0)} hold values: "
                f"{plural(int(values.get('observations', 0)), 'stored value')} in all"
                f"{cite(data['evidence'])}.",
            )
        ]
        for item in with_data[:6]:
            blocks.append(
                text(
                    "detail",
                    f"{item['name']}: {plural(item['stored_values'], 'value')}, "
                    f"{item['first'][:4]}–{item['last'][:4]}{cite(item['evidence'])}.",
                )
            )
        graph = data["graph"]
        blocks.append(
            text(
                "detail",
                (
                    f"The knowledge graph is built (build {graph['build']}) and "
                    f"{graph['freshness'].replace('_', ' ')}"
                    if graph["build"]
                    else "The knowledge graph has not been built"
                )
                + f"; {plural(int(values.get('scenarios', 0)), 'scenario')} and "
                f"{plural(int(values.get('executions', 0)), 'execution')} are stored"
                f"{cite(data['evidence'])}.",
            )
        )
        blocks.extend(call.output.display)
        blocks.append(notice("limitation", "Stored, not live", policy.LIVE_DATA))
        return Draft(
            status="answered",
            headline=f"{values.get('series_with_data', 0)} of {values.get('series', 0)} "
            "catalogued series hold values",
            blocks=blocks,
            follow_ups=[
                f"Show {with_data[0]['name']}."
                if with_data
                else "Which companies are exposed to the rupee?",
                "What changed recently?",
            ],
        )

    def _search(self) -> Draft:
        route = self.route
        country = route.countries[0] if route.countries else None
        kinds = [
            kind
            for kind, word in (
                ("company", "compan"),
                ("industry", "industr"),
                ("variable", "variable"),
                ("series", "series"),
                ("instrument", "instrument"),
            )
            if word in route.text
        ]
        call = self.call(
            "search_records",
            query="",
            kinds=kinds or ["company"],
            country_key=country.key if country else None,
            limit=SEARCH_LIMIT,
        )
        if not call.ok or call.output is None:
            return self.failure(call, "the records")
        data = call.output.data
        matches = data["matches"]
        where = f" in {country.label}" if country else ""
        requested = kinds or ["company"]
        one, many = (
            SEARCH_NOUNS.get(requested[0], ("record", "records"))
            if len(requested) == 1
            else ("record", "records")
        )
        # The listing is capped: at the cap, it says it shows the first ones, not how many.
        capped = len(matches) >= SEARCH_LIMIT
        counted = f"{'the first ' if capped else ''}{plural(len(matches), one, many)}"
        blocks: list[Block] = [
            text(
                "answer",
                (
                    f"Listed here: {counted} RUMIN holds{where}"
                    if capped
                    else f"RUMIN holds {counted}{where}"
                )
                + cite(data["evidence"])
                + (f": {', '.join(m['name'] for m in matches[:12])}." if matches else "."),
            ),
        ]
        blocks.extend(call.output.display)
        first = next((m for m in matches if m["kind"] in ("company", "industry")), None)
        return Draft(
            status="answered" if matches else "no_data",
            headline=f"{counted[:1].upper()}{counted[1:]}{where}",
            blocks=blocks,
            follow_ups=[f"What does RUMIN know about {first['name']}?"]
            if first
            else ["What data does RUMIN hold?"],
        )

    # --- policy with context -------------------------------------------------------------------

    def _advice(self) -> Draft:
        entity = self.route.entities[0] if self.route.entities else None
        blocks: list[Block] = [text("policy", policy.ADVICE)]
        if entity is None:
            return Draft(
                status="declined",
                headline="RUMIN does not make investment decisions",
                blocks=blocks,
                follow_ups=self.starters(),
            )
        context = self._entity_overview()
        context.blocks = blocks + context.blocks
        context.status = "declined"
        context.headline = (
            f"RUMIN does not make investment decisions; here is the context it "
            f"holds on {entity.label}"
        )
        return context

    def _forecast(self) -> Draft:
        route = self.route
        blocks: list[Block] = [text("policy", policy.FORECAST)]
        follow = []
        variable = route.variables[0] if route.variables else None
        if route.series:
            history = self._series_history()
            history.blocks = blocks + history.blocks
            history.status = "declined"
            history.headline = "RUMIN does not forecast; here is what it has stored"
            if variable is not None:
                history.follow_ups = [
                    f"What if {the(variable.label)} rises {example_change(variable)}?",
                    *history.follow_ups,
                ]
            return history
        related_series = [
            term
            for term in self.vocabulary.of_kind("series")
            if variable is not None and term.variable == variable.record_id
        ]
        if variable is not None and related_series:
            # What RUMIN has stored for the variable, instead of a forecast of it.
            route.series = related_series[:1]
            history = self._series_history()
            history.blocks = blocks + history.blocks
            history.status = "declined"
            history.headline = "RUMIN does not forecast; here is what it has stored"
            history.follow_ups = [
                f"What if {the(variable.label)} rises {example_change(variable)}?",
                *history.follow_ups,
            ]
            return history
        if variable is not None:
            follow = [
                f"What if {the(variable.label)} rises {example_change(variable)}?",
                f"Which companies does {the(variable.label)} reach?",
            ]
            call = self.call("get_variable_reach", variable_key=variable.key)
            if call.ok and call.output is not None:
                related = call.output.data["related_series"]
                if not related:
                    blocks.append(
                        text(
                            "detail",
                            f"RUMIN stores no series for {the(variable.label)}"
                            f"{cite(call.output.data['variable']['evidence'])}; a "
                            "scenario can still simulate a stated change to it.",
                        )
                    )
        return Draft(
            status="declined",
            headline="RUMIN does not forecast",
            blocks=blocks,
            follow_ups=follow or self.starters(),
            focus={"subject": variable.key, "variable": variable.key} if variable else {},
        )
