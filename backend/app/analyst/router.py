"""Reading a question: what is asked (the **intent**), about what (records named, or taken
from the conversation's focus), with which changes, periods and horizon.

The router is rules over words, not a language model, so the same question always routes
the same way and every decision can be listed (``Route.reasons``). When it cannot tell what
is meant — no subject, or a name that fits several records — it asks, with choices, rather
than guessing. Every reading that is not literal is kept as an assumption the answer states.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.analyst import parsing
from app.analyst.context import Focus
from app.analyst.parsing import Magnitude, Periods
from app.analyst.policy import Screening, screen
from app.analyst.vocabulary import Mention, Term, Vocabulary, normalise, the

INTENTS = (
    "capabilities",
    "entity_overview",
    "exposure",
    "compare_exposure",
    "variable_reach",
    "connection",
    "series_history",
    "period_change",
    "changes",
    "findings",
    "scenario_results",
    "explain_line",
    "what_if",
    "models",
    "templates",
    "data_coverage",
    "search",
    "advice",
    "forecast",
    "live_data",
    "injection",
    "secrets",
    "unsupported",
    "clarify",
)

# Intents that need a company or an industry.
NEEDS_ENTITY = {"entity_overview", "exposure", "compare_exposure"}
LINES = (
    ("profit_before_tax", r"profit\s+before\s+tax|\bpbt\b|pre-?tax\s+profit"),
    ("operating_profit", r"operating\s+profit|\bebit\b|operating\s+income|\bprofit\b|margin"),
    ("interest_expense", r"interest(?:\s+(?:expense|cost|costs|bill))?"),
    ("operating_costs", r"operating\s+costs?|\bcosts?\b|expenses?|fuel\s+bill|fuel\s+costs?"),
    ("revenue", r"revenue|sales|\bincome\b|fares?"),
)
CHANNELS = (
    ("financing", r"financ\w*|funding|borrow\w*|\bdebt\b|interest"),
    ("revenue", r"revenue|sales|income|fares?|earnings"),
    ("costs", r"\bcosts?\b|expenses?|input\s+prices?|margins?"),
)

_W = re.compile
CAPABILITIES = _W(
    r"^(?:help|hi|hello|hey)\b|what\s+can\s+(?:you|i|the\s+analyst)\s+(?:do|ask)|how\s+do\s+"
    r"(?:you|i)\s+(?:work|use)|what\s+(?:are\s+)?you\s+(?:able|for)|what\s+do\s+you\s+know\b"
    r"(?!\s+about)|what\s+kinds?\s+of\s+questions"
)
FOLLOW_UP = _W(r"^(?:and|also|what\s+about|how\s+about|same\s+for|now|then|ok(?:ay)?|and\s+for)\b")
PRONOUN = _W(
    r"\b(?:it|its|they|their|them|the\s+same|this\s+company|that\s+company|the\s+company|"
    r"this\s+one|that\s+one|the\s+variable|the\s+series|this\s+series|that\s+series)\b"
)
WHAT_IF = _W(
    r"\bif\b|\bsuppose\b|\bassum(?:e|ing)\b|\bscenario\b|\bwhat\s+happens\b|\bwhat\s+would\b"
    r"|\bimpact\b|\beffect\b|\bshock\b|\bsimulat\w*|\bhit\b|\bhappen\b"
)
EXPLAIN = _W(r"\bwhy\b|\bexplain\b|\bwhat\s+drove\b|\bdrivers?\s+of\b|\bbreak\s*down\b")
RESULT_WORDS = _W(r"\b(?:scenarios?|executions?|simulations?|runs?|results?|simulated|lab)\b")
LATEST_RESULTS = _W(
    r"\b(?:latest|last|recent|stored|saved|previous|my)\b.*\b(?:scenarios?|executions?|"
    r"simulations?|runs?|results?)\b|\bwhat\s+did\s+(?:the\s+|my\s+|that\s+)?(?:scenario|"
    r"simulation|execution)\b|\bresults?\s+(?:of|for)\b|\bscenarios?\s+(?:on|for)\b"
)
CONNECTION = _W(
    r"\bconnect\w*|\blink\w*|\brelationships?\s+between\b|\brelated\s+to\b|\bpath\w*\b"
    r"|\bchain\b|\btied\s+to\b|\bhow\s+(?:is|are|does|do)\b.*\b(?:relate|connected|linked)"
)
COMPARE = _W(r"\bcompare\w*|\bversus\b|\bvs\.?\b|\bdifference\s+between\b|\bbetween\b.*\band\b")
REACH = _W(
    r"\b(?:which|what|who|list)\b.*\b(?:companies|firms|businesses|industries|sectors|names|"
    r"entities)\b|\bwho\s+is\b|\bwho\s+are\b|\bexposed\s+to\b|\baffected\s+by\b|\bsensitive\s+"
    r"to\b|\breach\w*|\bhit\s+by\b|\bdepend\w*\s+on\b"
)
EXPOSURE = _W(
    r"\bexpos\w*|\bsensitiv\w*|\baffect\w*|\bimpact\w*|\brisks?\b|\bvulnerab\w*|\bdepend\w*"
    r"|\bdrivers?\b|\bvariables?\b|\bwhat\s+(?:moves|drives|affects)\b|\bchannels?\b"
)
HISTORY = _W(
    r"\bhistor\w*|\btrend\w*|\bover\s+time\b|\bsince\b|\bvalues?\b|\bdata\b|\bchart\b|\bplot\b"
    r"|\bshow\b|\bpast\b|\bhow\s+has\b|\bseries\b|\blevels?\b|\bvolatil\w*|\blatest\b"
)
CHANGE_WORDS = _W(
    r"\bchange\w*|\bmove\w*|\brise\b|\brose\b|\bfall\b|\bfell\b|\bincrease\w*|\bdecrease\w*"
    r"|\bdifference\b|\bhow\s+much\b|\bgrew\b|\bgrowth\b|\bdeclin\w*|\bup\b|\bdown\b"
)
FINDINGS = _W(
    r"\bfindings?\b|\binsights?\b|\bsignals?\b|\bhighlights?\b|\bstands?\s+out\b"
    r"|\bwhat\s+matters\b|\bkey\s+points?\b|\bunusual\b|\bnotable\b|\bred\s+flags?\b"
    r"|\bwhat\s+should\s+i\s+(?:look|know|watch)\b|\bworth\s+(?:knowing|noting)\b"
    r"|\bsummar\w*|\bbrief\b"
)
CHANGES = _W(
    r"\bwhat\s+(?:has\s+)?changed\b|\bchanges\b|\brecent(?:ly)?\b|\bnew\s+data\b|\bupdated?\b"
    r"|\brevis\w*|\bwhat\s+is\s+new\b|\bwhat's\s+new\b"
)
MODELS = _W(
    r"\bmodels?\b|\bwhat\s+can\s+(?:you|rumin|i)\s+simulate\b|\bsimulation\s+models?\b"
    r"|\bwhich\s+(?:changes|variables)\s+can\s+be\s+simulated\b"
)
TEMPLATES = _W(r"\btemplates?\b|\bready[\s-]made\b|\bscenario\s+ideas\b|\bexample\s+scenarios\b")
COVERAGE = _W(
    r"\bwhat\s+data\b|\bwhich\s+data\b|\bcoverage\b|\bdata\s+sources?\b|\bdatasets?\b"
    r"|\bwhat\s+series\b|\bwhich\s+series\b|\bmissing\s+data\b|\bdata\s+gaps?\b"
    r"|\bdo\s+you\s+have\s+(?:any\s+)?data\b|\bhow\s+much\s+data\b|\bwhat\s+do\s+you\s+hold\b"
)
SEARCH = _W(
    r"\b(?:list|find|search|show\s+me|which|what)\b.*\b(?:companies|industries|variables|"
    r"series|instruments|firms|countries)\b|\b(?:companies|firms)\s+(?:in|from)\b"
)
OVERVIEW = _W(
    r"\btell\s+me\s+about\b|\bwhat\s+do\s+(?:you|we|rumin)\s+know\s+about\b|\bwho\s+is\b"
    r"|\bwhat\s+is\b|\boverview\b|\bprofile\b|\bdescribe\b|\bdossier\b"
)
RUPEE_ALIASES = {"rupee", "the rupee", "indian rupee"}


@dataclass
class Change:
    variable: Term
    change_type: str  # percent_change | absolute_change
    value: Decimal
    text: str
    assumption: str | None = None
    figures: dict[str, Decimal] = field(default_factory=dict)  # stated readings, for evidence

    def to_json(self) -> dict[str, str]:
        return {
            "variable_id": self.variable.record_id,
            "change_type": self.change_type,
            "value": format(self.value.normalize(), "f"),
        }


@dataclass
class Clarification:
    question: str
    options: list[tuple[str, str]]  # (label, question to ask instead)


@dataclass
class Route:
    intent: str
    question: str
    text: str
    screening: Screening
    entities: list[Term] = field(default_factory=list)
    variables: list[Term] = field(default_factory=list)
    series: list[Term] = field(default_factory=list)
    countries: list[Term] = field(default_factory=list)
    models: list[Term] = field(default_factory=list)
    templates: list[Term] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    periods: Periods = field(default_factory=Periods)
    horizon: int | None = None
    line: str | None = None
    channel: str | None = None
    kinds: list[str] = field(default_factory=list)  # record kinds a search asks for
    clarification: Clarification | None = None
    assumptions: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    from_focus: list[str] = field(default_factory=list)
    alternatives: list[Term] = field(default_factory=list)  # other series that also fit
    series_named: bool = False  # a series named as such, not only by what it measures
    untied: int = 0  # figures written but not tied to any variable
    untied_figures: list[str] = field(default_factory=list)  # as written ("30%")
    untied_values: list[Decimal] = field(default_factory=list)  # as read (30)
    untied_units: list[str] = field(default_factory=list)  # percent | points | absolute

    @property
    def entity(self) -> Term | None:
        return self.entities[0] if self.entities else None

    @property
    def variable(self) -> Term | None:
        return self.variables[0] if self.variables else None

    def to_json(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "entities": [term.key for term in self.entities],
            "variables": [term.key for term in self.variables],
            "series": [term.key for term in self.series],
            "countries": [term.key for term in self.countries],
            "changes": [change.to_json() for change in self.changes],
            "periods": {
                "start": self.periods.start,
                "end": self.periods.end,
                "years": list(self.periods.years),
                "last": self.periods.last,
            },
            "horizon": self.horizon,
            "line": self.line,
            "channel": self.channel,
            "screening": list(self.screening.flags),
            "assumptions": self.assumptions,
            "reasons": self.reasons,
            "from_focus": self.from_focus,
        }


def _unique(terms: list[Term]) -> list[Term]:
    seen: dict[str, Term] = {}
    for term in terms:
        seen.setdefault(term.key, term)
    return list(seen.values())


def _groups(mentions: list[Mention]) -> list[list[Mention]]:
    """Mentions of the same words grouped together (one group per place in the text)."""
    by_span: dict[tuple[int, int], list[Mention]] = {}
    for mention in mentions:
        by_span.setdefault((mention.start, mention.end), []).append(mention)
    return [by_span[span] for span in sorted(by_span)]


def _pick(text: str, table: tuple[tuple[str, str], ...]) -> str | None:
    for value, pattern in table:
        if re.search(pattern, text):
            return value
    return None


def _rupee_note(word: str, magnitude: Magnitude, sign: int) -> tuple[str, Decimal | None]:
    """The stated reading of a rupee move as a USD/INR change, and the exact USD/INR change
    it strictly corresponds to (for the answer's evidence)."""
    size = abs(magnitude.value)
    note = (
        f"Read 'the rupee {word} {magnitude.text}' as USD/INR {'up' if sign > 0 else 'down'} "
        f"{format(size.normalize(), 'f')} %, as the Scenario Lab's rupee template does."
    )
    if magnitude.unit != "percent" or not Decimal(0) < size < Decimal(100):
        return note, None
    # A rupee x % weaker in dollars is a USD/INR x / (100 − x) higher; x % stronger,
    # x / (100 + x) lower.
    exact = size / (100 - size) * 100 if sign > 0 else size / (100 + size) * 100
    rounded = exact.quantize(Decimal("0.01"))
    note += (
        f" Strictly, a rupee {format(size.normalize(), 'f')} % "
        f"{'weaker' if sign > 0 else 'stronger'} in dollar terms is a USD/INR "
        f"{format(rounded, 'f')} % {'higher' if sign > 0 else 'lower'}."
    )
    return note, rounded


def _change(
    text: str,
    variable: Term,
    magnitude: Magnitude,
    subject: tuple[int, int] | None,
    alias: str | None,
    previous: Decimal | None = None,
) -> tuple[Change | None, str | None]:
    """One written change for ``variable``, or why it was left out."""
    value = magnitude.value
    assumption: str | None = None
    extra: dict[str, Decimal] = {}
    direction = (
        parsing.direction_near(text, subject, (magnitude.start, magnitude.end))
        if subject is not None
        else parsing.direction_near(
            text, (magnitude.start, magnitude.start), (magnitude.start, magnitude.end)
        )
    )
    if not magnitude.signed:
        if direction is None:
            if previous is not None and previous < 0:
                value = -value
                assumption = (
                    f"Read '{magnitude.text}' as a new size for the previous change to "
                    f"{variable.label}, in the same direction (down)."
                )
            elif previous is not None:
                assumption = (
                    f"Read '{magnitude.text}' as a new size for the previous change to "
                    f"{variable.label}, in the same direction (up)."
                )
            else:
                assumption = f"Read '{magnitude.text}' for {variable.label} as a rise."
        else:
            sign, word = direction
            if alias in RUPEE_ALIASES and variable.record_id == "var_usd_inr":
                sign = -sign  # a weaker rupee is a higher USD/INR
                assumption, strict = _rupee_note(word, magnitude, sign)
                if strict is not None:
                    extra["usd_inr.strict_equivalent"] = strict
            value = value * sign
    is_rate = bool(variable.unit and "percent" in variable.unit.lower())
    if magnitude.unit == "points":
        if not is_rate:
            return None, (
                f"'{magnitude.text}' is in points, but {variable.label} is not a rate; it was "
                "left out."
            )
        change_type = "absolute_change"
    elif magnitude.unit == "absolute":
        change_type = "absolute_change"
    elif is_rate:
        change_type = "absolute_change"
        reading = (
            f"Read '{magnitude.text}' on {variable.label}, a rate, as "
            f"{format(abs(value).normalize(), 'f')} percentage points."
        )
        assumption = f"{assumption} {reading}" if assumption else reading
    else:
        change_type = "percent_change"
    return Change(variable, change_type, value, magnitude.text, assumption, extra), None


def _changes(
    text: str,
    mentions: list[Mention],
    magnitudes: list[Magnitude],
    vocabulary: Vocabulary,
    focus: Focus,
) -> tuple[list[Change], list[str], bool, list[parsing.Magnitude]]:
    """Tie each written change to the variable it is about (the nearest one before it in
    the same clause, else the nearest after it). A bare figure in a follow-up ("what about
    30 %?") resizes the conversation's single previous change. Returns the changes, notes
    on what was left out, whether the conversation's change was used, and the figures tied
    to no variable."""
    variables = [item for item in mentions if item.term.kind == "variable"]
    years = parsing.year_spans(text)
    written = [
        item for item in magnitudes if not any(start <= item.start < end for start, end in years)
    ]
    changes: list[Change] = []
    notes: list[str] = []
    untied: list[parsing.Magnitude] = []
    if not variables and len(written) == 1 and len(focus.changes) == 1:
        previous = focus.changes[0]
        term = vocabulary.by_record(previous.get("variable_id", ""))
        if term is not None:
            try:
                before = Decimal(previous.get("value", ""))
            except ArithmeticError:
                before = None
            change, note = _change(text, term, written[0], None, None, before)
            return ([change] if change else []), ([note] if note else []), True, []
    for magnitude in written:
        before_it = [item for item in variables if item.end <= magnitude.start]
        after_it = [item for item in variables if item.start >= magnitude.end]
        mention = before_it[-1] if before_it else (after_it[0] if after_it else None)
        if mention is None:
            notes.append(
                f"'{magnitude.text}' is not tied to a variable RUMIN holds, so it was left out."
            )
            untied.append(magnitude)
            continue
        change, note = _change(
            text, mention.term, magnitude, (mention.start, mention.end), mention.text
        )
        if note:
            notes.append(note)
        if change is None:
            continue
        if any(item.variable.key == change.variable.key for item in changes):
            notes.append(
                f"A second change to {change.variable.label} ('{magnitude.text}') was left out."
            )
            continue
        changes.append(change)
    return changes, notes, False, untied


# Variables offered when a what-if names a size but no variable, by the size's unit; only
# those RUMIN holds are offered. A rate in percent moves in points, a price in percent.
EXAMPLE_VARIABLES = {
    "percent": ("var_brent_crude", "var_usd_inr"),
    "points": ("var_rbi_repo_rate",),
}
POINTS = _W(r"\bpp\b|percentage\s+points?|\bbps?\b|basis\s+points?")


def _clarify_change(found: Route, vocabulary: Vocabulary) -> Clarification:
    """A what-if without a variable: ask which one, keeping the size and company written."""
    entity = next((term for term in found.entities if term.kind == "company"), None)
    subject = f" for {entity.label}" if entity else ""
    figure = found.untied_figures[0] if found.untied_figures else None
    if figure is None:
        return Clarification(
            "Which change should be simulated? Name a variable and a size.",
            [
                ("Brent crude +20 %", f"What if Brent crude rises 20 %{subject}?"),
                ("Rupee 10 % weaker", f"What if the rupee weakens 10 %{subject}?"),
                (
                    "Repo rate +1.5 pp",
                    f"What if the RBI repo rate rises 1.5 percentage points{subject}?",
                ),
            ],
        )
    unit = "points" if POINTS.search(figure) else "percent"
    options = [
        (f"{term.label} by {figure}", f"What if {the(term.label)} changes by {figure}{subject}?")
        for term in (vocabulary.by_record(record) for record in EXAMPLE_VARIABLES[unit])
        if term is not None
    ]
    return Clarification(f"Which variable should change by {figure}?", options)


def _clarify_subject(vocabulary: Vocabulary, kind: str, template: str) -> Clarification:
    terms = vocabulary.of_kind(kind)
    options = [
        (term.label, template.format(name=term.label, the_name=the(term.label)))
        for term in terms[:6]
    ]
    return Clarification(f"Which {kind} do you mean?", options)


def route(question: str, vocabulary: Vocabulary, focus: Focus | None = None) -> Route:
    focus = focus or Focus()
    text = normalise(question)
    screening = screen(text)
    found = Route(intent="unsupported", question=question, text=text, screening=screening)

    if screening.has("injection"):
        found.intent = "injection"
        found.reasons.append("The question contains instructions aimed at the Analyst.")
        return found
    if screening.has("secrets"):
        found.intent = "secrets"
        found.reasons.append("The question asks for keys, passwords or settings.")
        return found
    if not text:
        found.reasons.append("The question is empty.")
        return found

    mentions = vocabulary.find(text)
    groups = _groups(mentions)
    by_kind: dict[str, list[Term]] = {}
    for mention in mentions:
        by_kind.setdefault(mention.term.kind, []).append(mention.term)
    companies = _unique(by_kind.get("company", []))
    industries = _unique(by_kind.get("industry", []))
    found.entities = _unique(companies + industries)
    found.variables = _unique(by_kind.get("variable", []))
    found.series = _unique(by_kind.get("series", []))
    found.series_named = any(
        mention.term.kind == "series" and mention.by != "measure" for mention in mentions
    )
    found.countries = _unique(by_kind.get("country", []))
    found.models = _unique(by_kind.get("model", []))
    found.templates = _unique(by_kind.get("template", []))
    found.periods = parsing.periods(text)
    found.horizon = parsing.horizon_months(text)
    found.line = _pick(text, LINES)
    found.channel = _pick(text, CHANNELS)
    changes, notes, resized, untied = _changes(
        text, mentions, parsing.magnitudes(text), vocabulary, focus
    )
    found.changes = changes
    found.untied = len(untied)
    found.untied_figures = [item.text for item in untied]
    found.untied_values = [item.value for item in untied]
    found.untied_units = [item.unit for item in untied]
    if resized:
        found.from_focus.append("changes")
    found.assumptions = [change.assumption for change in changes if change.assumption] + notes

    # A follow-up that names no subject ("and its revenue exposure?") is about the
    # conversation's subject.
    named = found.entities or found.variables or found.series_named or found.countries
    follow_up = bool(PRONOUN.search(text) or FOLLOW_UP.search(text))
    if not named and follow_up and focus.subject:
        subject = vocabulary.get(focus.subject)
        if subject is not None:
            found.from_focus.append("subject")
            if subject.kind in ("company", "industry"):
                found.entities = [subject]
            elif subject.kind == "variable":
                found.variables = [subject]
            elif subject.kind == "series":
                found.series = [subject]
                found.series_named = True

    # Ambiguous names: the same words fit several companies or industries.
    for group in groups:
        entities = [item.term for item in group if item.term.kind in ("company", "industry")]
        if len(entities) > 1:
            found.intent = "clarify"
            found.clarification = Clarification(
                f"'{group[0].text}' fits more than one record. Which do you mean?",
                [(term.label, f"{question} ({term.label})") for term in entities],
            )
            found.reasons.append(f"'{group[0].text}' names {len(entities)} records.")
            return found

    intent = _intent(found, focus)
    found.intent = intent
    _resolve_subjects(found, vocabulary, focus)
    return found


def _intent(found: Route, focus: Focus) -> str:
    text = found.text
    has_entity = bool(found.entities)
    has_variable = bool(found.variables)
    has_series = bool(found.series)
    reasons = found.reasons

    if "changes" in found.from_focus and focus.intent == "what_if":
        reasons.append("Resizes the previous what-if.")
        return "what_if"
    if CAPABILITIES.search(text) and not (has_entity or has_variable or has_series):
        reasons.append("Asks what the Analyst can do.")
        return "capabilities"
    if found.changes and (WHAT_IF.search(text) or found.screening.conditional):
        reasons.append("Names a change to a variable in a conditional question.")
        return "what_if"
    if found.untied and WHAT_IF.search(text) and not found.changes:
        reasons.append("A conditional question with a figure tied to no variable.")
        return "what_if"
    if found.untied and FOLLOW_UP.search(text) and not found.changes and not has_series:
        reasons.append("A follow-up with a figure tied to no variable and no change to resize.")
        return "what_if"
    if found.screening.has("advice"):
        reasons.append("Asks for an investment decision.")
        return "advice"
    if found.screening.has("forecast") and not found.screening.conditional:
        reasons.append("Asks about the future without stating a change.")
        return "forecast"
    if TEMPLATES.search(text):
        reasons.append("Asks for scenario templates.")
        return "templates"
    if MODELS.search(text) and not found.changes:
        reasons.append("Asks which models exist.")
        return "models"
    if (
        EXPLAIN.search(text)
        and found.line
        and (RESULT_WORDS.search(text) or focus.execution_id or has_entity)
    ):
        reasons.append(f"Asks why a line ({found.line}) of a simulation changed.")
        return "explain_line"
    if LATEST_RESULTS.search(text) or (
        RESULT_WORDS.search(text) and has_entity and not EXPOSURE.search(text)
    ):
        reasons.append("Asks about stored scenario results.")
        return "scenario_results"
    subjects = len(found.entities) + len(found.variables) + len(found.series) + len(found.countries)
    if CONNECTION.search(text) and subjects >= 2:
        reasons.append("Asks how two records are connected.")
        return "connection"
    if COMPARE.search(text) and len(found.entities) >= 2:
        reasons.append("Compares two or more companies or industries.")
        return "compare_exposure"
    if found.screening.has("live_data") and (has_variable or has_series):
        reasons.append("Asks for a live value.")
        return "live_data"
    if (has_series or has_variable) and not has_entity:
        two_periods = len(found.periods.years) >= 2 or (
            found.periods.start is not None and found.periods.end is not None
        )
        if two_periods and CHANGE_WORDS.search(text):
            reasons.append("Asks for the change of a series between two periods.")
            return "period_change"
        if has_variable and REACH.search(text) and not found.series_named:
            reasons.append("Asks which companies a variable reaches.")
            return "variable_reach"
        if found.series_named or HISTORY.search(text) or not found.periods.empty:
            reasons.append("Asks for the stored values of a series.")
            return "series_history"
        if has_variable:
            reasons.append("Names a variable: which companies it reaches.")
            return "variable_reach"
        if FINDINGS.search(text) is None and CHANGES.search(text) is None:
            reasons.append("Names what a stored series measures.")
            return "series_history"
    if has_entity and has_variable and EXPOSURE.search(text):
        reasons.append("Asks how a variable reaches a company or industry.")
        return "exposure"
    if has_entity and EXPOSURE.search(text):
        reasons.append("Asks about the exposure of a company or industry.")
        return "exposure"
    if FINDINGS.search(text):
        reasons.append("Asks for findings.")
        return "findings"
    if CHANGES.search(text):
        if has_entity:
            reasons.append("Asks what changed for a company or industry: its findings.")
            return "findings"
        reasons.append("Asks what changed.")
        return "changes"
    if TEMPLATES.search(text):
        reasons.append("Asks for scenario templates.")
        return "templates"
    if MODELS.search(text):
        reasons.append("Asks which models exist.")
        return "models"
    if COVERAGE.search(text):
        reasons.append("Asks what data RUMIN holds.")
        return "data_coverage"
    if EXPOSURE.search(text) and REACH.search(text) and not (has_entity or has_series):
        reasons.append("Asks which companies are exposed, without naming a variable.")
        return "variable_reach"
    if SEARCH.search(text) and not has_entity:
        reasons.append("Asks for a list of records.")
        return "search"
    if has_entity:
        reasons.append("Names a company or industry.")
        return "entity_overview"
    if EXPOSURE.search(text) and not (has_variable or has_series):
        reasons.append("Asks about exposure without naming a company or industry.")
        return "exposure"
    if has_variable:
        reasons.append("Names a variable.")
        return "variable_reach"
    if found.countries:
        reasons.append("Names a country.")
        return "search"
    if found.models:
        return "models"
    if found.templates:
        return "templates"
    # A follow-up with no subject of its own: the conversation's last question, again.
    if focus.intent and (FOLLOW_UP.search(text) or PRONOUN.search(text) or found.changes):
        reasons.append(f"A follow-up to the previous question ({focus.intent}).")
        return focus.intent
    if found.screening.has("live_data"):
        return "live_data"
    reasons.append("No rule matched the question.")
    return "unsupported"


def _resolve_subjects(found: Route, vocabulary: Vocabulary, focus: Focus) -> None:
    """Fill a missing subject from the conversation, pick among series, or ask."""
    intent = found.intent
    pronoun = bool(PRONOUN.search(found.text)) or bool(FOLLOW_UP.search(found.text))

    def from_focus(key: str | None, label: str) -> Term | None:
        if key is None:
            return None
        term = vocabulary.get(key)
        if term is not None:
            found.from_focus.append(label)
        return term

    wants_entity = intent in NEEDS_ENTITY or intent in (
        "scenario_results",
        "explain_line",
        "findings",
    )
    if wants_entity and not found.entities and (pronoun or intent in NEEDS_ENTITY or found.line):
        term = from_focus(focus.entity, "entity")
        if term is not None:
            found.entities = [term]
    if intent in ("what_if",) and not found.entities:
        term = from_focus(focus.entity, "entity") if (pronoun or focus.entity) else None
        if term is not None and term.kind == "company":
            found.entities = [term]
    if intent in ("variable_reach", "live_data") and not found.variables and not found.series:
        term = from_focus(focus.variable, "variable")
        if term is not None:
            found.variables = [term]
    if intent in ("series_history", "period_change", "live_data"):
        _pick_series(found, vocabulary, focus, pronoun)
    if intent == "what_if" and not found.changes and focus.changes:
        for item in focus.changes:
            term = vocabulary.by_record(item.get("variable_id", ""))
            try:
                value = Decimal(item.get("value", ""))
            except ArithmeticError:
                continue
            if term is not None and item.get("change_type") in (
                "percent_change",
                "absolute_change",
            ):
                found.changes.append(
                    Change(term, item["change_type"], value, "the previous change")
                )
        if found.changes:
            found.from_focus.append("changes")
    if intent == "what_if" and found.horizon is None and focus.horizon and pronoun:
        found.horizon = focus.horizon
    if intent == "compare_exposure" and len(found.entities) == 1 and focus.entity:
        other = from_focus(focus.entity, "entity")
        if other is not None and other.key != found.entities[0].key:
            found.entities = [other, *found.entities]

    if intent in NEEDS_ENTITY and not found.entities:
        found.intent = "clarify"
        found.clarification = _clarify_subject(
            vocabulary, "company", "What does RUMIN know about {name}?"
        )
        found.reasons.append("No company or industry is named, and none is in focus.")
    elif intent == "compare_exposure" and len(found.entities) < 2:
        found.intent = "exposure"
    elif intent == "variable_reach" and not found.variables:
        found.intent = "clarify"
        found.clarification = _clarify_subject(
            vocabulary, "variable", "Which companies are exposed to {the_name}?"
        )
        found.reasons.append("No economic variable is named, and none is in focus.")
    elif intent in ("series_history", "period_change") and not found.series:
        if found.clarification is None:
            found.clarification = _clarify_subject(vocabulary, "series", "Show {name}.")
        found.intent = "clarify"
    elif intent == "what_if" and not found.changes and not focus.changes:
        found.intent = "clarify"
        found.clarification = _clarify_change(found, vocabulary)
    elif intent == "connection" and (
        len(found.entities) + len(found.variables) + len(found.series) + len(found.countries) < 2
    ):
        found.intent = "clarify"
        found.clarification = Clarification(
            "Which two records should be connected?",
            [
                (
                    "Brent crude and Aerisca Airways",
                    "How is Brent crude connected to Aerisca Airways?",
                ),
                ("The repo rate and Anvaya Bank", "How is the repo rate connected to Anvaya Bank?"),
            ],
        )


def _pick_series(found: Route, vocabulary: Vocabulary, focus: Focus, pronoun: bool) -> None:
    """The series a question means: named with its country, or the related series of a
    named variable; other series that also fit are kept as alternatives."""
    if found.series:
        candidates = found.series
        if found.countries:
            wanted = {term.record_id for term in found.countries}
            chosen = [term for term in candidates if term.country in wanted]
            candidates = chosen or candidates
        if len(candidates) > 1:
            related = [
                term
                for term in candidates
                if any(term.variable == variable.record_id for variable in found.variables)
            ]
            if len(related) == 1:
                found.alternatives = [term for term in candidates if term.key != related[0].key]
                candidates = related
                found.reasons.append("Took the series recorded for the named variable.")
            elif len({term.country for term in candidates}) > 1 or len(related) > 1:
                found.clarification = Clarification(
                    "More than one stored series fits. Which one?",
                    [(term.label, f"Show {term.label}.") for term in candidates[:6]],
                )
                found.series = []
                return
        found.series = candidates[:2] if found.intent == "period_change" else candidates[:1]
        return
    if found.variables:
        related = [
            term
            for term in vocabulary.of_kind("series")
            if term.variable in {variable.record_id for variable in found.variables}
        ]
        if related:
            found.series = related[:1]
            found.reasons.append("Took the series recorded as a related measure of the variable.")
            return
        return
    term = vocabulary.get(focus.series) if focus.series and pronoun else None
    if term is not None:
        found.series = [term]
        found.from_focus.append("series")
