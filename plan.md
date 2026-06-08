# Chicago Restaurant Food-Blog Text Corpus

## Objective

Build a production-style, GCP-native data collection and curation platform that:

- Crawls Chicago restaurant food blogs with a focused (topical) crawler
- Stores raw crawl artifacts immutably
- Extracts and normalizes text
- Scores topical relevance and computes quality signals
- Performs exact and near-duplicate removal
- Produces a clean, train-ready text corpus (deduplicated blog post text + metadata)
- Is fully restartable and idempotent
- Runs entirely on GCP

The corpus is intended to *eventually* support questions about trending and most-popular Chicago restaurants. Actually answering those questions, and any restaurant entity/structured extraction, is explicitly out of scope. The deliverable here is clean text data only.

The project is educational: a miniature, domain-focused version of the systems behind Common Crawl, FineWeb, and Dolma.

---

## Scope

In scope:

- A focused crawler seeded from known Chicago food blogs that follows external links gated by a relevance filter
- Raw to bronze to silver to gold to train batch pipeline
- Topical relevance scoring + quality filtering
- Exact and near-duplicate deduplication
- Clean text corpus shards + dataset manifest + operational stat reports

Out of scope:

- Answering trending/popular-restaurant questions
- Restaurant/dish/sentiment entity extraction or any structured "restaurant mentions" dataset
- A local end-to-end prototype (local usage is per-component dev/test only; the full flow only runs on GCP)
- BigQuery / a data warehouse

---

# High-Level Architecture

```text
Chicago food-blog seeds
        |
        v
Cloud SQL URL Frontier  <----+  (relevance-prioritized)
        |                    |
        v                    |
GKE Focused Crawler Workers  |
   (fetch + relevance) ------+  discovered links
        |
        v
GCS Raw Storage (WARC)
        |
        v
Ray Extraction Pipeline
        |
        v
GCS Bronze (extracted docs)
        |
        v
Ray Quality + Relevance Pipeline
        |
        v
GCS Silver (filtered docs)
        |
        v
Ray Deduplication Pipeline
        |
        v
GCS Gold (deduped docs)
        |
        v
Ray Shard Writer
        |
        v
GCS Train Shards + Manifest + Stat Reports
```

Orchestrated by Airflow (Cloud Composer). Observability via Cloud Monitoring + Cloud Logging. No BigQuery.

---

# Design Principles

## Raw Data is Immutable

Raw crawl data is never modified. Every processing stage writes new outputs.

```text
raw -> bronze -> silver -> gold -> train
```

## Everything Is Restartable

Workers may fail at any time. Every stage supports:

- retries
- replay
- backfills
- incremental processing

without corrupting state.

## Idempotency

All operations are safe to run multiple times:

- URL insertion uses unique URL hashes
- Content storage uses content hashes
- Processing jobs write versioned outputs
- Dataset creation is deterministic

## Batch Processing First

The architecture favors:

```text
Object Storage -> Batch Processing -> Object Storage
```

over event-driven microservices. This mirrors how large-scale training datasets are typically built.

## GCP-First, Test Components Locally

There is no local end-to-end prototype. Each component is developed and unit/integration tested locally against a small input (e.g. the fetcher against a few URLs, a single Ray job against a sample), but the full pipeline only ever runs on GCP.

---

# GCP Stack


| Layer                  | Technology               |
| ---------------------- | ------------------------ |
| Object Storage         | GCS                      |
| URL Frontier           | Cloud SQL (Postgres)     |
| Crawler Compute        | GKE                      |
| Batch Processing       | Ray                      |
| Workflow Orchestration | Airflow / Cloud Composer |
| Infrastructure         | Terraform                |
| Monitoring             | Cloud Monitoring         |
| Logging                | Cloud Logging            |
| Secrets                | Secret Manager           |
| Containers             | Artifact Registry        |


