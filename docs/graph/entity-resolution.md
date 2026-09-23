# Entity resolution

Entity resolution decides which records describe the same entity. RUMIN decides it
**conservatively**: records are merged only through identifiers and explicit links, and
a similar name is never enough. The code is `backend/app/graph/resolution.py`; name
normalisation is in `backend/app/graph/names.py`.

## The stages

| Stage | What happens | Outcome recorded |
|---|---|---|
| 1. **Record keys** | A record that exists in its own right (a country, industry, company, variable, series or instrument) always maps to its own node, keyed by its own ID. Two records that would produce the same key are not merged: the second is rejected (`unsupported_merge`) | — |
| 2. **Exact identifiers** | Currencies, sectors and markets exist only as codes named by other records. Every record naming the same valid code (ISO 4217, ISIC section, ISO 10383 MIC) links to the same node | `identifier` · `linked` (13 decisions in the sample graph) |
| 3. **Provider identifiers** | A World Bank series names its country by ISO 3166-1 alpha-3 (`IND`), and its catalogue entry links it to a reference country (`cty_in`). The code is attached to that country as an identifier — unless another country claims it too | `explicit_link` · `identifier_attached` (11) |
| 4. **Normalised names** | Names are compared after normalising case, accents, punctuation, `&`, a leading "The", common abbreviations and trailing legal forms: *"The Deltrin Refining Co. Pvt. Ltd."* → `deltrin refining` | — |
| 5. **Candidates** | Equal normalised names are a **strong** candidate; the same words in another order, or every word of one name inside the other, a **weak** one | — |
| 6. **Decision** | Strong: both kept and **flagged for review** (`possible_duplicate`). Weak: **noted** (`similar_name`), since it is often a parent and a subsidiary. Fictional or sample versus real: **ruled out** (`match_ruled_out`). Nothing is merged | `name_comparison` · `candidate_flagged` or `rejected` |
| 7. **Audit log** | Every decision beyond a record's own key is stored in `graph_resolution_decisions`, with the source record, its original values, the outcome, the candidates and the reason | — |

Name checks run on companies and economic variables (the kinds where two records could
plausibly describe one entity), and between instruments and companies.

## Conflicts are never resolved silently

- **One identifier, two nodes of different kinds** (e.g. a code claimed for a country
  and something else): the identifier is attached to **neither**, both nodes are flagged,
  and the decision is logged as a `conflict` (`identifier_conflict`).
- **One identifier, two nodes of the same kind** (e.g. two industries with ISIC
  division 51): the records are **not merged**, both are flagged `unsupported_merge`,
  and the identifier is attached to neither. A curator must decide which is correct.
- **An identifier that is not valid in its scheme** is not attached, and is flagged
  (`invalid_identifier`). Formats are checked (ISO 4217 is three capitals, an ISIN has
  a valid check digit, a MIC is four characters); RUMIN holds no copy of the ISO code
  lists, so a well-formed but unassigned code cannot be detected.
- **An instrument whose name resembles a company's** is noted (`possible_issuer`) and
  **not linked**: a similar name is not evidence that the company issued it.

Original values are never changed: the node keeps its record's name and codes, and the
decision stores the values it compared.

## Why names never merge

Names collide constantly in finance: parents and subsidiaries ("Tata Steel" /
"Tata Steel Europe"), the same trading name in different countries ("ABC Holdings Ltd" in
India and "ABC Holdings Limited" in the United States), and unrelated firms that share
common words. Merging on a name would silently join different legal entities, and the
merge could not be undone without the original records. So a name match can only raise
a review item, and the tests check the false matches that must *not* happen:

| Test | Guards against |
|---|---|
| `test_identical_normalised_names_are_flagged_not_merged` | "ANVAYA BANK LTD." and "Anvaya Bank" stay two nodes; both flagged, nothing linked |
| `test_same_name_in_different_countries_is_still_two_entities` | Two "ABC Holdings" in India and the US keep their own domiciles |
| `test_a_contained_name_is_only_noted` | "Tata Steel" ⊂ "Tata Steel Europe" is noted, not flagged or merged |
| `test_fiction_is_never_matched_with_a_real_instrument` | A real instrument named like a fictional company is ruled out |
| `test_a_similar_name_never_links_an_instrument_to_a_company` | A sample instrument named "Aerisca Airways" gets no edge to the company |
| `test_common_words_do_not_make_every_name_a_candidate` | Exact duplicates are found among 120 names sharing common words; see below |
| `test_graph_names.py` | Normalisation and the strong / weak / no-match rules, case by case |

(All in `backend/tests/test_graph_construction.py` and `test_graph_names.py`.)

## Finding candidates without comparing every pair

Comparing every name with every other grows with the square of the number of records:
at 1,000 companies that was 500,000 comparisons and 4.8 seconds per build. Candidates are
therefore found by **blocking**:

- pairs with the **same normalised name**, or the **same words**, are always compared;
- otherwise a pair is compared if it shares a word used by **at most 100 names**
  (`MAX_BLOCK_SIZE`). A word shared by more names — "company", "india", or "synthetic" in
  a generated dataset — identifies nothing on its own.

The trade-off is documented and tested: a *partial* match made only of very common words
("Bharat Power" inside "Bharat Power 007", when both words appear in over 100 names) is
not searched for. Exact and reordered duplicates are always found.

## What entity resolution does not do

- It does not look anything up outside RUMIN (no registry, LEI or OpenFIGI lookup).
- It does not merge by name, address, similarity score or machine learning.
- It has no review workflow yet: flagged candidates are listed in the build report and
  `GET /api/v1/graph/issues`, and a curator resolves them by editing the source records.
