"""The names a question can use for RUMIN's records.

Built on every turn from what RUMIN holds — companies, industries, countries and economic
variables (the reference data the graph is built from), stored series and instruments, the
registered models and the Scenario Lab's templates — so a record added to RUMIN is
recognised without any change here. Keys are the knowledge graph's node keys
(``company:co_aerisca_airways``, ``variable:var_usd_inr``, ``series:wb-ind-pa-nus-fcrf``).

Each record is found by its own name, by that name without qualifiers, and by the common
names in ``ALIASES`` (keyed by record id: the curated sample network is part of this
repository, so its ids are known). A name that fits several records (``"bank"``) is kept
for all of them, and the router asks which one is meant.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Country, EconomicSeries, EconomicVariable, Industry, Instrument
from app.scenario_lab.templates import TEMPLATES
from app.simulation.registry import REGISTRY

KINDS = (
    "company",
    "industry",
    "country",
    "variable",
    "series",
    "instrument",
    "model",
    "template",
)

# Common names for the curated sample network's records (see the module docstring).
ALIASES: dict[str, tuple[str, ...]] = {
    # Economic variables
    "var_brent_crude": ("brent", "brent crude", "crude", "crude oil", "oil price", "oil prices"),
    "var_jet_fuel": ("jet fuel", "atf", "aviation fuel", "aviation turbine fuel"),
    "var_henry_hub_gas": ("henry hub", "natural gas", "gas price", "gas prices"),
    "var_usd_inr": (
        "usd/inr",
        "usd-inr",
        "usdinr",
        "usd inr",
        "inr/usd",
        "rupee",
        "the rupee",
        "indian rupee",
        "rupee-dollar",
        "dollar-rupee",
        "exchange rate",
        "fx rate",
    ),
    "var_rbi_repo_rate": ("repo rate", "repo", "rbi rate", "rbi repo", "rbi policy rate"),
    "var_us_fed_funds": ("fed funds", "federal funds", "fed rate", "fed funds rate"),
    "var_india_cpi_inflation": ("india cpi", "cpi inflation", "india inflation", "inflation"),
    # Industries
    "ind_oil_gas_extraction": (
        "oil and gas extraction",
        "oil & gas",
        "oil and gas",
        "upstream",
        "oil producers",
        "oil producer",
    ),
    "ind_petroleum_refining": ("refining", "refiner", "refiners", "refineries", "refinery"),
    "ind_chemicals": ("chemicals", "chemical companies", "chemical industry"),
    "ind_power": ("power", "utilities", "utility", "electricity", "power companies"),
    "ind_land_transport": (
        "land transport",
        "logistics",
        "trucking",
        "road transport",
        "road haulage",
        "haulier",
        "hauliers",
    ),
    "ind_air_transport": ("airlines", "airline", "air transport", "aviation", "carriers"),
    "ind_it_services": ("it services", "software services", "it companies", "software"),
    "ind_banking": ("banks", "banking", "lenders"),
    # Countries
    "cty_in": ("india", "indian"),
    "cty_us": ("united states", "u.s.", "usa", "america", "american"),
    "cty_ae": ("united arab emirates", "uae", "emirates"),
}
# Short forms recognised only as written in capitals ("US", not the pronoun "us").
_CAPITALS = re.compile(r"(?<![A-Za-z0-9])(?:US|U\.S\.?)(?![A-Za-z0-9])")

# What each World Bank indicator measures, in the words people use (by indicator code).
MEASURES: dict[str, tuple[str, ...]] = {
    "fp-cpi-totl-zg": ("inflation", "consumer prices", "cpi", "cpi inflation"),
    "pa-nus-fcrf": ("exchange rate", "official exchange rate", "rupee", "usd/inr", "usd inr"),
    "fr-inr-lend": ("lending rate", "lending interest rate", "lending rates"),
    "fr-inr-rinr": ("real interest rate", "real rate", "real interest rates"),
    "ny-gdp-mktp-kd-zg": ("gdp growth", "growth", "economic growth", "real gdp growth"),
    "ny-gdp-mktp-cd": ("gdp", "gdp in dollars", "nominal gdp", "size of the economy"),
    "bn-cab-xoka-gd-zs": ("current account", "current account balance", "current account deficit"),
    "ne-exp-gnfs-zs": ("exports", "exports of goods and services", "export share"),
}
COUNTRY_BY_ISO3 = {"IND": "cty_in", "USA": "cty_us", "ARE": "cty_ae"}
# Words that are never a record's short name on their own.
STOP = {
    "the",
    "and",
    "bank",
    "power",
    "digital",
    "energy",
    "air",
    "refining",
    "logistics",
    "chemicals",
    "petroleum",
    "airways",
    "company",
    "group",
    "price",
    "rate",
}


_PLAIN = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "&": " and ",
    }
)


def normalise(text: str) -> str:
    """Lower case, plain quotes and dashes, '&' as 'and', single spaces. Every reading of a
    question (names, figures, periods) works on this form, so positions agree."""
    text = unicodedata.normalize("NFKC", text)
    text = _CAPITALS.sub("u.s.", text)
    text = text.translate(_PLAIN)
    text = re.sub(r"'s\b", "", text.lower())
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class Term:
    kind: str
    key: str
    record_id: str
    name: str  # normalised, for matching
    label: str  # as stored, for display
    aliases: tuple[str, ...]
    country: str | None = None  # a country record id (cty_…)
    measures: tuple[str, ...] = ()  # series: what it measures
    variable: str | None = None  # series: the variable it is a related measure of
    unit: str | None = None
    frequency: str | None = None
    category: str | None = None
    fictional: bool = False


@dataclass(frozen=True)
class Mention:
    term: Term
    start: int
    end: int
    text: str
    by: str  # "name", "alias" or "measure"


@dataclass
class Vocabulary:
    terms: list[Term] = field(default_factory=list)

    def of_kind(self, *kinds: str) -> list[Term]:
        return [term for term in self.terms if term.kind in kinds]

    def get(self, key: str) -> Term | None:
        return next((term for term in self.terms if term.key == key), None)

    def by_record(self, record_id: str) -> Term | None:
        return next((term for term in self.terms if term.record_id == record_id), None)

    def find(self, text: str) -> list[Mention]:
        """Every record named in ``text`` (already ``normalise``d): longer names win over
        shorter ones inside them; a name that fits several records is returned for each."""
        candidates: list[Mention] = []
        for term in self.terms:
            for alias, by in _forms(term):
                for match in _pattern(alias).finditer(text):
                    candidates.append(Mention(term, match.start(), match.end(), alias, by))
        candidates.sort(key=lambda item: (-(item.end - item.start), item.start))
        kept: list[Mention] = []
        for mention in candidates:
            overlaps = [
                other for other in kept if mention.start < other.end and other.start < mention.end
            ]
            if not overlaps:
                kept.append(mention)
            elif all(
                (other.start, other.end) == (mention.start, mention.end) for other in overlaps
            ) and all(other.term.key != mention.term.key for other in overlaps):
                kept.append(mention)  # the same words name another record too
        unique: dict[tuple[str, int], Mention] = {}
        for mention in kept:
            unique.setdefault((mention.term.key, mention.start), mention)
        return sorted(unique.values(), key=lambda item: (item.start, item.term.kind))


def _pattern(alias: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])")


def _forms(term: Term) -> list[tuple[str, str]]:
    forms = [(term.name, "name")]
    forms += [(alias, "alias") for alias in term.aliases if alias != term.name]
    forms += [(measure, "measure") for measure in term.measures]
    return [(alias, by) for alias, by in forms if alias]


def _plain(name: str) -> str:
    """A name without its parenthetical qualifiers: 'jet fuel price (u.s. gulf coast)' →
    'jet fuel price'."""
    return re.sub(r"\s*\([^)]*\)", "", name).strip(" ,-")


def _indicator(series_id: str) -> str:
    # "wb-ind-fp-cpi-totl-zg" → "fp-cpi-totl-zg"
    parts = series_id.split("-", 2)
    return parts[2] if len(parts) == 3 else series_id


def load(session: Session) -> Vocabulary:
    """The vocabulary of what RUMIN holds now."""
    terms: list[Term] = []
    companies = session.scalars(select(Company).order_by(Company.name)).all()
    firsts = Counter(normalise(row.name).split(" ")[0] for row in companies)
    for row in companies:
        name = normalise(row.name)
        first = name.split(" ")[0]
        short = (first,) if firsts[first] == 1 and len(first) >= 4 and first not in STOP else ()
        terms.append(
            Term(
                kind="company",
                key=f"company:{row.id.lower()}",
                record_id=row.id,
                name=name,
                label=row.name,
                aliases=(*short, *ALIASES.get(row.id, ())),
                country=row.country_id,
                fictional=row.is_fictional,
            )
        )
    for industry in session.scalars(select(Industry).order_by(Industry.name)):
        name = normalise(industry.name)
        terms.append(
            Term(
                kind="industry",
                key=f"industry:{industry.id.lower()}",
                record_id=industry.id,
                name=name,
                label=industry.name,
                aliases=tuple({_plain(name), *ALIASES.get(industry.id, ())} - {name}),
            )
        )
    for country in session.scalars(select(Country).order_by(Country.name)):
        terms.append(
            Term(
                kind="country",
                key=f"country:{country.id.lower()}",
                record_id=country.id,
                name=normalise(country.name),
                label=country.name,
                aliases=ALIASES.get(country.id, ()),
            )
        )
    for variable in session.scalars(select(EconomicVariable).order_by(EconomicVariable.name)):
        name = normalise(variable.name)
        plain = _plain(name)
        terms.append(
            Term(
                kind="variable",
                key=f"variable:{variable.id.lower()}",
                record_id=variable.id,
                name=name,
                label=variable.name,
                aliases=tuple(
                    dict.fromkeys(a for a in (plain, *ALIASES.get(variable.id, ())) if a != name)
                ),
                country=variable.country_id,
                unit=variable.unit,
                frequency=str(variable.frequency.value),
                category=str(variable.category.value),
            )
        )
    for series in session.scalars(select(EconomicSeries).order_by(EconomicSeries.name)):
        name = normalise(series.name)
        measures = MEASURES.get(_indicator(series.id))
        if measures is None:
            head = re.split(r"\s*[(,]|\s+-\s+", name)[0].strip()
            measures = (head,) if head and head != name else ()
        home = series.country_id or COUNTRY_BY_ISO3.get(series.country_iso3 or "")
        terms.append(
            Term(
                kind="series",
                key=f"series:{series.id.lower()}",
                record_id=series.id,
                name=name,
                label=series.name,
                aliases=(_plain(name),) if _plain(name) != name else (),
                country=home,
                measures=tuple(measures),
                variable=series.variable_id,
                unit=series.unit,
                frequency=str(series.frequency.value),
            )
        )
    for instrument in session.scalars(select(Instrument).order_by(Instrument.name)):
        terms.append(
            Term(
                kind="instrument",
                key=f"instrument:{instrument.id.lower()}",
                record_id=instrument.id,
                name=normalise(instrument.name),
                label=instrument.name,
                aliases=(normalise(instrument.symbol),) if len(instrument.symbol) >= 3 else (),
                country=instrument.country_id,
                unit=instrument.currency,
            )
        )
    for model in REGISTRY.latest():
        definition = model.definition
        name = normalise(definition.name)
        terms.append(
            Term(
                kind="model",
                key=f"model:{definition.id}",
                record_id=definition.id,
                name=name,
                label=definition.name,
                aliases=(definition.id.replace("_", " "),),
            )
        )
    for template in TEMPLATES:
        terms.append(
            Term(
                kind="template",
                key=f"template:{template.id}",
                record_id=template.id,
                name=normalise(template.title),
                label=template.title,
                aliases=(),
            )
        )
    return Vocabulary(terms)
