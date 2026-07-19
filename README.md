# Kist

**A self-hosted, local-first personal finance & career command center.**

A *kist* is an old word for the chest where you keep what's valuable — at home, in your own hands. This one turns scattered personal finances and career signals into one decision cockpit. Runs entirely on your machine — a Flask backend, a single SQLite file, and a vanilla-JS frontend with no build step.

> **Your data never leaves your machine.** Everything lives in one local SQLite file, stored **outside the repo** by default (`~/Library/Application Support/Kist` on macOS, `~/.local/share/kist` on Linux) — no database server, no cloud account. This repo ships **no personal data**, a first-run wizard sets you up, and a **demo mode** masks every figure for safe screenshots.

## What problems does it solve?

- **"My money is scattered across 10 apps and a spreadsheet"** — one dashboard: net worth, cash-flow, debts, goals, investments, taxes.
- **"When will I actually reach my goal?"** — month-by-month projections: goal ETA at your savings pace, FIRE/work-optional crossover, overpay-vs-invest scenarios with saved-interest math.
- **"Should I sell my vested stock? Overpay the mortgage? Convert currency now?"** — opinionated, data-grounded guidance: an FX signal engine with a historical backtest, RSU Monte-Carlo on real volatility, debt-overpayment simulations.
- **"I don't trust cloud finance apps"** — local-first by design; optional cloud integrations touch only *public market data*, never your numbers.
- **"AI assistants read my finances on someone else's server"** — here the AI is **built in and runs on your machine**: a local LLM reviews your recommendations, narrates forecasts and answers questions grounded in your own numbers — with an explicit, off-by-default switch if you ever want a cloud model's second opinion.
- **"Forecasts that admit what they don't know"** — research-grounded modeling: short-horizon **range forecasts** (EWMA volatility + empirical quantiles — because direction of a single stock/FX is not predictable, and the app doesn't pretend otherwise) and long-horizon labeled scenario bands. The forecast journal **grades itself daily** (band-coverage vs an 80% target) and **self-calibrates on its own past errors** (conformal calibration) — no black box, every band is explainable in one sentence.

## Quick start

```bash
git clone https://github.com/grzella/kist.git
cd kist
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
- **Built-in private AI** — the app never *requires* an LLM to function, and it ships the full client (`server/llm_local.py`) for a **local** [llama.cpp](https://github.com/ggml-org/llama.cpp) server, so AI features run on your machine and **your numbers never leave it**. See ["Local AI"](#local-ai-optional) below.
- **Commit tracker** — set `commit_repos` / `commit_author` in settings or `COMMIT_REPOS` / `COMMIT_AUTHOR` env vars.

## Built-in private AI

The AI is not an add-on here — it's a core feature, designed so it **runs on your machine**. The app ships the whole AI stack (client, grounding, prompt log, safety checks); the only thing it cannot ship is the model weights themselves (gigabytes, licensed separately) — you fetch a model once with a single command below, and everything lights up. No model running? Every AI feature degrades gracefully to "offline" and the rest of the app is unaffected.

**How the local LLM works.** You run a small open model (e.g. Qwen 2.5 3B) with [llama.cpp](https://github.com/ggml-org/llama.cpp)'s `llama-server` — a local process exposing an OpenAI-compatible API on `localhost`. The app talks to it over HTTP; no API keys, no data egress, no per-call cost. Because it speaks the OpenAI API, the same setup works with LM Studio or Ollama. Where the answer must be machine-readable, the app sends a **JSON Schema and llama.cpp enforces it at the token level** (GBNF grammars) — the model physically cannot return malformed output.

```bash
brew install llama.cpp        # or build from source; any OpenAI-compatible server works
llama-server -hf bartowski/Qwen2.5-3B-Instruct-GGUF:Q4_K_M --port 8080 --api-key <secret>
```

Then set `LOCAL_LLM_KEY=<secret>` (and optionally `LOCAL_LLM_URL`) in `.env`. Control Center shows the model's status, and the security review actively **probes the local server to confirm it rejects keyless requests**. Without a running server, AI features simply report "offline"; nothing breaks.

**What the AI actually does in the app:**

- **AI second opinion on Recommendations** — the rule engine computes recommendations from your data; the AI reviews them (agrees/disagrees, what's missing) with your own numbers as context. One click in the Recommendations tab.
- **Forecast narration** — turns the self-learning forecast journal into a plain-language *why*.
- **A grounded ask-anything box** (Control Center) plus a keyless `/api/llm/chat` hook for your own scripts.

**AI mode — local by default, cloud strictly opt-in.** The Control Center **AI mode** switch governs *all* of the above. Default: **local only** — every AI call stays on your machine. Flip to **local + Claude** and the app asks *both* engines, then **synthesizes one verdict** from the two answers (typically the best of both); the cloud model defaults to Anthropic's newest (`claude-fable-5`, configurable via `CLOUD_LLM_MODEL`). The UI warns plainly that this mode **sends the prompt and snippets of your data to Anthropic** — set your own `ANTHROPIC_API_KEY` in `.env` to enable it. All AI answers are framed by a rigorous financial-analyst system prompt (explicit assumptions, scenario ranges, opportunity-cost/tax, a one-line bottom line), and every question/answer is recorded in a **local prompt log** (Control Center) so you can see what was asked and whether the AI helps.

**Local RAG — answers grounded in your own numbers.** Before the AI answers, the app hands it the matching snippets of *your* data — goals, wealth items, offers, business entries, saved analyses, plus computed recommendations and reminders — from a local `rag_chunks` index (pure stdlib, fully offline). So the model reasons about your figures, not generic advice. Hit **Refresh memory** in Control Center after adding data.

Retrieval is **BM25 (lexical) out of the box**, and upgrades to a **BM25 + semantic hybrid** if you point it at a local embedding server — then a question can match by *meaning* even with different words or across languages ("saving for retirement" finds your "pension account"):

```bash
llama-server -hf <embedding-model-GGUF> --embeddings --port 8081
# in .env:
LOCAL_EMBED_URL=http://127.0.0.1:8081/v1
```

Embeddings are stored per chunk (L2-normalized) and cosine similarity is computed in plain Python — no vector DB, no SQLite extension. Without an embedding server everything stays lexical; Control Center shows how many chunks are embedded.

## Backups

Your data is one local SQLite file, so a backup is just a copy — but a copy you don't have to think about. Control Center's **Data backup** card writes a consistent snapshot (SQLite's online-backup API, WAL-safe) into a folder your desktop **Google Drive / Dropbox / iCloud** client already syncs. The app itself talks to **no** cloud API and holds **no** OAuth keys — your own sync client pushes the file. Common synced folders are auto-detected; the last 14 snapshots are kept. For at-rest encryption, `pip install cryptography` and set `BACKUP_KEY` in `.env` — snapshots are then Fernet-encrypted before they touch the cloud.

## Data & privacy

- **Everything is local out of the box.** No account, no server, no cloud dependency — the whole app runs against a single local SQLite file. Live market data and alerts are the only cloud touchpoints, and they're opt-in (see above).
- **Your data lives outside the repo by default.** A fresh clone stores its database in a per-user app-data dir (`~/Library/Application Support/Kist` on macOS, `~/.local/share/kist` on Linux) — so a stray `git add` can't stage your finances. An existing `./.finance/` keeps working in place, and `FINANCE_PROJECT_DIR=/path ./run.sh` overrides the location.
- `.finance/`, `.env`, and `backups/` are git-ignored — **never commit them**.
- `seed.py` refuses to overwrite existing data (use `--force` only on a throwaway DB).
- **Demo mode** (Control Center or `?demo`) masks all figures with a `0-1` pattern and hides chart axis values — safe screenshots.
- **Language**: UI is English-native with a Polish toggle (Control Center or `?lang=pl`); i18n contributions welcome.

## Security & tests

This repo is built to be safe to fork and contribute to:

- `server/security_review.py` — a pentest-style suite: secret scan of the working tree **and the full git history**, dangerous-pattern static analysis (eval/exec, shell, SQL injection, debug, network binds), maintainer personal-data audit, config hygiene, endpoint smoke tests, and an **active probe of any local LLM server** (must reject keyless requests).
- Runs three ways: **Control Center button**, CLI (`cd server && python -m security_review --ci`), and **GitHub Actions** on every push/PR + weekly ([`.github/workflows/security.yml`](.github/workflows/security.yml)).
- **Real test suite** — `pytest` in [`tests/`](tests/) (endpoint smoke across every GET route, goals/wealth CRUD, forecast math, RAG ranking incl. the semantic hybrid, backup/restore round-trip). CI enforces a **coverage floor** and a **bandit** security-lint gate; **Dependabot** watches dependencies. Run locally: `python -m pytest -q`.

## Tech

Python 3 + Flask, SQLite (WAL, single file), vanilla JS + Chart.js. Self-contained SQLite layer (`server/db.py`) — no dependencies beyond Flask.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for setup, the two CI gates, and ground rules. Good first areas: i18n (new languages), market-data adapters, new forecast models, and UX. Clone, run `./run.sh`, load sample data via the wizard, and you have a working playground.

## License

MIT © Łukasz Grzella