(BigQuery removed. Operational reporting is handled via GCS stat reports + Cloud Monitoring; see Reporting & Metrics.)

---

# Storage Layout

## GCS Buckets

```text
gs://chi-food-raw/
gs://chi-food-bronze/
gs://chi-food-silver/
gs://chi-food-gold/
gs://chi-food-train/
```

## Raw Zone

Original crawl artifacts (WARC).

```text
raw/
  crawl_id=2026-06-06/
    host=example-chicago-food-blog.com/
      part-00000.warc.zst
      part-00001.warc.zst
```

## Bronze Zone

Extracted documents.

```text
bronze/
  crawl_id=2026-06-06/
    documents-00000.parquet
```

## Silver Zone

Quality-scored, relevance-filtered documents. Rejected documents are retained (metadata only) for analysis and threshold tuning.

```text
silver/
  crawl_id=2026-06-06/
    accepted/
      filtered-00000.parquet
    rejected/
      rejected-00000.parquet
```

## Gold Zone

Deduplicated documents.

```text
gold/
  crawl_id=2026-06-06/
    exact_dedup/
      deduped-00000.parquet
    near_dedup/
      deduped-00000.parquet
```

## Train Zone

Training shards + manifest + reports.

```text
train/
  dataset_version=v001/
    shard-00000.parquet
    shard-00001.parquet
    manifest.json
    stats/
      report.json
```

---

# Crawl Targeting & Seeds

The crawler is focused on Chicago restaurant food blogs. Targeting has three inputs.

## Seed list

A curated, version-controlled seed file (`crawler/seeds/seeds.yaml`) lists known Chicago food blogs and city/neighborhood dining sites. Seed hosts are marked trusted (`is_seed = true`) and are crawled without a relevance gate; their outbound links are the entry point for discovery.

```yaml
# crawler/seeds/seeds.yaml
# TODO: populate with verified Chicago food-blog domains before first crawl.
seeds:
  - url: https://example-chicago-eats.com/
    notes: placeholder - city-wide restaurant blog
  - url: https://example-windy-city-dining.com/
    notes: placeholder - neighborhood reviews
  - url: https://example-deep-dish-diary.com/
    notes: placeholder - restaurant reviews
```

These are placeholders. Populate with real, verified domains (and confirm each allows crawling) before the first run.

## Topic lexicon

A lexicon file (`crawler/seeds/lexicon.yaml`) drives heuristic relevance scoring:

- Geo terms: `chicago`, neighborhood names (e.g. `wicker park`, `pilsen`, `logan square`, `west loop`, `hyde park`), `the loop`, `chicagoland`
- Food/restaurant terms: `restaurant`, `menu`, `dish`, `chef`, `reservation`, `tasting`, `brunch`, `deep dish`, `michelin`, `BYOB`, etc.

The lexicon is the single source of truth for both URL-path heuristics and content relevance.

## Allow / deny rules

- Scheme allowlist: `http`, `https` only.
- Off-seed hosts are allowed but bounded (see depth limits in Focused Crawling).
- Optional host denylist for known aggregators/spam.

---

# Focused Crawling & Relevance

This replaces the implicit "crawl everything" model. The crawl stays on-topic via relevance scoring applied at two points.

## (1) Discovery-time URL relevance (cheap)

When links are discovered, each candidate gets an initial `relevance_score` and `priority` from cheap signals, with no network calls:

- Host reputation: seed/trusted host > previously-relevant host > unknown host
- URL-path keyword hints: lexicon terms in the path/slug (e.g. `/chicago-restaurants/`, `/west-loop-dining/`)
- Parent-page relevance: links inherit a fraction of the linking page's content relevance score
- Depth penalty: score decays with crawl depth, especially across host boundaries

This sets queue priority so the crawler spends its budget on likely-relevant pages first.

## (2) Content-time relevance (after extraction)

