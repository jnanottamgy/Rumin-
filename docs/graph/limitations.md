# Data-quality limitations

What the knowledge graph cannot tell you, and why. Read this before drawing a conclusion
from a node, an edge, a path or a metric. The product-wide list is in
[`docs/known-limitations.md`](../known-limitations.md).

## Questions it can and cannot answer

| Question | Can the graph answer it? |
|---|---|
| Which records does RUMIN hold about Deltrin Refining, and where did each come from? | **Yes.** The node's sources, identifiers and evidence |
| Why are these two nodes connected? | **Yes.** Every edge has evidence records and a rule |
| Which variables is a company or industry *assumed* to be affected by? | **Yes, as assumptions.** Each is labelled with its evidence status, "direct" or "via its industry", and has no magnitude |
| How exposed is a company to the oil price, in rupees or per cent? | **No.** Nothing is measured. An assumed-effect edge has no size |
| Does the oil price *cause* changes in a company's costs? | **No.** No edge is a causal finding |
| Do two series move together? | **No.** No correlation is computed, and the graph holds no values |
| Who are a real company's suppliers, customers or lenders? | **No.** The only companies are fictional, and relationships are never inferred from industries |
| Which company is most important? | **No.** Degree is data coverage, and no ranking is computed |
| Is the economy of India well connected? | **No.** Components and density describe RUMIN's records, not an economy |

## Coverage

- **Small, and partly fictional.** The sample graph has 50 nodes and 97 edges: 3
  countries, 3 currencies, 6 ISIC sections, 8 industries, 12 **fictional** companies, 7
  variable definitions and 11 World Bank series definitions. Instruments appear only when
  a price file is imported. The graph is **not a map of the economy**, and the API and
  the explorer say so on every overview.
- **Only types the data supports.** There are no nodes for commodities, banks as a
  separate kind, governments, indices, ownership, subsidiaries, trade flows or real supply
  chains, because RUMIN holds no structured source for them.
- **A missing edge is not a missing relationship.** An edge exists only where a record
  states it. The absence of a `supplies_to` edge says nothing about the world. A path search
  that finds nothing says so in those words ("…not that the two are unrelated in the
  world").

## Evidence

- **65 of 97 sample edges are illustrative.** They touch the fictional companies. They
  demonstrate the model and describe nothing real.
- **41 edges are model assumptions.** Each has a written rationale, an assumed polarity
  and an illustrative strength (weak, moderate or strong). None was estimated or
  validated. The strength is a curator's ordinal label, not a measurement, and it is
  never used as a weight.
- **"Evidence-backed" means "a source states it", not "verified".** The 24
  evidence-backed edges transcribe a classification (ISIC Rev. 4), an ISO code or a
  provider's metadata. RUMIN checks codes for their **format**, and holds no copy of the
  ISO code lists, so a well-formed but unassigned code cannot be detected.
- **The ISIC section table is RUMIN's transcription.** Industry → sector edges are
  derived from the division ranges in `backend/app/graph/isic.py`. They are only as
  correct as that table.
- **No citations for the curated relationships.** None of the 41 sample relationships
  cites an outside source. The panels say "None — the record does not cite an outside
  source" rather than leaving the field blank.
- **Unverified edges are recorded as declared.** An instrument's market, currency and
  country come from its price-file manifest, and the licence of a price file is declared
  by the importer. RUMIN cannot check either.
- **No confidence scores.** A number would need a defined meaning and a method to
  estimate it, and none exists. The evidence status is the summary.

## Meaning

- **Assumed effects have no size, timing or certainty.** *"Brent crude — affects costs of
  → Refined petroleum products"* says the curator assumes such an effect. It does not say
  how large it is, when it happens, or that it holds for every refiner.
- **Industry-level assumptions are not company facts.** An effect stated for an industry
  is shown for its companies only as "via its industry", with the note that companies can
  be affected very differently.
- **One industry and one domicile per company.** `in_industry` is the primary industry
  from the company record, and `domiciled_in` is the country of domicile. Neither says
  where a company sells, produces or is exposed.
- **Paths link records, not mechanisms.** A 3-hop path through a country or a currency
  connects almost anything. Hops ignore evidence status unless you filter by it.
- **Degree, components and density describe the data.** Countries and currencies are hubs
  by construction. One connected component does not mean an integrated economy.

## Identity

- **Duplicates are flagged, not merged.** Two records for the same entity with slightly
  different names stay as two nodes until a curator fixes the source records. They are
  listed as `possible_duplicate` or `similar_name` issues.
- **Some partial name matches are not searched for.** To keep builds fast, a pair of names
  that shares only very common words (words used by more than 100 names) is not compared.
  Exact and reordered duplicates are always found. See
  [entity resolution](entity-resolution.md#finding-candidates-without-comparing-every-pair).
- **No outside registries.** There is no LEI, company-registry or OpenFIGI lookup, and no
  review workflow. Flagged candidates are resolved by editing the source records.

## Time

- **The graph is as of its last build.** Builds run from the command line (`make graph`).
  Nothing rebuilds automatically. When the sources change, the overview reports the
  graph as **stale**. On a running API that can take up to 30 seconds per process to
  appear (the check is cached).
- **Validity periods only when a source states one.** No sample relationship states one,
  so no edge is historical. RUMIN never guesses a period.
- **Membership history, not value history.** Every node and edge records the build that
  added, last changed and retired it, so the graph's membership at any build can be
  reconstructed. Earlier descriptions or qualifiers are overwritten, and a node that was
  retired and later restored keeps no record of when it was absent.
- **Series values stay outside the graph.** A series node says whether values are stored
  (read live), but the values, their periods and revisions are in the Phase 2 tables. World
  Bank data is mostly annual and published with a lag. No live retrieval was verified in
  the environment where RUMIN was built ([known limitations](../known-limitations.md)).

## Scale

- Measured on synthetic graphs up to 20,948 nodes and 107,832 edges
  ([performance](performance.md)). Larger graphs have not been tested.
- At that size a first build takes about 21 s on SQLite, an unchanged rebuild about 16 s,
  and the first overview request after a build or a restart about 6 s, because it checks
  every source record for changes.
- The explorer draws at most 150 nodes, and one API request returns at most 200 nodes.
  Larger neighbourhoods are cut short, and the cut is reported.

## Access

- **Read-only API, no authentication.** RUMIN has no users yet, so there are no write
  endpoints. Builds run from the command line only. Anyone who can reach the API can read
  the whole graph: local use only ([security](../security.md)).
