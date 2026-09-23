# Relationship type dictionary

The 18 edge types, as defined in `backend/app/domain/graph_types.py` and served by
`GET /api/v1/graph/types`. Each says what an edge *means*, which kinds of node it may
join, whether it has a direction, which evidence statuses it may carry — and what it does
**not** mean. The seven economic types keep the meaning Phase 1 gave them.

An edge reads as a sentence: *source* **label** *target*.

## Summary

| Type | Reads | Endpoints | Directed | Allowed evidence | Built by | In the sample graph |
|---|---|---|---|---|---|---|
| `supplies_to` | “supplies” | company → company; industry → industry | yes | evidence-backed, model assumption | R01 | 13 |
| `lends_to` | “lends to” | company → company | yes | evidence-backed, model assumption | R01 | 6 |
| `competes_with` | “competes with” | company → company | no | evidence-backed, model assumption | R01 | 1 |
| `affects_costs` | “affects costs of” | economic_variable → company; economic_variable → industry | yes | evidence-backed, model assumption | R01 | 7 |
| `affects_revenue` | “affects revenue of” | economic_variable → company; economic_variable → industry | yes | evidence-backed, model assumption | R01 | 6 |
| `affects_financing` | “affects financing costs of” | economic_variable → company; economic_variable → industry | yes | evidence-backed, model assumption | R01 | 3 |
| `influences` | “influences” | economic_variable → economic_variable | yes | model assumption | R01 | 5 |
| `in_industry` | “operates in” | company → industry | yes | analyst-created, evidence-backed | R02 | 12 |
| `domiciled_in` | “is domiciled in” | company → country | yes | analyst-created, evidence-backed | R03 | 12 |
| `measured_for` | “is measured for” | economic_variable → country | yes | analyst-created | R04 | 6 |
| `in_sector` | “belongs to” | industry → sector | yes | evidence-backed | R05 | 8 |
| `has_currency` | “has currency” | country → currency | yes | evidence-backed | R06 | 3 |
| `covers` | “covers” | data_series → country | yes | evidence-backed | R07 | 11 |
| `related_measure_of` | “is a related measure of” | data_series → economic_variable | yes | analyst-created | R08 | 2 |
| `expressed_in` | “is expressed in” | data_series → currency | yes | evidence-backed | R09 | 2 |
| `listed_on` | “is listed on” | instrument → market | yes | unverified | R10 | 0 |
| `quoted_in` | “is quoted in” | instrument → currency | yes | unverified | R11 | 0 |
| `associated_with` | “is associated with” | instrument → country | yes | unverified | R12 | 0 |

## Economic relationships (curated or assumed)

### `supplies_to` — “supplies”

- **Meaning.** The source provides goods or services that the target uses as inputs.
- **Joins.** company → company; industry → industry.
- **Evidence.** evidence-backed, model assumption. Built by rule R01.
- **Does not mean.** A recorded supply relationship. It does not say how large or how important it is.

### `lends_to` — “lends to”

- **Meaning.** The source (a lender) provides credit facilities to the target.
- **Joins.** company → company.
- **Evidence.** evidence-backed, model assumption. Built by rule R01.
- **Does not mean.** A recorded lending relationship. It says nothing about amounts, terms or risk.

### `competes_with` — “competes with”

- **Meaning.** Both entities sell similar products or services in the same market.
- **Joins.** company → company (undirected: stored once, read both ways).
- **Evidence.** evidence-backed, model assumption. Built by rule R01.
- **Does not mean.** The two sell similar products in the same market; it does not rank them.

### `affects_costs` — “affects costs of”

- **Meaning.** Changes in the source variable are assumed to change the target's operating or input costs.
- **Joins.** economic_variable → company; economic_variable → industry.
- **Evidence.** evidence-backed, model assumption. Built by rule R01.
- **Does not mean.** An assumed effect, not a measured one: it says nothing about size or timing, and entities of the same kind can be affected very differently. A connection is not evidence of causation.

### `affects_revenue` — “affects revenue of”

- **Meaning.** Changes in the source variable are assumed to change the target's revenue, through prices, volumes or currency translation.
- **Joins.** economic_variable → company; economic_variable → industry.
- **Evidence.** evidence-backed, model assumption. Built by rule R01.
- **Does not mean.** An assumed effect, not a measured one: it says nothing about size or timing, and entities of the same kind can be affected very differently. A connection is not evidence of causation.

### `affects_financing` — “affects financing costs of”

- **Meaning.** Changes in the source variable are assumed to change the target's cost of borrowing or refinancing.
- **Joins.** economic_variable → company; economic_variable → industry.
- **Evidence.** evidence-backed, model assumption. Built by rule R01.
- **Does not mean.** An assumed effect, not a measured one: it says nothing about size or timing, and entities of the same kind can be affected very differently. A connection is not evidence of causation.

### `influences` — “influences”