After text extraction, a content `relevance_score` in [0, 1] is computed from lexicon density (geo + food term coverage and frequency, normalized by length). This is heuristic first, with a clear hook to swap in an embedding similarity or a small trained classifier later. Documents below the threshold are routed to `silver/.../rejected/` with their score and reason, not silently dropped.

## Drift control

- Off-seed hosts have a bounded max depth (e.g. 2) from the point of discovery.
- A host that yields repeated low-relevance content gets deprioritized (lower future priority).
- Per-crawl caps on total pages and per-host pages.

```text
                 +-------------------------+
discovered link  | URL/host heuristic score|---> priority + relevance_score
                 +-------------------------+            |
                                                        v
                                              Cloud SQL frontier (ordered)
                                                        |
                                                        v
                                              fetch + extract + content score
                                                        |
                          relevance >= threshold? ------+------ no ---> rejected/ (kept for tuning)
                                   |
                                  yes
                                   |
                                   v
                       enqueue outbound links (inherit parent score, depth+1)
```

---

# URL Frontier

The URL frontier determines what to crawl next. It is implemented in Cloud SQL (PostgreSQL).

## frontier_urls

```sql
CREATE TABLE frontier_urls (
    id BIGSERIAL PRIMARY KEY,
    url_hash TEXT UNIQUE NOT NULL,
    canonical_url TEXT NOT NULL,
    host TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    relevance_score REAL DEFAULT 0,
    topic_source TEXT,            -- seed | discovered
    depth INTEGER DEFAULT 0,
    discovered_from TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_attempt_at TIMESTAMPTZ,
    next_fetch_after TIMESTAMPTZ NOT NULL,
    lease_expires_at TIMESTAMPTZ,
    retry_count INTEGER DEFAULT 0,
    content_hash TEXT,
    failure_reason TEXT
);
```

## host_state

```sql
CREATE TABLE host_state (
    host TEXT PRIMARY KEY,
    is_seed BOOLEAN DEFAULT FALSE,
    allow BOOLEAN DEFAULT TRUE,
    robots_txt TEXT,
    robots_fetched_at TIMESTAMPTZ,
    crawl_delay_seconds INTEGER DEFAULT 5,
    last_fetch_at TIMESTAMPTZ,
    next_allowed_fetch_at TIMESTAMPTZ,
    consecutive_failures INTEGER DEFAULT 0,
    relevant_pages BIGINT DEFAULT 0,
    irrelevant_pages BIGINT DEFAULT 0
);
```

## crawl_runs

```sql
CREATE TABLE crawl_runs (
    crawl_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    status TEXT,
    pages_fetched BIGINT DEFAULT 0,
    pages_failed BIGINT DEFAULT 0,
    pages_irrelevant BIGINT DEFAULT 0,
    bytes_downloaded BIGINT DEFAULT 0
);
```

---

# URL Leasing

Crawler workers lease URLs; they never directly pop work from a queue.

A worker:

1. Starts a transaction.
2. Selects eligible URLs ordered by priority and relevance.
3. Locks them.
4. Marks them leased.
5. Commits.

```sql
SELECT id
FROM frontier_urls
WHERE status = 'queued'
  AND next_fetch_after <= NOW()
  AND (lease_expires_at IS NULL OR lease_expires_at < NOW())
ORDER BY priority DESC, relevance_score DESC
LIMIT 100
FOR UPDATE SKIP LOCKED;
```

Leased URLs become:

```text
status = fetching
lease_expires_at = now + 5 minutes
```

---

# Crawl Politeness

The crawler must:

- Respect robots.txt
- Respect crawl-delay directives
- Avoid concurrent requests to the same host
- Use a descriptive User-Agent

Initial limits:

```text
1 concurrent request per host
5-10 second delay between requests
```

Example User-Agent:

```text
ChiFoodCrawler/0.1 (+mailto:contact@example.com)
```

---

# URL Discovery

When new links are found:

