# food-crawl

A production-style, GCP-native platform that crawls Chicago restaurant food
blogs and curates a clean, train-ready text corpus. See [`plan.md`](./plan.md)
for the full architecture, design principles, and the implementation todo list.

## Layout

```text
infra/terraform/   # Milestone 1: GCP foundation (VPC, GCS, Cloud SQL, IAM, ...)
crawler/           # focused crawler components
  seeds/           # seed list + topic lexicon (targeting inputs)
  frontier/        # URL frontier schema, repository, migrations
  leasing/         # concurrent-safe URL leasing
  robots/          # robots.txt compliance + per-host politeness
  fetcher/         # polite HTTP client + raw-crawl metadata
tests/             # unit tests
```

## Development

Requires Python `>=3.11`. Using [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev      # create the venv and install deps
uv run pytest            # run the test suite
uv run ruff check .      # lint
```

### Seeds & lexicon CLI

```bash
uv run chi-food-seeds seeds      # list normalized frontier seeds (dry run)
uv run chi-food-seeds lexicon    # summarize the topic lexicon
uv run chi-food-seeds check      # validate seeds + lexicon parse cleanly
```

### URL frontier

The frontier lives in Cloud SQL (Postgres); schema changes are managed with
Alembic. Set a database URL via `--dsn` or the `FRONTIER_DSN` env var (e.g. a
Cloud SQL Auth Proxy, or `sqlite:///frontier.db` for a local smoke test).

```bash
uv run chi-food-frontier --dsn "$FRONTIER_DSN" migrate      # alembic upgrade head
uv run chi-food-frontier --dsn "$FRONTIER_DSN" load-seeds   # load seeds into frontier
uv run chi-food-frontier --dsn "$FRONTIER_DSN" stats        # frontier counts by status

# Alembic directly (autogenerate a new revision after editing the schema):
FRONTIER_DSN=... uv run alembic revision --autogenerate -m "describe change"
FRONTIER_DSN=... uv run alembic upgrade head
```

### Robots & politeness

`crawler/robots/` enforces the Robots Exclusion Protocol and per-host spacing.
`parse_robots()` resolves `Allow`/`Disallow`/`Crawl-delay` for our user-agent
(`ChiFoodCrawler/0.1 (+mailto:...)`; set the contact via `CRAWLER_CONTACT_EMAIL`).
`PolitenessManager` fetches and caches robots.txt in `host_state` with a TTL,
authorizes individual paths, and advances `next_allowed_fetch_at` to honor
crawl-delay (one in-flight request per host). HTTP is injected as a
`RobotsFetcher`, so the real fetcher (component 6) plugs in without coupling.

### Fetcher

`crawler/fetcher/` is a polite HTTP client (`HttpClient`, over `httpx`) with
connect/read timeouts, bounded redirects, retries with exponential backoff on
network errors and `429`/`5xx`, and a streamed body-size cap. Each fetch returns
a `FetchOutcome` (status, body, `sha256:` content hash, timing, transport
errors captured rather than raised); `build_raw_record()` turns that plus
frontier context into the `RawCrawlRecord` metadata document from `plan.md`.
`make_robots_fetcher(client)` adapts the client into the politeness layer's
`RobotsFetcher`, wiring components 5 and 6 together.

## Infrastructure

The GCP foundation is managed with Terraform under `infra/terraform/`; see its
[README](./infra/terraform/README.md) for bootstrap and apply instructions.
