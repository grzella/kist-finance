# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are dates (no semver yet — pre-1.0).

## [Unreleased]

### Fixed (2026-10-08)
- **Empty or cut-off local answers with the SQL tool**: Qwen3 thinking was left on in `chat_with_tools` and the reasoning used the whole 700-token budget (`finish_reason: length`). Thinking is now off there, an empty answer counts as no answer, and the plain-chat fallback runs without thinking too.
- **The tool path lives in `db_tools.ask_local()`**, shared by the app and the local eval, so the eval measures the answer the user sees.
- **⚠️ on numbers not found in your data**: the answer lists numbers that appear neither in the context, the question nor the SQL results (computed, rounded or made up); also returned as `unsourced_numbers`.

### Ported from the private instance (2026-10-07)
- **🎓 AI improvement tab** (Control Center → `#ai`, `server/ai_improve.py`, `/api/ai/improve`): AI mode, the ask box, the prompt log and learned lessons moved here from the main Control view, plus a red / amber / green checklist of the learning loop (model, RAG memory, ratings, lessons, quality eval, recommendation outcomes, forecasts, data freshness, failing scheduled tasks) sorted by urgency, and an improvement roadmap with evidence and a success criterion per item.
- **👍/👎 on answers** (`POST /api/llm/log/<id>/rating`, values -1 / 0 / 1): ratings are attributed to the lessons that were in the answer's context (by lesson id), the lessons list shows uses and ratings and flags lessons that hurt more than they help; "Learn from this" counts as 👍. At most one lesson enters the RAG context. Distilled lessons are trimmed to whole sentences.
- **Scheduled quality eval** (`ai_eval` task, `ai_eval_cmd` setting): runs only when the model, the question set or the 30-day window changed, and records its result in `<data>/eval/`.
- **Incremental RAG reindex**: embeddings of unchanged chunks are carried over and the "new data" flag is cleared by the reindex itself; the response reports chunks, embedded, reused and seconds. Loan chunks include the fixed-rate end and remaining installments.
- **Forecast calibration verdicts** count non-overlapping windows; a gap from 80% within binomial noise reads "too few windows". FIRE snapshots freeze the planned monthly inflow, so editing the plan does not rewrite how past months score.
- **Recommendations**: a rewording with new numbers supersedes the previous entry (outcome "obsolete") and keeps its age, instead of piling up "resolved without an outcome".
- **Barometer**: a 🗂️ job-boards stream (No Fluff Jobs postings per role, keyless, `barometer_boards`).
- **Restart from the stale-code banner** (`POST /api/restart`); `run.sh` stops whoever owns the port.
- **Monte Carlo cone** in the RSU tab: axis titles and tooltips with the month, share count, amount and price.
- **Long analysis text** (career, market brief, RSU deep-dive) renders as short paragraphs and lists (`paras()` in `api.js`, which escapes what it emits).
- **Security review**: the request-cap check no longer calls the model, tests are excluded from the dangerous-pattern grep, SQL identifiers go through `_ident()`, and `ai.js` is covered by the XSS view check.
- **Demo**: the AI improvement tab ships with a coherent sample story (rated answers, lessons in use, three eval runs, an indexed memory).

### Ported from the private instance (2026-10-06)
- **Investment policy card** in Forecasts (`/api/invest-plan`, `planner_fire.invest_plan`): a model portfolio for money with no goal (core / bonds / themes / satellites / sandbox, weights from the `invest_model` setting), the brokerage positions from Wealth sorted into buckets (employer stock excluded), a buy list that splits the next vest and the surpluses until then across the buckets below weight (nothing sold), a 5/10/15-year projection at 4% / blended / 9%, and an optional themes plan (`invest_themes` setting) with cached prices and 1-year change.
- **Broker-confirmed vest total** (`confirmed_shares_per_vest`, `confirmed_until` in the RSU grant parameters): the broker's shares-per-vest overrides the pricing-window estimate until the given month, the difference shows up as a "broker correction" source so Career and Cash-flow sum what the broker shows.
- **Forecasts fold completed scenarios**: once no loan is left to overpay, the loan scenarios move to a collapsed "Completed" section at the bottom instead of showing an empty calculator on top.