1. Resolve relative URLs.
2. Canonicalize URLs.
3. Remove fragments.
4. Remove unsupported schemes.
5. Score relevance (URL/host heuristic + inherited parent score).
6. Apply depth/drift limits.
7. Insert unseen URLs with computed priority + relevance.

Rejected schemes:

```text
mailto: javascript: tel: data:
```

Insertion is idempotent:

```sql
INSERT INTO frontier_urls (...)
VALUES (...)
ON CONFLICT (url_hash) DO NOTHING;
```

---

# Crawler Workflow

Each crawler worker performs:

```text
Lease URLs
   |
   v
Check host availability (politeness window)
   |
   v
Check robots.txt
   |
   v
Fetch content
   |
   v
Write raw artifact (WARC) to GCS
   |
   v
Extract links
   |
   v
Score discovered URLs (relevance heuristic)
   |
   v
Insert discovered URLs (priority + relevance, depth limits)
   |
   v
Update frontier + host_state
```

---

# Raw Crawl Format

Each fetch generates metadata.

```json
{
  "crawl_id": "2026-06-06",
  "url": "https://example-chicago-food-blog.com/page",
  "canonical_url": "https://example-chicago-food-blog.com/page",
  "host": "example-chicago-food-blog.com",
  "status_code": 200,
  "content_type": "text/html",
  "fetch_timestamp": "2026-06-06T18:00:00Z",
  "content_hash": "sha256...",
  "discovery_relevance": 0.62,
  "raw_gcs_uri": "gs://chi-food-raw/..."
}
```

---

# Processing Pipeline

Ray jobs operate on immutable GCS inputs.

```text
Raw HTML / WARC
   |
   v
Text Extraction
   |
   v
Normalization
   |
   v
Language Detection
   |
   v
Relevance Scoring + Quality Signals
   |
   v
Filtering (language + quality + relevance)
   |
   v
Exact Deduplication
   |
   v
Near-Duplicate Removal
   |
   v
Training Shards
```

---

# Document Schema

Text-corpus shape (no restaurant entity fields).

```json
{
  "id": "...",
  "url": "...",
  "host": "...",
  "crawl_id": "...",
  "source": "crawler",
  "title": "...",
  "text": "...",
  "language": "en",
  "metadata": {
    "crawl_topic": "chicago_restaurants",
    "depth": 1
  },
  "quality_signals": {
    "relevance_score": 0.71,
    "is_chicago_food_relevant": true
  }
}
```

---

# Extraction Job

Input:

```text
raw/
```

Output:

```text
bronze/
```

Responsibilities:

- Read WARC files
- Parse HTML
- Extract main content
- Extract title
- Extract metadata
- Normalize whitespace

Suggested libraries:

```text
warcio
trafilatura
readability-lxml
BeautifulSoup
```

---

# Quality + Relevance Pipeline

Input:

```text
bronze/
```

Output:

```text
silver/  (accepted/ and rejected/)
```

Signals:

```text
language
language_confidence
num_chars
num_words
symbol_ratio
digit_ratio
uppercase_ratio
stopword_ratio
duplicate_line_ratio
relevance_score
is_chicago_food_relevant
```

Initial filters:

```text
language == en
num_words >= 100
symbol_ratio < 0.2
duplicate_line_ratio < 0.3
relevance_score >= 0.4   # tune on a sample; start conservative
```

Store both accepted documents and rejected document metadata (including the failing signal) for later analysis and threshold tuning.

---

# Exact Deduplication

Input:

```text
silver/accepted/
```

Output:

```text
gold/exact_dedup/
```

Method:

```text
normalize text
   |
   v
sha256(text)
   |
   v
remove duplicate hashes
```

---

# Near-Duplicate Deduplication

Input:

```text
gold/exact_dedup/
```

Output:

```text
gold/near_dedup/
```

Technique:

```text
MinHash + LSH
```

Goals:

- remove mirrors
- remove copied content
- remove lightly modified duplicates (common across food blogs republishing lists)

