# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are dates (no semver yet — pre-1.0).

## [Unreleased]

### Added
- **Research-grounded forecasting engine** (`server/forecast_models.py`, stdlib-only): short-horizon **range forecasts** (EWMA λ=0.94 volatility + empirical N-day quantiles — direction of single stocks/FX is not predictable, so the app forecasts ranges, not direction) and long-horizon scenario-band framing (i.i.d. Monte-Carlo GBM rejected for 1–15y per Kitces/Pfau; labeled scenario bands kept as primary).
- **Self-learning forecast journal** (`forecast_track`): daily band forecasts for the whole watchlist are recorded, auto-scored when they mature, and bands become **conformally calibrated on the model's own realized errors** (≥40 scored forecasts per ticker+horizon). Walk-forward backfill seeds the journal. Self-score (band coverage vs 80% target) surfaces in Control Center.
- Short-horizon range panel in RSU, 1M/3M ranges on FX cards, goal ETA shown as a **range** (pace ±25%) instead of a single date; `/api/forecast/bands/<ticker>`, `/api/forecast/selfscore`, `/api/forecast/cycle`.

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