- **Meaning.** Changes in the source variable are assumed to transmit to the target variable.
- **Joins.** economic_variable → economic_variable.
- **Evidence.** model assumption. Built by rule R01.
- **Does not mean.** Assumed transmission between two variables, not a statistical or causal estimate. A connection is not evidence of causation.

## Structural links (classifications and record fields)

### `in_industry` — “operates in”

- **Meaning.** The company's primary industry (derived from the company record).
- **Joins.** company → industry.
- **Evidence.** analyst-created, evidence-backed. Built by rule R02.
- **Does not mean.** A primary-industry classification. A company can also operate in other industries.

### `domiciled_in` — “is domiciled in”

- **Meaning.** The company's country of domicile (derived from the company record).
- **Joins.** company → country.
- **Evidence.** analyst-created, evidence-backed. Built by rule R03.
- **Does not mean.** Country of domicile only — not where the company sells, produces or is exposed.

### `measured_for` — “is measured for”

- **Meaning.** The economy the variable describes (derived from the variable record).
- **Joins.** economic_variable → country.
- **Evidence.** analyst-created. Built by rule R04.
- **Does not mean.** The economy the variable describes. It does not mean the variable matters only there.

### `in_sector` — “belongs to”

- **Meaning.** The industry's ISIC Rev. 4 division belongs to this ISIC section.
- **Joins.** industry → sector.
- **Evidence.** evidence-backed. Built by rule R05.
- **Does not mean.** A classification hierarchy: every division sits in exactly one section. It says nothing about economic links between industries of the same section.

### `has_currency` — “has currency”

- **Meaning.** The country's currency, by its ISO 4217 code.
- **Joins.** country → currency.
- **Evidence.** evidence-backed. Built by rule R06.
- **Does not mean.** It says nothing about exchange-rate exposure, or about other places that use the currency.

### `covers` — “covers”

- **Meaning.** The series describes this country's economy, as the provider defines it.
- **Joins.** data_series → country.
- **Evidence.** evidence-backed. Built by rule R07.
- **Does not mean.** The provider's geography, not a statement about influence between the series and the country.

### `related_measure_of` — “is a related measure of”

- **Meaning.** A curator recorded the series as a related measure of the variable, stating how the two differ.
- **Joins.** data_series → economic_variable.
- **Evidence.** analyst-created. Built by rule R08.
- **Does not mean.** A related measure, not the same measure: frequency, definition or source differ (see the stated difference).

### `expressed_in` — “is expressed in”

- **Meaning.** The currency the series' unit is stated in.
- **Joins.** data_series → currency.
- **Evidence.** evidence-backed. Built by rule R09.
- **Does not mean.** Values are shown as published and never converted.

### `listed_on` — “is listed on”

- **Meaning.** The market the instrument's prices come from, as declared in its price-file manifest.
- **Joins.** instrument → market.
- **Evidence.** unverified. Built by rule R10.
- **Does not mean.** Declared by the importer; RUMIN did not verify the listing.

### `quoted_in` — “is quoted in”

- **Meaning.** The currency of the instrument's prices, as declared in its price-file manifest.
- **Joins.** instrument → currency.
- **Evidence.** unverified. Built by rule R11.
- **Does not mean.** Declared by the importer; prices are never converted.

### `associated_with` — “is associated with”

- **Meaning.** The price-file manifest links the instrument to this country.
- **Joins.** instrument → country.
- **Evidence.** unverified. Built by rule R12.
- **Does not mean.** The manifest does not say how (country of listing, of the issuer, or other).
## Notes on evidence

- **Curated relationships are model assumptions.** Rule R01 gives every Phase 1
  relationship the status `model_assumption`, whatever its Phase 1 evidence level
  (`illustrative` for all 41 today): those levels describe how well an *assumption* is
  supported, not that a source states the relationship. The economic types also allow
  `evidence_backed`, for a future import of relationships that a cited source states
  (see [limitations](limitations.md)).
- **Record fields are analyst-created.** A company's industry and domicile, and a
  variable's economy, are fields a curator wrote (R02–R04). Classification, currency and
  provider-geography links are evidence-backed (R05–R07, R09) because a published standard
  or the provider's metadata states them. Price-file links are unverified (R10–R12):
  the importer declared them and RUMIN cannot check them.
- **Nothing is inferred from membership.** No type is created because two records share
  an industry, a country or a dataset: `supplies_to`, `lends_to` and `competes_with`
  exist only where a record states them.

## Adding a type

A new type needs a value in `GraphEdgeType` (`app/domain/enums.py`) and an Alembic
migration (enum columns are VARCHAR with a CHECK constraint), an entry in
`graph_types.py` (meaning, endpoints, direction, allowed statuses, caveat), a
construction rule in `rules.py` that produces it with evidence, a row in this dictionary
and tests. The validator rejects any edge whose type, endpoints, direction or status the
registry does not allow, and the explorer picks the new type up from the API.