### Ported from the private instance (2026-10-01)
- **Barometer watchlist stream** (`barometer_collect.collect_watchlist`, monthly `barometer_watchlist` task): counts real open roles for your configured roles at an editable list of companies, read keyless from their public Greenhouse / Lever / Ashby boards. Only postings in Europe or remote without a restriction to another continent count; sales / solutions / support engineering roles are skipped and a role posted once per country counts once. The built-in `em` / `head` role keys use title families (Senior/Staff EM, Head/Director); other roles match their query. Edited in ⚙️ next to roles and geography; the latest snapshot's matches are listed under the table.
- **Indeed Hiring Lab stream** (`collect_hiringlab`, monthly `barometer_hiringlab` task): Software Development and "IT broad" (four Indeed IT sectors) posting indices averaged over GB/DE/FR, drawn as dotted lines; a country lacking a sector averages the ones it has. Rewrites the whole series each run without duplicating rows.
- **Career view**: Google Trends renamed to *interest* (it measures searches, so its reading says "falling", not "shrinking"), readings as tiles, a watchlist numbers row above the chart, single-point series hidden, a 3-month inbound average and an average-offered-range chart against the current package.

### Ported from the private instance (2026-09-18)
- **Experience distill is fenced as untrusted data** (`server/experience.py`): the question is user free-text and the answer is model output re-ingested by the loop, so `_build_prompt()` now wraps both in `_UNTRUSTED_DELIM` with an untrusted-data frame and strips injected copies of the delimiter — a poisoned Q&A can no longer spoof a turn or steer the stored lesson. Retrieval of the lesson was already fenced; this closes the *ingest* side. Covered by an audit probe in `_check_ai_tools()` and a regression test.
- **FIRE stops promising a loan payoff that already happened** (`server/planner_fire.py`): the projection read the loan's monthly cost, which drops to zero the moment it is paid off, so it could not tell "paid off" from "no data" — it kept announcing a future freeing date and delayed the down-payment accumulation by five months. It now reads the loan **balance** (`loan_open`); once the loan is closed the freed installment is assumed to sit in the baseline surplus (counting it twice is the bug on the other side), accumulation starts immediately and both notes say so.

### UX phase 2 (2026-09-05)
- Light theme: 🌗 toggle in the nav (choice kept in `localStorage`, `?theme=light` for screenshots); chart colours follow the theme.
- Collapsible explanations (`help()`): long "how to read this" notes fold under a one-line summary.
- Inline editing of amounts in Wealth and Fixed expenses (Enter saves, Esc cancels) — no more `prompt()` dialogs.
- Dashboard opens with the four numbers and "3 decisions for today"; the rest folds below.
- Loading skeleton, a 2 px busy bar for in-flight requests, and an error card with "Try again".


### Added (2026-09-05 — efficiency pass: data layers, calibration, RAG, leader's log)
- **Ratios tab** (`/api/metrics`, `server/metrics.py`): eleven personal-finance ratios (savings rate, essential share, cushion months, debt service / income, liquid / debt, investment share, employer concentration, real estate share, FX exposure, effective cost of debt, net worth m/m) with traffic lights vs explicit targets, stored as a **monthly series** (`metrics_monthly`) and a **weekly wealth point** (`wealth_points`, new `wealth_points` scheduler task; older monthly snapshots are merged into the chart). "Recompute derived" also stores a point.
- **Net-worth trajectory cone** (`/api/trajectory`): 24-month p10/p50/p90 from a block bootstrap of the benchmark's demeaned monthly returns on the invested part plus deterministic surplus, vest cash and bonus; scenario controls (horizon, bonus on/off, employer stock ±30%, USD ±10%, real terms) repaint in place; the last run is stored in the engine's `scenarios` table.
- **Forecast calibration per ticker × horizon** (`/api/forecast/calibration`): interval scores (coverage, miss direction, Winkler) instead of a single hit rate; a rolling window of the last 120 own settlements **per horizon** for the conformal quantiles; a VIX volatility-regime multiplier (`market.vol_regime`) widens the 21/63-day bands; new forecasts carry a `calibrated` flag so self-calibrated bands can be scored separately. Direction accuracy is no longer used to grade RSU forecasts.
- **RAG over markdown notes**: `rag_dirs` (setting or `config.RAG_DIRS`) are chunked by heading with a file-date prefix; answers return `sources` (source · ref · date) as citations; a small freshness bonus; `/api/rag/status` reports chunks by source.
- **Leader's evidence log** (Career tab, `/api/em`): dated entries (impact / visibility / scope / feedback / learning) with an optional metric and proof link, the week in four numbers (energy, deep-work hours, 1:1s, decisions) and a checklist state for a `plan_90d` list from the career analysis.
- **Recommendation outcomes** (`PUT /api/recommendation/outcome`, `GET /api/recommendation/review`): done / rejected / obsolete per recommendation, a monthly review table with the execution rate, and a reminder when resolved recommendations lack an outcome for a week.

