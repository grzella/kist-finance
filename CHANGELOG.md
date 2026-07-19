# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are dates (no semver yet — pre-1.0).

## [Unreleased]

### Added
- **Optional local AI** (`server/llm_local.py`): private, offline llama.cpp client (OpenAI-compatible) for transaction categorization and forecast-miss narration — data never leaves the machine; `/api/llm/{status,chat}`, Control Center status task, and a security-review probe that flags an unprotected local model. English README section explains use cases.
- **Research-grounded forecasting engine** (`server/forecast_models.py`, stdlib-only): short-horizon **range forecasts** (EWMA λ=0.94 volatility + empirical N-day quantiles — direction of single stocks/FX is not predictable, so the app forecasts ranges, not direction) and long-horizon scenario-band framing (i.i.d. Monte-Carlo GBM rejected for 1–15y per Kitces/Pfau; labeled scenario bands kept as primary).
- **Self-learning forecast journal** (`forecast_track`): daily band forecasts for the whole watchlist are recorded, auto-scored when they mature, and bands become **conformally calibrated on the model's own realized errors** (≥40 scored forecasts per ticker+horizon). Walk-forward backfill seeds the journal. Self-score (band coverage vs 80% target) surfaces in Control Center.
- Short-horizon range panel in RSU, 1M/3M ranges on FX cards, goal ETA shown as a **range** (pace ±25%) instead of a single date; `/api/forecast/bands/<ticker>`, `/api/forecast/selfscore`, `/api/forecast/cycle`.

## [2026-07-19]

### Added
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
