# food-crawl

A production-style, GCP-native platform that crawls Chicago restaurant food
blogs and curates a clean, train-ready text corpus. See [`plan.md`](./plan.md)
for the full architecture, design principles, and the implementation todo list.

## Layout

```text
infra/terraform/   # Milestone 1: GCP foundation (VPC, GCS, Cloud SQL, IAM, ...)
crawler/           # focused crawler components
  seeds/           # seed list + topic lexicon (targeting inputs)
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

## Infrastructure

The GCP foundation is managed with Terraform under `infra/terraform/`; see its
[README](./infra/terraform/README.md) for bootstrap and apply instructions.
