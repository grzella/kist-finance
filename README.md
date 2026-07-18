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
- **AI assistant** — the app itself calls no LLM at runtime. Some snapshot content (market brief, analyses) is authored offline; wire your own AI (Claude/OpenAI/local llama.cpp) around the JSON API if you want.
- **Commit tracker** — set `commit_repos` / `commit_author` in settings or `COMMIT_REPOS` / `COMMIT_AUTHOR` env vars.

## Data & privacy

- `.finance/`, `.env`, and `backups/` are git-ignored — **never commit them**.
- `seed.py` refuses to overwrite existing data (use `--force` only on a throwaway DB).
- **Demo mode** (Control Center or `?demo`) masks all figures with a `0-1` pattern and hides chart axis values — safe screenshots.
- **Language**: UI is Polish-first with an English toggle (Control Center or `?lang=en`); i18n contributions welcome.

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