---

# Shard Writer

Input:

```text
gold/near_dedup/
```

Output:

```text
train/
```

Produces:

```text
Parquet shards
JSONL.zst shards
dataset manifest
summary statistics
```

Manifest example:

```json
{
  "dataset_version": "v001",
  "crawl_ids": ["2026-06-06"],
  "topic": "chicago_restaurants",
  "num_documents": 98423,
  "created_at": "2026-06-06T20:00:00Z"
}
```

---

# Reporting & Metrics

No BigQuery. Operational and dataset metrics are produced two ways.

## GCS stat reports

Each pipeline stage writes a JSON stat report next to its output (and a roll-up under `train/dataset_version=.../stats/report.json`):

```text
pages fetched / failed / irrelevant
status code distribution
content types
language distribution
relevance score distribution
quality filter rates
dedup rates (exact + near)
estimated token count
```

```json
{
  "dataset_version": "v001",
  "crawl_ids": ["2026-06-06"],
  "pages_fetched": 120342,
  "pages_irrelevant": 41200,
  "accepted_documents": 98423,
  "exact_dup_removed": 8123,
  "near_dup_removed": 4501,
  "relevance_histogram": {"0.0-0.2": 12000, "0.2-0.4": 29200, "0.4-0.6": 30100, "0.6-0.8": 25000, "0.8-1.0": 24042},
  "estimated_tokens": 41200000
}
```

## Live operations

- Cloud Monitoring: dashboards + alerts for crawler throughput, error rate, frontier backlog, Ray job health.
- Cloud Logging: structured logs from crawler workers and Ray jobs.

---

# Airflow DAG

```text
start_crawl
   |
   v
wait_for_completion
   |
   v
extract_text
   |
   v
quality_relevance_filter
   |
   v
exact_dedup
   |
   v
near_dedup
   |
   v
write_shards
   |
   v
generate_reports
```

---

# Repository Layout

```text
repo/
  infra/
    terraform/
  crawler/
    seeds/            # seeds.yaml, lexicon.yaml
    frontier/
    leasing/
    robots/
    fetcher/
    canonicalizer/
    link_extractor/
    relevance/        # URL + content relevance scoring
    storage/
  processing/
    extraction/
    quality/
    relevance/
    dedup/
    shard_writer/
  ray_jobs/
    extract_text.py
    quality_filter.py
    exact_dedup.py
    near_dedup.py
    shard_writer.py
  reporting/
    reports.py        # GCS JSON stat reports
  orchestration/
    airflow/
  docs/
```

---

# Milestones

GCP-first. There is no local end-to-end prototype; each component is tested locally against small inputs during development, but the full flow runs only on GCP.

## Milestone 1 - GCP Foundation

- Terraform: project, IAM, networking
- GCS buckets (raw/bronze/silver/gold/train)
- Cloud SQL (Postgres)
- Artifact Registry
- Secret Manager

## Milestone 2 - Frontier & Seeds

- Frontier + host_state + crawl_runs schema
- URL leasing
- Seed loader (seeds.yaml) and lexicon
- Canonicalization + discovery with URL/host relevance heuristics
- Unit-tested locally against sample URLs

## Milestone 3 - Focused Crawler on GKE

- Containerized polite fetcher (robots, crawl-delay, 1 req/host)
- Discovery-time relevance scoring + depth/drift limits
- WARC storage to GCS raw
- Small focused crawl (hundreds of pages from seeds) to validate targeting

## Milestone 4 - Extraction, Relevance & Quality

- Ray extraction raw -> bronze
- Text normalization + language detection
- Content relevance scoring + quality signals -> silver (accepted/rejected)
- Tune relevance threshold on a sample; measure precision

## Milestone 5 - Deduplication

- Exact dedup (sha256)
- MinHash + LSH near-dedup -> gold

## Milestone 6 - Dataset Generation & Reporting