### Added (2026-09-05 — modelling and finance pass)
- **Vest schedule from the grant list** (`market.vest_schedule`): legacy grants expire on `legacy_until`, the yearly and extra grants start on `first_vest` with their own pricing windows, cash-vest included; one source for the RSU view, cash-flow, goals, FIRE and the Monte Carlo windows. The broker's `shares_next_vest` still wins for the next vest until `new_grants_vesting` is set.
- **RSU sales log + capital gains reserve**: `GET/POST/DELETE /api/rsu/sales`; the year's sales feed a tax row and a calendar entry in Taxes (19% of the full sale amount, due next April) and are deducted from net worth as `tax_reserve` until paid.
- **Net cash-flow**: vests × (1 − tax) + cash-vest × payslip net factor + bonus; the tax reserve accumulates separately; `cf_sweep_target` (loan name / `debt` / `none`) is honoured and the liquid start defaults to cash from Wealth. One savings pace: `cf_monthly_surplus` ⇄ `monthly_savings`.
- **Recommendation memory** (`rec_log`): each recommendation carries a "since" date, resolved ones are listed; loan-vs-market is compared **after** capital gains tax; one `essential_monthly()` definition; the cushion = cash + 80% of brokerage, retirement accounts shown separately; a debt strategy note shows how much changed since it was written.
- **Bootstrap Monte Carlo**: RSU projection, its backtest and the daily forecast journal all use a block bootstrap of real (demeaned) returns instead of GBM with a fixed drift.
- **FIRE**: inflation-indexed target, contribution growth, an after-tax series and crossover, and a p10/p50/p90 cone bootstrapped from a benchmark's real monthly returns (`fire_benchmark_ticker`, default `IWDA.AS`). Goal simulations index the target by inflation.
- **Fixed expenses in any currency** (`fx_to_base`): amounts are stored in the item's currency and converted at the cached rate on every read; a `billing` (monthly/yearly) field with a table toggle and a data-driven annual-plan hint; a health/sport subscription category.
- **Scheduled task failures are visible**: a failed runner records `sched_err.<id>` (Data → Schedules, Control Center health, and the barometer card when the last full month is missing); success clears it. New monthly `rates_refresh` task (NBP reference rate from the official XML; WIBOR manual or estimated) for PLN-based instances.
- **Stale-code and stale-analysis signals**: `/api/health` reports `code_stale` when `server/*.py` changed after the process started (the UI shows a restart banner); analysis snapshots with `as_of` get a `stale` marker once the underlying data changed later.
- **Loan history event kinds** (`installment` / `overpayment` / `correction` / `start`) with markers on the balance chart instead of sawtooth lines.

### Changed (2026-09-05 — planner split)
- `server/planner.py` (3.6k lines) is now a thin facade over thirteen `server/planner_*.py` modules (core, wealth, expenses, goals, career, debts, recs, business, cashflow, allocation, freshness, ops, fire). Every public name is still importable from `planner`; function bodies were moved 1:1 by an AST-driven script, and cross-module calls go through a lazy proxy (`planner_proxy.P`) so there are no import cycles and `monkeypatch.setattr(planner, …)` keeps working for cross-module calls. Verified with the full suite plus a before/after snapshot of all 45 GET routes on a seeded database (identical after UUID/timestamp normalisation). To patch a call made *inside* one module, patch that module (e.g. `planner_ops`).

### Changed (2026-09-05)
- Lighter visual layer: grouped sidebar navigation on wide screens, hairlines instead of borders, semantic color tokens, global Chart.js defaults; "Change amount" instead of "Set for <month>" in Fixed Expenses. `run.sh` prefers `./.venv/bin/python`.

