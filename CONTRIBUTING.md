# Contributing

Thanks for considering a contribution! This is a **local-first** personal-finance
app — Python 3 + Flask + a single SQLite file + vanilla JS, no build step. The
guiding principles are: your data stays on your machine, dependencies stay
minimal, and the repo stays generic (no maintainer-specific data).

## Dev setup

```bash
git clone https://github.com/grzella/kist-finance.git
cd kist-finance
pip install -r requirements.txt -r requirements-dev.txt
./run.sh                       # → http://127.0.0.1:8321
```

On first launch a wizard lets you load a fake sample persona (or start empty).
You can also seed a throwaway DB directly:

```bash
FINANCE_PROJECT_DIR=$(mktemp -d) python seed.py
```

## Before you open a PR

Both of these run in CI on every PR — run them locally first:

```bash
python -m pytest -q                          # tests must pass
cd server && python -m security_review --ci  # must exit 0 (no blockers)
```

### Tests that touch the AI: mock both local-model paths

`_ai_answer` prefers tool-calling: when `db_tools.schema_summary()` returns a schema
(almost always), it calls `llm_local.chat_with_tools`, not `llm_local.chat`. A test
that mocks only `chat` **silently hits the real local model**. It passes in isolation
(the model answers, ~35s) but fails in a full suite run when the model is busy, with
a misleading `AI offline`. Mock both functions, which also keeps the test fast and
independent of load, or mark the test as an integration test on purpose.

## Ground rules

- **Runtime dependencies: Flask only.** Prefer the standard library. If a change
  truly needs another package, raise it in an issue first — most things (RAG,
  backups, forecasting) are built on stdlib on purpose.
- **Keep it generic.** No real names, employers, cities, or personal figures in
  code — the security review's personal-data audit will fail the build. Real data
  belongs only in your local, git-ignored `.finance/`.
- **Local-first.** The server binds to `127.0.0.1`; cloud integrations
  (Supabase, n8n, a cloud LLM) are always opt-in and never required.
- **Never commit** `.finance/`, `.env`, or `backups/` (they're git-ignored).
- **Match the surrounding code.** Vanilla JS, no framework, no bundler; Python in
  the existing style. Add a test when you add behavior.

## Good first contributions

- **i18n** — the UI is English-only; translation dictionaries and new languages
  are welcome (`static/js/app.js`).
- **Market-data adapters** — alternatives to the Supabase reader (Stooq, Yahoo…).
- **New forecast models** — the forecast journal grades itself; add a model and
  let it compete on band-coverage.
- **UX polish** — the frontend is plain HTML/CSS/JS, easy to iterate on.

## Reporting bugs / requesting features

Open an issue using the templates. For security-sensitive reports, please avoid
posting secrets or real data in the issue.