- Train-ready shards (Parquet + JSONL.zst)
- Dataset manifest
- GCS JSON stat reports
- Cloud Monitoring dashboards

## Milestone 7 - Scale & Tune

- Larger focused crawl (100,000+ fetched pages)
- Measure relevance precision/recall on a labeled sample
- Measure throughput, storage growth, processing cost

---

# Future Extensions

## Restaurant Entity Extraction & Trend Analysis

The natural next step beyond this corpus (currently out of scope):

```text
restaurant + dish NER
mention frequency over time
sentiment / rating extraction
trending / most-popular restaurant analysis
```

## Improved Relevance

```text
embedding similarity to a Chicago-food reference set
small trained relevance classifier
active-learning loop from rejected/ samples
```

## Media Collection

```text
images (restaurant/dish photos)
```

Pipeline:

```text
download -> normalize -> metadata extraction -> OCR -> dataset shards
```

## Advanced Quality Filters

```text
spam detection
toxicity detection
PII classification
domain reputation scoring
```

---

# Success Criteria

The system is successful when it can:

1. Crawl 100,000+ pages focused on Chicago restaurant food blogs.
2. Respect crawl politeness (robots.txt, crawl-delay, per-host concurrency).
3. Stay on-topic via relevance scoring at discovery and content time.
4. Store raw artifacts immutably in GCS.
5. Extract clean text.
6. Generate quality + relevance metadata and route rejects for tuning.
7. Remove exact duplicates.
8. Remove near duplicates.
9. Produce a train-ready clean text corpus with a manifest.
10. Produce operational + dataset stat reports (no BigQuery).
11. Recover cleanly from worker failures.

---

# Implementation Todo

One numbered todo per component, ordered top-of-funnel (raw acquisition) to bottom (clean corpus). Each is independently developable and locally testable against a small input; the full flow runs only on GCP.

## 0. Foundation (prerequisite)

### 1. GCP foundation & infra (`infra/terraform/`)

Terraform-managed project scaffolding that everything else depends on. *Done when:* `terraform apply` provisions all five buckets, a reachable Cloud SQL instance, and required service accounts.

- Terraform project, IAM roles, and networking (VPC, subnets, firewall)
- GCS buckets: `raw`, `bronze`, `silver`, `gold`, `train`
- Cloud SQL (Postgres) instance + database + users
- Artifact Registry repo for container images
- Secret Manager secrets (DB creds, crawler contact email)
- Remote Terraform state + `README` for `plan`/`apply`

## Top of funnel — acquire raw data

### 2. Seeds & topic lexicon (`crawler/seeds/`)

Curated targeting inputs, the single source of truth for relevance. *Done when:* seeds load into `frontier_urls` and the lexicon is importable by both URL and content scorers.

- [x] Populate `seeds.yaml` with verified Chicago food-blog domains (confirm each allows crawling)
- [x] Author `lexicon.yaml` (geo terms + food/restaurant terms)
- [x] Seed loader that inserts seeds as `is_seed=true`, `topic_source=seed`, `depth=0`
- [x] Lexicon parser exposing terms/weights to URL + content scorers
- [x] Unit tests for loader and lexicon parsing

### 3. URL frontier schema (`crawler/frontier/`)

Cloud SQL tables that drive what to crawl next. *Done when:* migrations create the schema and duplicate URL inserts are no-ops.

- [x] `frontier_urls`, `host_state`, `crawl_runs` DDL + migrations
- [x] Indexes for lease query (`status`, `next_fetch_after`, `priority`, `relevance_score`)
- [x] Idempotent insert via `url_hash` `ON CONFLICT (url_hash) DO NOTHING`
- [x] Data-access layer (insert / update status / fetch by id)
- [x] Tests asserting duplicate inserts are no-ops

### 4. URL leasing (`crawler/leasing/`)

Safe concurrent work distribution. *Done when:* concurrent workers never lease the same URL and expired leases are reclaimed.