### Security (2026-09-05)
- Yahoo history fetch URL is host-pinned with an allow-listed ticker and a closed range set (`_yf_chart_url`), covered by a convergence check and six tests. The personal-data audit gained family/foundation/vendor/host markers plus two repo-scan tests; the recommendation key uses SHA-256 (bandit B324).

### Security
- **Mass-assignment guard**: the generic `PUT /api/settings` writer now drops security-sensitive keys (`commit_repos`, `commit_author`, `ai_mode`, `backup_dir`, `app_config`, …) — they're only settable via their own dedicated endpoints, so a same-origin write can't repoint the commit tracker or flip the AI to cloud through one open key/value setter. Escaped user free-text in the offers view and external (n8n collector) fields in the barometer. `security_review` pentests the settings denylist. (Second red-team pass.)
- **Loopback/CSRF guard**: a `before_request` check rejects any non-loopback `Host` (DNS rebinding) and blocks cross-origin state-changing requests (CSRF) — the API has no auth by design, so this closes the two browser-reachable attack paths. Added a strict **Content-Security-Policy** (`script-src 'self'`), `X-Frame-Options: DENY`, `nosniff` and `no-referrer`; external (Supabase) market text is HTML-escaped before it hits the DOM; the system prompt now treats retrieved context / DB rows as data, not instructions (indirect prompt-injection). `security_review` actively pentests the guard (forged `Host` + cross-origin write must 403), and [SECURITY.md](SECURITY.md) documents the threat model. Prompted by a red-team self-review.

