# Kist

**A self-hosted, local-first personal finance & career command center.**

A *kist* is an old word for the chest where you keep what's valuable — at home, in your own hands. This one turns scattered personal finances and career signals into one decision cockpit. Runs entirely on your machine — a Flask backend, a single SQLite file, and a vanilla-JS frontend with no build step.

**[▶ Try the live demo](https://grzella.github.io/kist-finance/)** — the real UI with a fake persona ("Alex Demo"), fully clickable, read-only. Static snapshots on GitHub Pages; nothing you click is saved and no backend is involved.

> **Your data never leaves your machine.** Everything lives in one local SQLite file, stored **outside the repo** by default (`~/Library/Application Support/Kist` on macOS, `~/.local/share/kist` on Linux) — no database server, no cloud account. This repo ships **no personal data**, a first-run wizard sets you up, and a **demo mode** masks every figure for safe screenshots.

## What problems does it solve?

Mostly my own. Too many apps to check, a spreadsheet I kept forgetting to update, and a nagging feeling that every finance tool out there wants my data in its cloud more than it wants to help me. So I built the small local tool I actually wanted — nothing revolutionary, it just answers my own everyday questions. If it answers yours too, great; that's the only reason it's public.


- **"My money is scattered across 10 apps and a spreadsheet"** — one dashboard: net worth, cash-flow, debts, goals, investments, taxes.
- **"When will I actually reach my goal?"** — month-by-month projections: goal ETA at your savings pace, FIRE/work-optional crossover, overpay-vs-invest scenarios with saved-interest math.
- **"Should I sell my vested stock? Overpay the mortgage? Convert currency now?"** — opinionated, data-grounded guidance: an FX signal engine with a historical backtest, RSU Monte-Carlo on real volatility, debt-overpayment simulations.
- **"I don't trust cloud finance apps"** — local-first by design; optional cloud integrations touch only *public market data*, never your numbers.
- **"Is the world nervous today?"** — a 🌍 **Risk Radar** in the Markets tab: VIX, gold, oil and USD with explicit thresholds blended into one calm/elevated/hot reading, backfilled a month and refreshed daily — an honest, measurable take on the meme "pizza index" idea (it contextualizes; it doesn't predict).
- **"AI assistants read my finances on someone else's server"** — here the AI is **built in and runs on your machine**: a local LLM reviews your recommendations, narrates forecasts and answers questions grounded in your own numbers — with an explicit, off-by-default switch if you ever want a cloud model's second opinion.
- **"Forecasts that admit what they don't know"** — research-grounded modeling: short-horizon **range forecasts** (EWMA volatility + empirical quantiles — because direction of a single stock/FX is not predictable, and the app doesn't pretend otherwise) and long-horizon labeled scenario bands. The forecast journal **grades itself daily** (band-coverage vs an 80% target) and **self-calibrates on its own past errors** (conformal calibration) — no black box, every band is explainable in one sentence.

## Quick start

```bash
git clone https://github.com/grzella/kist-finance.git
cd kist
pip install -r requirements.txt
./run.sh                      # → opens http://127.0.0.1:8321
```

That's it. On first launch a **setup wizard** walks you through:
1. **Modules** — enable only what fits your life (see below).
2. **Data** — three ways to start: load a **fake sample persona** to look around, start **empty** and type your own numbers, or pick **"Set it up with an AI assistant"** — a copyable onboarding prompt that has any AI assistant interview you and fill the app tab by tab (with a privacy warning: cloud assistants take your answers off localhost).
3. **Integrations** — optional; skip freely, the app is fully functional offline.

Re-run the wizard anytime at `http://127.0.0.1:8321/#wizard`. Use a different port with `PORT=8400 ./run.sh`.

## Modules

Core (always on):

| Module | What it does |
|---|---|
| 📊 Dashboard | net worth and key figures at a glance |
| 💸 Cash-flow | income vs. expenses, monthly surplus |
| 💡 Recommendations | rule-engine guidance from your data (+ optional AI) |
| 💎 Wealth | assets and net worth over time, with snapshots |
| 🥧 Allocation | portfolio breakdown vs. targets, 5/25 drift |
| 🎯 Goals | savings goals with ETA as a range |
| 🔮 Forecasts | range forecasts, FIRE crossover, stress test + guardrails |
| 🛠️ Control Center | status, AI mode, prompt log, backups, security review |

Optional — toggle in the wizard, disabled ones disappear from the UI:

| Module | What it adds |
|---|---|
| 🏠 Loans & mortgage | principal/interest split, effective rate, overpayment scenarios |
| 🏛️ Taxes | consolidated tax sources + payment calendar |
| 📈 Markets & FX | watchlist, price analytics, currency signal engine with backtest, daily 🌍 Risk Radar, on-demand keyless history backfill |
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
  - For any watchlist symbol the nightly sync doesn't cover deeply, a per-ticker **Deepen history** action backfills its full history straight from Yahoo (keyless, no setup) so the chart and indicators have depth.
- **Data-freshness alerts (n8n → Telegram)** — importable workflow in [`integrations/n8n/`](integrations/n8n/) that messages you when the pipeline goes stale. Setup guide in its README.
- **Market barometer (two streams, built-in collectors)** — the Career tab's barometer tracks demand for **your roles** (configurable roles + geography, edited in the tab) as two series per role: **📈 demand** (Google Trends search interest — keyless, with history, collected monthly by the app's `barometer_collect` schedule, one-off `backfill()` for history) and **🎯 openings** (real posting counts via JSearch/Google for Jobs — set `RAPIDAPI_JSEARCH_KEY`). Shown as an **index (base 100) + trend** per role×stream (demand solid, openings dashed), not a raw count. External collectors still work via `POST /api/market-barometer` — two importable n8n workflows ([`barometer-jsearch-collector.json`](integrations/n8n/), [`barometer-apify-collector.json`](integrations/n8n/)) remain an alternative; see their README for the methodology.
- **Stress test & withdrawal guardrails** — a deterministic "financial fire drill" (stocks −25%, rates +2pp, income stops) plus a Guyton-Klinger dynamic-withdrawal policy with guardrails in Forecasts; allocation drift follows the 5/25 rebalancing rule with editable targets.
- **Built-in private AI** — the app never *requires* an LLM to function, and it ships the full client (`server/llm_local.py`) for a **local** [llama.cpp](https://github.com/ggml-org/llama.cpp) server, so AI features run on your machine and **your numbers never leave it**. See ["Built-in private AI"](#built-in-private-ai) below.
- **Commit tracker** — set `commit_repos` / `commit_author` in settings or `COMMIT_REPOS` / `COMMIT_AUTHOR` env vars.

## Built-in private AI

The AI is not an add-on here — it's a core feature, designed so it **runs on your machine**. The app ships the whole AI stack (client, grounding, prompt log, safety checks); the only thing it cannot ship is the model weights themselves (gigabytes, licensed separately) — you fetch a model once with a single command below, and everything lights up. No model running? Every AI feature degrades gracefully to "offline" and the rest of the app is unaffected.

**How the local LLM works.** You run a small open model (recommended: **Qwen3 8B** — its toggleable thinking mode measurably helps multi-step financial math; any GGUF works) with [llama.cpp](https://github.com/ggml-org/llama.cpp)'s `llama-server` — a local process exposing an OpenAI-compatible API on `localhost`. The app talks to it over HTTP; no API keys, no data egress, no per-call cost. Because it speaks the OpenAI API, the same setup works with LM Studio or Ollama. Where the answer must be machine-readable, the app sends a **JSON Schema and llama.cpp enforces it at the token level** (GBNF grammars) — the model physically cannot return malformed output. On Qwen3 the app toggles thinking per task: on for analysis, off for quick structured calls.

```bash
brew install llama.cpp        # or build from source; any OpenAI-compatible server works
llama-server -hf bartowski/Qwen3-8B-GGUF:Q4_K_M --port 8080 --api-key <secret> \
    --spec-type ngram-simple  # free speedup: drafts repeated n-grams (great for JSON), no second model needed
```

Then set `LOCAL_LLM_KEY=<secret>` (and optionally `LOCAL_LLM_URL`) in `.env`. Control Center shows the model's status, and the security review actively **probes the local server to confirm it rejects keyless requests**. Without a running server, AI features simply report "offline"; nothing breaks.

**What the AI actually does in the app:**

- **AI second opinion on Recommendations** — the rule engine computes recommendations from your data; the AI reviews them (agrees/disagrees, what's missing) with your own numbers as context. One click in the Recommendations tab.
- **Forecast narration** — turns the self-learning forecast journal into a plain-language *why*.
- **A grounded ask-anything box** (Control Center) plus a keyless `/api/llm/chat` hook for your own scripts.
- **It checks real numbers, not vibes** — the local model gets one tool: a **read-only SQL SELECT** against your database (`server/db_tools.py`). Asked "how far am I from my goals?", it queries the actual tables instead of guessing from text snippets. Defense in depth: the connection is opened read-only at the SQLite level, only a single SELECT passes validation, results are capped, and every round-trip lands in the prompt log — and the security review **actively pentests this guard** (injection/DDL/stacked-query payloads must all be refused). Servers without tool support just fall back to plain answers.

**AI mode — local by default, cloud strictly opt-in.** The Control Center **AI mode** switch governs *all* of the above. Default: **local only** — every AI call stays on your machine. Flip to **local + Claude** and the app asks *both* engines, then **synthesizes one verdict** from the two answers (typically the best of both); the cloud model defaults to Anthropic's newest (`claude-fable-5`, configurable via `CLOUD_LLM_MODEL`). The UI warns plainly that this mode **sends the prompt and snippets of your data to Anthropic** — set your own `ANTHROPIC_API_KEY` in `.env` to enable it. All AI answers are framed by a rigorous financial-analyst system prompt (explicit assumptions, scenario ranges, opportunity-cost/tax, a one-line bottom line), and every question/answer is recorded in a **local prompt log** (Control Center) so you can see what was asked and whether the AI helps.

**Local RAG — answers grounded in your own numbers.** Before the AI answers, the app hands it the matching snippets of *your* data — goals, wealth items, offers, business entries, saved analyses, plus computed recommendations and reminders — from a local `rag_chunks` index (pure stdlib, fully offline). So the model reasons about your figures, not generic advice. The index **maintains itself**: any data write marks it stale and it reindexes before the next AI answer (plus a scheduled refresh); the **Refresh memory** button in Control Center remains for forcing it.

Retrieval is **BM25 (lexical) out of the box**, and upgrades to a **BM25 + semantic hybrid** if you point it at a local embedding server — then a question can match by *meaning* even with different words or across languages ("saving for retirement" finds your "pension account"):

```bash
# recommended: Qwen3-Embedding-0.6B (~600 MB, strong multilingual retrieval)
llama-server -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --embeddings --pooling last \
  --batch-size 2048 --ubatch-size 2048 --port 8081
# in .env:
LOCAL_EMBED_URL=http://127.0.0.1:8081/v1
```

Embeddings are stored per chunk (L2-normalized) and cosine similarity is computed in plain Python — no vector DB, no SQLite extension. Without an embedding server everything stays lexical; Control Center shows how many chunks are embedded. Two hard-won notes: **raise `--ubatch-size`** — non-English text tokenizes densely, and with the default 512 a ~2000-char chunk can crash `llama-server` mid-reindex (the app then quietly falls back to lexical); and **run the server persistently** (launchd/systemd), because the self-maintaining reindex embeds new data only while the server is up — if it's down, the rebuilt index degrades to BM25 until the next reindex with the server alive. That degrade-and-recover contract is covered by a regression test.

Optionally add a **third retrieval stage — a reranker**: the hybrid picks ~20 candidates, a small cross-encoder re-orders them by true relevance and only the top few reach the model. Same graceful pattern:

```bash
llama-server -hf gpustack/bge-reranker-v2-m3-GGUF --embedding --pooling rank --port 8082
# in .env:
LOCAL_RERANK_URL=http://127.0.0.1:8082/v1
```

**Experience distillation — the assistant learns from its good answers.** When an answer is genuinely useful, one click (**💡 Learn from this**, in the Control Center prompt log) asks the model to compress that Q&A into a single *transferable* lesson — the method and the pitfall, not your specific numbers. The lesson is stored, indexed into the same RAG memory, and **injected as guidance on future similar questions** — so the assistant gets better over time without any retraining or weight changes (the pattern from *AI Agents in Depth*, ch. 8). It's deliberately human-gated: only answers you mark become lessons (no auto-noise), and a **🧠 Learned experiences** panel lets you prune any that don't hold up. Everything stays local.

**Market brief — daily & weekly, written by the AI.** The Markets tab keeps two briefs: a **daily** one (regenerated every morning) and a **weekly** one (Monday mornings) — toggle between them in the tab. Each is generated from your cached quotes and the risk-radar state by the engine your **AI mode** selects (local only, or cloud-first with local fallback in local+Claude mode), schema-locked so it always renders. The daily view has a **🔄 Fetch latest** button: it pulls fresh quotes and rewrites the brief on the spot (e.g. you open the app at noon and want more than the morning run). You can still paste your own brief (weekly box) — a saved brief is never overwritten by a failed generation. Cadence is editable in Data → Schedules.

**Risk-radar Telegram alert.** When the radar composite goes hot (🔴, ≥4/8), the app can ping you on Telegram — **a signal to investigate, not to act**. Two ways, pick either:

1. *Built-in (app running):* set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in `.env` — the daily radar snapshot sends the alert itself (at most once a day, with the drivers and the AI one-liner).
2. *Standalone (works with the app off):* import `integrations/n8n/risk-radar-telegram-alert.json` into n8n — it recomputes the same composite from Yahoo every morning and alerts on the same threshold.

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

- **Loopback hardening (no auth by design).** The API is keyless because the model is "one user, on their own machine, over loopback." A `before_request` guard defends the two attacks that need only your browser: it **rejects any non-loopback `Host`** (DNS rebinding) and **blocks cross-origin state-changing requests** (CSRF). Defense in depth: a strict **Content-Security-Policy** (`script-src 'self'`) neutralizes injected markup even in unescaped fields, external data (e.g. Supabase market text) is HTML-escaped, and RAG/DB content is framed to the model as *data, not instructions*. **Do not expose the app beyond `127.0.0.1`** — see [SECURITY.md](SECURITY.md) for the full threat model.
- `server/security_review.py` — a pentest-style suite: secret scan of the working tree **and the full git history**, dangerous-pattern static analysis (eval/exec, shell, SQL injection, debug, network binds), maintainer personal-data audit, config hygiene, endpoint smoke tests, an **active probe of any local LLM server** (must reject keyless requests), an **active pentest of the AI's SQL tool** (injection/DDL/stacked-query payloads must all be refused, the connection read-only at the SQLite layer), and an **active pentest of the web guard** — a forged `Host` and a cross-origin write must both return 403, so a regression fails the build.
- Runs three ways: **Control Center button**, CLI (`cd server && python -m security_review --ci`), and **GitHub Actions** on every push/PR + weekly ([`.github/workflows/security.yml`](.github/workflows/security.yml)).
- **Real test suite** — `pytest` in [`tests/`](tests/) (endpoint smoke across every GET route, goals/wealth CRUD, forecast math, RAG ranking incl. the semantic hybrid, backup/restore round-trip, the wizard's module→view gating). CI enforces a **coverage floor** and a **bandit** security-lint gate; **Dependabot** watches dependencies. Run locally: `python -m pytest -q`.
- **LLM contract tests** ([`tests/test_llm_contract.py`](tests/test_llm_contract.py)) — a distinct kind of test for the AI surface: the model is *mocked* and the tests assert the invariants the app guarantees **around** it (rather than what it says). Graceful degradation when the model is offline, the shared pipeline always logs and returns a `best`, local mode never calls the cloud, and a failed brief never overwrites the last good one — the harness contract, kept deterministic and fast.

## Tech

Python 3 + Flask, SQLite (WAL, single file), vanilla JS + Chart.js. Self-contained SQLite layer (`server/db.py`) — no dependencies beyond Flask.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for setup, the two CI gates, and ground rules. Good first areas: i18n (new languages), market-data adapters, new forecast models, and UX. Clone, run `./run.sh`, load sample data via the wizard, and you have a working playground.

## License

MIT © Łukasz Grzella