- [x] Transactional lease query (`ORDER BY priority DESC, relevance_score DESC ... FOR UPDATE SKIP LOCKED`)
- [x] Mark leased rows `status=fetching`, `lease_expires_at=now+5m`
- [x] Completion API (mark fetched/failed, set `content_hash`/`failure_reason`)
- [x] Lease reclamation for expired leases
- [x] Concurrency test: N workers, zero double-leases

### 5. Robots & politeness (`crawler/robots/`)

Respectful, compliant crawling. *Done when:* disallowed paths are skipped and per-host spacing is enforced.

- [x] Fetch + parse + cache robots.txt in `host_state` (with TTL)
- [x] Allow/disallow path check before fetch
- [x] Honor crawl-delay; default 5–10s spacing via `next_allowed_fetch_at`
- [x] Enforce 1 concurrent request per host
- [x] Descriptive User-Agent (`ChiFoodCrawler/0.1 (+mailto:...)`)
- [x] Tests for allow/deny and delay computation

### 6. Fetcher (`crawler/fetcher/`)

Polite HTTP fetch producing raw-crawl metadata. *Done when:* a small URL set is fetched with correct metadata and politeness windows respected.

- [x] HTTP client with timeouts, retries, redirect handling
- [x] Capture status code, content-type, bytes, fetch timestamp
- [x] Compute `content_hash` (sha256 of body)
- [x] Emit raw-crawl metadata record (matching plan JSON)
- [x] Local test against a few sample URLs

### 7. Canonicalizer (`crawler/canonicalizer/`)

Normalize URLs so dedup and idempotency work. *Done when:* equivalent URLs canonicalize identically and rejected schemes are dropped.

- [x] Resolve relative URLs against base
- [x] Strip fragments; normalize host/case/default ports/trailing slash
- [x] Drop unsupported schemes (`mailto:`/`javascript:`/`tel:`/`data:`)
- [x] Compute stable `url_hash` from canonical URL
- [x] Tests covering equivalence classes + rejected schemes

### 8. Link extractor (`crawler/link_extractor/`)

Find outbound links for discovery. *Done when:* links are extracted and passed through the canonicalizer.

- Parse HTML and extract `<a href>` (+ rel/nofollow awareness)
- Pipe extracted links through the canonicalizer
- De-duplicate links within a page
- Tests on sample HTML fixtures

### 9. Discovery-time URL relevance (`crawler/relevance/`)

Cheap scoring that keeps the crawl on-topic. *Done when:* discovered URLs are scored, prioritized, and inserted with depth/drift limits.

- Host-reputation signal (seed > previously-relevant > unknown)
- URL-path lexicon-hint scoring
- Inherit fraction of parent-page content relevance
- Depth penalty (stronger across host boundaries)
- Combine into `relevance_score` + `priority`
- Enforce off-seed max depth + per-crawl/per-host caps; host deprioritization
- Tests for scoring + depth/drift limits

### 10. Raw WARC storage (`crawler/storage/`)

Immutable raw artifacts in GCS. *Done when:* fetches land as partitioned WARC and frontier/host state advance correctly.

- Write WARC records (`.warc.zst`) with request/response
- Partition path `crawl_id=.../host=.../part-*.warc.zst`
- Part rolling (size/count) + upload to `gs://chi-food-raw/`
- Update `frontier_urls`, `host_state`, `crawl_runs` after write
- Test WARC round-trips and is replayable

### 11. Focused crawler on GKE (`crawler/`)

Assemble components into a deployable worker loop. *Done when:* a few hundred seed-anchored pages land in `raw/` on GKE.

- Worker loop: lease → politeness → fetch → store → extract-links → score → enqueue
- Dockerfile + push to Artifact Registry
- GKE Deployment/Job manifests + config/secrets wiring
- Structured logging + graceful shutdown (lease release)
- Small focused crawl to validate targeting

