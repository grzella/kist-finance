# Finance & Career Command Center

A **self-hosted, local-first** web app that turns scattered personal finances and career signals into one decision cockpit. Runs entirely on your machine — a Flask backend, a single SQLite file, and a vanilla-JS frontend with no build step.

> **Your data never leaves your machine.** Everything lives in one local, git-ignored file (`.finance/finance.db`) — there is no database server to install and no cloud account required. This repo ships **no personal data**, a first-run wizard sets you up, and a **demo mode** masks every figure for safe screenshots.

## What problems does it solve?

- **"My money is scattered across 10 apps and a spreadsheet"** — one dashboard: net worth, cash-flow, debts, goals, investments, taxes.
- **"When will I actually reach my goal?"** — month-by-month projections: goal ETA at your savings pace, FIRE/work-optional crossover, overpay-vs-invest scenarios with saved-interest math.
- **"Should I sell my vested stock? Overpay the mortgage? Convert currency now?"** — opinionated, data-grounded guidance: an FX signal engine with a historical backtest, RSU Monte-Carlo on real volatility, debt-overpayment simulations.
- **"I don't trust cloud finance apps"** — local-first by design; optional cloud integrations touch only *public market data*, never your numbers.
- **"Forecasts that admit what they don't know"** — research-grounded modeling: short-horizon **range forecasts** (EWMA volatility + empirical quantiles — because direction of a single stock/FX is not predictable, and the app doesn't pretend otherwise) and long-horizon labeled scenario bands. The forecast journal **grades itself daily** (band-coverage vs an 80% target) and **self-calibrates on its own past errors** (conformal calibration) — no black box, every band is explainable in one sentence.

## Quick start

```bash
git clone https://github.com/grzella/financeapp.git
cd financeapp
pip install -r requirements.txt
./run.sh                      # → opens http://127.0.0.1:8321
```

That's it. On first launch a **setup wizard** walks you through:
1. **Modules** — enable only what fits your life (see below).
2. **Data** — load a fake sample persona to look around, or start empty with your own numbers.
3. **Integrations** — optional; skip freely, the app is fully functional offline.

Re-run the wizard anytime at `http://127.0.0.1:8321/#wizard`. Use a different port with `PORT=8400 ./run.sh`.

## Modules

Core (always on): **Dashboard · Cash-flow · Recommendations · Wealth · Allocation · Goals · Forecasts · Control Center**.

Optional — toggle in the wizard, disabled ones disappear from the UI:

| Module | What it adds |
|---|---|
| 🏠 Loans & mortgage | principal/interest split, effective rate, overpayment scenarios |
| 🏛️ Taxes | consolidated tax sources + payment calendar |
| 📈 Markets & FX | watchlist, price analytics, currency signal engine with backtest |
| 💎 Equity / RSU | vesting schedule, Monte-Carlo projection, sell-vs-hold guidance |
| 🚁 Side business | revenue/costs of self-employment or a side company |
| 💼 Career tracker | inbound job offers, market barometer, commit-activity tracker |
| 🏡 Property analysis | deep-dive for a property-purchase goal |

## Connecting your own services (all optional)

The app **runs fully offline**. Live market data and alerts are opt-in:

- **Market data (stock/FX quotes)** — the app reads public prices from a Supabase table:
  1. Create a free [Supabase](https://supabase.com) project with tables `market_prices` (`ticker, date, close, currency`) and `market_watchlist` (`ticker, notes`).
  2. Put keys in `.env` (copy `.env.example`): `SUPABASE_URL=…`, `SUPABASE_ANON_KEY=…`.
  3. Feed the table daily however you like — e.g. an [n8n](https://n8n.io) workflow pulling quotes from Yahoo/Stooq. Without this, market views simply show "no data".
- **Data-freshness alerts (n8n → Telegram)** — importable workflow in [`integrations/n8n/`](integrations/n8n/) that messages you when the pipeline goes stale. Setup guide in its README.
- **Local AI (optional, fully private)** — the app never *requires* an LLM, but it ships a thin client (`server/llm_local.py`) for a **local** [llama.cpp](https://github.com/ggml-org/llama.cpp) server, so AI features run on your machine and **your numbers never leave it**. See ["Local AI"](#local-ai-optional) below.
- **Commit tracker** — set `commit_repos` / `commit_author` in settings or `COMMIT_REPOS` / `COMMIT_AUTHOR` env vars.

## Local AI (optional)

Cloud finance assistants send your balances to someone else's server. This app takes the opposite route: point it at a **local** model and every AI feature runs on your machine — no API keys, no data egress, no per-call cost.

**What it gives you concretely:**

- **Private transaction categorization** — label imported transactions ("BIEDRONKA 4231" → "Groceries") without shipping your spending to a cloud API. `categorize_transaction()` returns a category in well under a second on a small model.
- **Plain-language narration over your own data** — e.g. `explain_forecast_miss()` turns the self-learning forecast journal into a sentence ("the band was too tight because earnings gapped the stock"), so the numbers come with a *why*.
- **A private, keyless `/api/llm/chat`** — a generic hook other features (or your own scripts) can call to summarize, extract, or draft over sensitive figures, all offline.
- **Zero lock-in** — it speaks the OpenAI API, so the same code works against `llama.cpp`, LM Studio, or Ollama; swap the model with one flag.

**Enable it:**

```bash
brew install llama.cpp        # or build from source; any OpenAI-compatible server works
llama-server -hf bartowski/Qwen2.5-3B-Instruct-GGUF:Q4_K_M --port 8080 --api-key <secret>
```

Then set `LOCAL_LLM_KEY=<secret>` (and optionally `LOCAL_LLM_URL`) in `.env`. Control Center shows the model's status, and the security review actively **probes the local server to confirm it rejects keyless requests** — a local model on `localhost:8080` with no key is reachable by any web page in your browser, so the suite flags an unprotected one. Without a running server, AI features simply report "offline"; nothing breaks.

**AI mode — local by default, cloud strictly opt-in.** Control Center has an **AI mode** switch. The default is **local only**: every AI question stays on your machine. Optionally flip it to **local + Claude**, which asks *both* your local model and Anthropic's Claude and shows the answers side by side — often the best of the two — with a plain warning that this mode **sends the prompt to Anthropic**. Cloud is never on unless you turn it on; set your own `ANTHROPIC_API_KEY` in `.env` to enable it. AI answers are framed by a rigorous financial-analyst system prompt (explicit assumptions, scenario ranges, opportunity-cost/tax, a one-line bottom line).

**Local RAG — answers grounded in your own numbers.** A pure-stdlib retriever (zero dependencies, fully offline) indexes your own data — goals, wealth, offers, business entries, saved analyses, plus computed recommendations and reminders — into a `rag_chunks` table. Every AI question is automatically grounded in the most relevant snippets, so the model reasons about *your* figures, not generic ones. Hit **Reindex** in Control Center after adding data.

Retrieval is **BM25 (lexical) out of the box**, and upgrades to a **BM25 + semantic hybrid** if you point it at a local embedding server — then a question can match by *meaning* even with different words or across languages ("saving for retirement" finds your "pension account"). To enable it, run an embedding model and set two env vars, then Reindex:

```bash
llama-server -hf <embedding-model-GGUF> --embeddings --port 8081
# in .env:
LOCAL_EMBED_URL=http://127.0.0.1:8081/v1
# LOCAL_EMBED_MODEL=...   # optional, if the server needs an explicit model id
# LOCAL_EMBED_KEY=...     # optional, if the embedding server requires a key
```

Embeddings are stored per chunk (L2-normalized) and cosine similarity is computed in plain Python — no vector DB, no SQLite extension. Without an embedding server, everything stays lexical and works exactly as before; Control Center shows how many chunks are embedded.

## Backups

Your data is one local SQLite file, so a backup is just a copy — but a copy you don't have to think about. Control Center's **Data backup** card writes a consistent snapshot (SQLite's online-backup API, WAL-safe) into a folder your desktop **Google Drive / Dropbox / iCloud** client already syncs. The app itself talks to **no** cloud API and holds **no** OAuth keys — your own sync client pushes the file. Common synced folders are auto-detected; the last 14 snapshots are kept. For at-rest encryption, `pip install cryptography` and set `BACKUP_KEY` in `.env` — snapshots are then Fernet-encrypted before they touch the cloud.

## Data & privacy

- **Everything is local out of the box.** No account, no server, no cloud dependency — the whole app runs against a single local SQLite file. Live market data and alerts are the only cloud touchpoints, and they're opt-in (see above).
- **Your data lives outside the repo by default.** A fresh clone stores its database in a per-user app-data dir (`~/Library/Application Support/financeapp` on macOS, `~/.local/share/financeapp` on Linux) — so a stray `git add` can't stage your finances. An existing `./.finance/` keeps working in place, and `FINANCE_PROJECT_DIR=/path ./run.sh` overrides the location.
- `.finance/`, `.env`, and `backups/` are git-ignored — **never commit them**.
- `seed.py` refuses to overwrite existing data (use `--force` only on a throwaway DB).
- **Demo mode** (Control Center or `?demo`) masks all figures with a `0-1` pattern and hides chart axis values — safe screenshots.
- **Language**: UI is English-native with a Polish toggle (Control Center or `?lang=pl`); i18n contributions welcome.

## Security

This repo is built to be safe to fork and contribute to:

- `server/security_review.py` — a pentest-style suite: secret scan of the working tree **and the full git history**, dangerous-pattern static analysis (eval/exec, shell, SQL injection, debug, network binds), maintainer personal-data audit, config hygiene, and endpoint smoke tests.
- Runs three ways: **Control Center button**, CLI (`cd server && python -m security_review --ci`), and **GitHub Actions** on every push/PR + weekly ([`.github/workflows/security.yml`](.github/workflows/security.yml)).

## Tech

Python 3 + Flask, SQLite (WAL, single file), vanilla JS + Chart.js. Self-contained SQLite layer (`server/db.py`) — no dependencies beyond Flask.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Contributing

Issues and PRs welcome — i18n (English strings!), market-data adapters, new forecast models, and UX especially. Clone, run `./run.sh`, load sample data via the wizard, and you have a working playground. CI runs the security suite on every PR.

## License

MIT © Łukasz Grzella