### Added
- **Two-stream market barometer with built-in collectors**: the barometer now tracks two series per role — **📈 demand** (Google Trends search interest: keyless, already an index, with real monthly history; collected by the new app-side `barometer_collect` schedule, plus a one-off `backfill()` from 2026-01) and **🎯 openings** (real posting counts from JSearch/Google for Jobs via the `barometer_openings` schedule; needs `RAPIDAPI_JSEARCH_KEY`, fixed 3-page depth so the index stays comparable). `market_barometer` gains a `stream` column, `list_barometer()` returns a shared month axis and per-role×stream series (`"role|stream"` keys), and the Career view draws demand as solid and openings as dashed lines over the inbound bars, with a per-series direction legend. External n8n collectors keep working via `POST /api/market-barometer` (default stream `trends`).
- **Semantic RAG, documented end-to-end**: README now ships a concrete recommended embedding setup (Qwen3-Embedding-0.6B via `llama-server --embeddings`) with two hard-won operational notes — raise `--ubatch-size` (dense non-English tokenization can crash the server mid-reindex at the default 512) and run the embedding server persistently (the self-maintaining reindex embeds new data only while it's up; otherwise the index quietly degrades to lexical BM25). The degrade-and-recover contract is now guarded by a regression test (`test_rag_reindex_embeds_new_data_and_degrades_without_server`).
- **Market barometer, reworked**: configurable roles + geography (edited in the Career tab, stored as `barometer_config`, defaults from `career_role_a/b`), demand shown as an **index (base 100) + 3-month trend + a direction reading** instead of a falsely-precise absolute count, with raw counts and source in the tooltip. Two n8n collectors (`integrations/n8n/barometer-{jsearch,apify}-collector.json`) feed it monthly from popular job boards (Google for Jobs aggregate / Apify LinkedIn-Indeed) via `POST /api/market-barometer`; the schema generalized to per-role counts + methodology (`sources`/`geo`/`as_of`), back-compatible with old points.
- **Experience distillation** (`server/experience.py`): a good answer can be distilled — one click, **💡 Learn from this** in the prompt log — into a transferable lesson stored in `agent_experiences`, indexed into RAG and injected as guidance on similar future questions. Self-evolution without retraining (*AI Agents in Depth*, ch. 8); human-gated, prunable (**🧠 Learned experiences** panel), fully local. `/api/experience`, `/api/experiences`.
- **Live demo on GitHub Pages**: the real UI with the fake "Alex Demo" persona, fully clickable and read-only — `demo/build_demo.py` seeds a throwaway DB, snapshots every GET endpoint to JSON and assembles `dist/`; api.js serves those snapshots when `KIST_STATIC_DEMO` is set (writes become a friendly toast). Deployed by `.github/workflows/demo-pages.yml` on the canonical repo (push + weekly).
- **Mobile navigation**: the top nav collapses into a hamburger below 860px.
- **RSU respects the base currency**: values convert via `USD<base>=X` (or stay in USD when the base is USD) instead of always going through USD/PLN; the FX labels adapt.

- **Allocation**: the pre-filled targets are now labelled as a **📐 Model** (textbook reference) in their own column, with an intro that explains the initial drift is measured against that model until you set your own targets.
- **LLM contract tests** (`tests/test_llm_contract.py`): a new test kind that mocks the model and asserts harness invariants — graceful offline degradation, the pipeline always logs and returns a `best`, local mode never calls the cloud, a failed brief keeps the saved one. Plus coverage for the wizard's module→view gating, the RSU base-currency rate and price rounding, and a guard that shared global JS helpers used by views (`esc`/`fmt`/`api`/…) are actually defined in `api.js`/`app.js`.

### Changed
- **Commit tracker** no longer auto-scans your home folder for git repos (a fresh clone would show unrelated repos' commits, from every author). It stays empty until you connect `gh` or set `commit_repos`; the view and health check show setup steps instead.

### Fixed
- `market.fetch_yahoo_history` crashed with a NameError (`eb` undefined) — every `/api/market/deepen` call silently failed; now writes through `db.get_conn()`.
- Dashboard: the KPI grid (net worth / income / costs / surplus) was flush against the business card above — added the missing top margin.

## [2026-07-19]

### Added
- **AI SQL-tool pentest**: the security review now actively attacks the local model's SQL tool — injection/DDL/stacked-query payloads must all be refused, the tool connection is proven read-only at the SQLite layer, and a guard-efficacy test fails loudly if the guard is ever weakened (`_check_ai_tools` + Hypothesis fuzz in `tests/test_quality.py`).
- **On-demand history backfill**: `/api/market/deepen/<ticker>` pulls a watchlist symbol's full history straight from Yahoo (keyless, no setup) so the chart and indicators have depth even where the nightly sync is thin.
- **Watchlist human names**: non-obvious tickers (VIX, futures, FX pairs, ETF listings) show a readable name + full tooltip, with generic suffix decoding for unknown ones.
- **Local AI checks real numbers**: a read-only SQL SELECT tool for the local model (`server/db_tools.py` + an OpenAI-compatible tool-calling loop) — answers query the actual database instead of guessing from RAG snippets.
- **RAG upgrades**: optional reranker stage (`LOCAL_RERANK_URL`), and the index now **refreshes itself** (data writes mark it stale; it reindexes before the next answer).
- **Daily & weekly market brief** generated by the AI-mode engine from cached quotes (+ 🔄 Fetch latest button); cadence editable in Schedules.
- **Risk-radar Telegram alert** when the composite goes hot: built-in (env `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`) or standalone n8n workflow (`integrations/n8n/risk-radar-telegram-alert.json`).
- **Analytics**: stress-test "fire drill" card (equities −25%, rates +2pp, income stops), Guyton-Klinger withdrawal guardrails, 5/25 rebalancing rule with UI-editable allocation targets.
- **Setup wizard**: third data option "Set it up with an AI assistant" (copyable onboarding prompt + privacy warning); one-click **Wipe all data** in Control Center.
- Qwen3 8B recommended local model (per-task thinking toggle) + llama-server ngram speculative decoding flags.
- **Optional local AI** (`server/llm_local.py`): private, offline llama.cpp client (OpenAI-compatible) for transaction categorization and forecast-miss narration — data never leaves the machine; `/api/llm/{status,chat}`, Control Center status task, and a security-review probe that flags an unprotected local model. English README section explains use cases.
- **Research-grounded forecasting engine** (`server/forecast_models.py`, stdlib-only): short-horizon **range forecasts** (EWMA λ=0.94 volatility + empirical N-day quantiles — direction of single stocks/FX is not predictable, so the app forecasts ranges, not direction) and long-horizon scenario-band framing (i.i.d. Monte-Carlo GBM rejected for 1–15y per Kitces/Pfau; labeled scenario bands kept as primary).
- **Self-learning forecast journal** (`forecast_track`): daily band forecasts for the whole watchlist are recorded, auto-scored when they mature, and bands become **conformally calibrated on the model's own realized errors** (≥40 scored forecasts per ticker+horizon). Walk-forward backfill seeds the journal. Self-score (band coverage vs 80% target) surfaces in Control Center.
- Short-horizon range panel in RSU, 1M/3M ranges on FX cards, goal ETA shown as a **range** (pace ±25%) instead of a single date; `/api/forecast/bands/<ticker>`, `/api/forecast/selfscore`, `/api/forecast/cycle`.
- **🌍 Risk Radar** (Markets): VIX + gold + WTI oil + USD with explicit 0–2 thresholds → one composite reading (calm/elevated/hot), a month of backfilled history with a 7-day trend line, keyless Yahoo fallback fetch when the nightly sync hasn't run yet, optional local-AI one-liner, and a daily schedule task.
- **AI second opinion on Recommendations**: the rule engine's list is reviewed by the AI (local, or local+cloud with a synthesized verdict) against your own data; result stored with timestamp.
- **Shared AI pipeline** (`_ai_answer`): RAG grounding → local model → (both-mode: cloud + verdict synthesis) → prompt log; governs every AI feature via the Control Center mode. Cloud model defaults to `claude-fable-5` (with limits sized for its always-on thinking).
- **User-configurable schedules** (Data tab): frequency/day/hour for backup snapshots, wealth snapshots, the forecast self-learning cycle and RAG reindex; tasks fire at the first app-open past their moment.
- **Backups**: consistent snapshots into a cloud-synced folder (Google Drive "My Drive"/localized dirs detected correctly), optional Fernet encryption, restore with a pre-restore safety copy, auto-backup master switch.
- **Semantic RAG upgrade**: BM25 + optional embedding hybrid, light PL/EN stemming (inflection no longer blocks matches), richer index (debts, current wealth values, a profile summary, business totals) and a bigger context window.
- Freshness stamp under every view title; human-friendly copy for the AI mode and the AI's "private memory" (RAG).

### Changed
- App renamed to **Kist**; data stored **outside the repo** by default; UI English-native with a Polish toggle; repo made public with CONTRIBUTING, issue/PR templates, coverage floor + bandit in CI, CodeQL (default setup) and Dependabot.
- Personal-data audit hardened: portable regexes (macOS/Linux), new markers (email, home paths, private repo name, employer ticker) — and the audit immediately caught and removed leftover personal defaults.

### Fixed
- Wizard config API 500 on a list-of-modules payload; scanner false positive on JavaScript's `RegExp.exec()`; a tracked `.coverage` artifact removed from the repo and ignored.

## [2026-07-18]

### Added
- **First-run setup wizard** (`#wizard`): pick modules, load sample data or start empty, learn about optional integrations. Re-runnable anytime.
- **Modular architecture**: optional modules (Loans, Taxes, Markets & FX, Equity/RSU, Side business, Career tracker, Property analysis) can be toggled; disabled modules disappear from navigation, routes and the dashboard.
- **Security & functional test suite** (`server/security_review.py`): secret/leak scan of the working tree *and full git history*, static code checks (eval/exec, shell, SQL injection, debug, bind), maintainer personal-data audit, config hygiene, endpoint smoke tests. Run from Control Center, CLI (`python -m security_review --ci`) or CI (`.github/workflows/security.yml` — every push/PR + weekly).
- **Data inventory tab** (Control → Data in the app): every data source with mode (auto / derived / offline-authored / manual), freshness and a monthly-effort estimate, plus an automation roadmap.
- **Market brief section** on the Market tab (regime, highlights, geopolitical context, per-position stances) served from an offline-authored snapshot.
- **n8n → Telegram data-freshness alert** workflow (importable, `integrations/n8n/`).
- **PL/EN language toggle** (Control Center or `?lang=en`).
- Demo mode hardening: chart axis/label masking, share-count masking, currency-symbol amounts.

### Changed
- "Add loan" form collapsed to the bottom of the Loans tab (rare action).
- SQL update statements now go through a validated identifier builder (`update_sql`) — injection-proof by construction.

### Fixed
- `run.sh` pointed the data directory outside the repo on fresh clones.
- Chart demo-masking crashed on Chart.js v4 (options resolver recursion).

### Removed
- Transactions tab (UI). The table and API remain for future bank-import automation.

## [2026-07-17]

### Added
- Initial public release: extracted from a personal repo as a standalone, generic, MIT-licensed app. Self-contained SQLite layer, seed script with a fake persona, demo mode, FIRE forecasts, FX signal engine with backtest, RSU Monte-Carlo, cash-flow projection, debts, taxes, goals, Control Center.