## Processing — raw to clean (Ray jobs)

### 12. Text extraction: raw → bronze (`ray_jobs/extract_text.py`, `processing/extraction/`)

Turn raw HTML/WARC into structured documents. *Done when:* a sample WARC yields clean bronze docs matching the document schema.

- Read WARC from `raw/` (warcio)
- Parse HTML + extract main content (trafilatura / readability-lxml / BeautifulSoup)
- Extract title + metadata (depth, crawl topic)
- Normalize whitespace; assemble document schema
- Write `bronze/.../documents-*.parquet`
- Local Ray run on a sample WARC

### 13. Quality + content relevance: bronze → silver (`ray_jobs/quality_filter.py`, `processing/quality/`, `processing/relevance/`)

Score, filter, and route documents. *Done when:* docs split accepted/rejected with reasons and the threshold is tunable on a sample.

- Language detection + confidence
- Quality signals (`num_words`, `symbol_ratio`, `digit_ratio`, `uppercase_ratio`, `stopword_ratio`, `duplicate_line_ratio`)
- Lexicon-density content `relevance_score` + `is_chicago_food_relevant`
- Apply initial filters (lang=en, words≥100, symbol_ratio<0.2, dup_line<0.3, relevance≥0.4)
- Route to `silver/accepted/` and `silver/rejected/` (rejects keep score + failing signal)
- Tune threshold on a labeled sample; measure precision

### 14. Exact deduplication: silver → gold/exact_dedup (`ray_jobs/exact_dedup.py`, `processing/dedup/`)

Remove byte-identical content. *Done when:* identical texts collapse to one document.

- Normalize text for hashing
- Compute `sha256(text)`
- Drop duplicate hashes (keep one representative)
- Write `gold/exact_dedup/`
- Test identical texts collapse to one

### 15. Near-duplicate removal: gold/exact_dedup → gold/near_dedup (`ray_jobs/near_dedup.py`, `processing/dedup/`)

Remove mirrors and lightly-modified copies. *Done when:* near-duplicate clusters collapse on a sample at the chosen Jaccard threshold.

- Shingle text + compute MinHash signatures
- LSH banding to find candidate pairs
- Cluster near-dupes; keep one representative per cluster
- Write `gold/near_dedup/`
- Tune Jaccard threshold + test on a sample

### 16. Shard writer: gold/near_dedup → train (`ray_jobs/shard_writer.py`, `processing/shard_writer/`)

Produce the train-ready corpus. *Done when:* deterministic shards + a valid manifest are produced.

- Write Parquet shards under `train/dataset_version=v001/`
- Write JSONL.zst shards
- Generate `manifest.json` (version, crawl_ids, topic, doc count, created_at)
- Deterministic sharding (stable ordering/sizing)
- Test shards + manifest validate

## Cross-cutting — observe & orchestrate

### 17. Reporting & metrics (`reporting/reports.py`)

Operational + dataset visibility without BigQuery. *Done when:* each stage emits a stat report and a roll-up is generated for a dataset version.

- Per-stage GCS JSON stat reports next to outputs
- Roll-up `train/.../stats/report.json` (fetch/fail/irrelevant, status/content-type/language/relevance distributions, dedup rates, estimated tokens)
- Cloud Monitoring dashboards (throughput, error rate, frontier backlog, Ray job health)
- Cloud Logging structured logs from workers + Ray jobs
- Alerts on error rate / stalled frontier

### 18. Orchestration (`orchestration/airflow/`)

Tie the stages together on Cloud Composer. *Done when:* the DAG runs end-to-end on GCP and is safely re-runnable.

- DAG: `start_crawl → wait_for_completion → extract_text → quality_relevance_filter → exact_dedup → near_dedup → write_shards → generate_reports`
- Sensors/operators for crawl completion + Ray job submission
- Retries, idempotency, and backfill support per task
- Deploy to Cloud Composer
- End-to-end re-run validation

