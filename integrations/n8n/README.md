# n8n → Telegram: data-freshness alert

A ready-made n8n workflow that **checks daily whether the data pipeline is alive**
and sends a Telegram notification when something breaks — without opening the app.
It watches the cloud layer (Supabase), so it works **whether or not the local app
is running**.

File: [`data-freshness-telegram-alert.json`](./data-freshness-telegram-alert.json)

## What it checks (and what it doesn't)

- ✅ **Quote/FX freshness** — whether the `market_prices` table in Supabase got
  fresh quotes (by default it alerts when the latest entry is > 2 days old, or the
  table is empty). This catches a broken daily sync (n8n → Supabase).
- ➕ Easy to add more sources (e.g. ads reports in `analysis_reports`) — see
  "Extending" below.
- ❌ It does **not** watch local things (backups, security scan) — those are
  guarded by launchd/CI, since they aren't visible from the cloud.

Flow: `Schedule (daily 23:15)` → `HTTP: Supabase (latest date)` →
`Code: freshness check` → `IF: any problem?` → `Telegram: send alert`.
By default a notification is sent **only on a problem** (silence = all good).

## Requirements

- A running **n8n** (self-hosted or Cloud).
- **Supabase** — the same project the app uses (the `market_prices` table). An
  **anon key** is enough for reads.
- A **Telegram bot** (token) and your **chat id**.

## Step-by-step setup

### 1. Create a Telegram bot
1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → name the bot.
2. Save the **token** (looks like `123456789:ABC-...`).
3. Send any message to your new bot (so it can reply to you).
4. Get your **chat id**: easiest via [@userinfobot](https://t.me/userinfobot), or
   open `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `chat.id`.

### 2. Add credentials in n8n
- **Telegram API** → paste the bot token. Name it e.g. `Telegram bot`.
- **Header Auth** (for Supabase) → *Name:* `apikey`, *Value:* your Supabase
  **anon key**. Name it e.g. `Supabase anon key (apikey)`.

### 3. Import the workflow
n8n → *Workflows* → *Import from File* → pick `data-freshness-telegram-alert.json`.

### 4. Fill in the placeholders
- The **"Supabase: latest quote date"** node → in the URL replace
  `https://YOUR-PROJECT.supabase.co` with your project host; select the Header
  Auth credential from step 2.
- The **"Telegram: send alert"** node → *Chat ID* = your chat id; select the
  Telegram credential.

### 5. Test
- In the **"Assess freshness + build alert"** node, set `MAX_AGE_DAYS` to `-1`
  (forces an alert), click **Execute Workflow** → you should get a Telegram
  message. Restore `MAX_AGE_DAYS = 2`.

### 6. Enable
Toggle the workflow to **Active**. It runs daily at 23:15 (after the ~22:35 daily
sync). Change the time in the Schedule node (`15 23 * * *`).

## Extending with more sources

Add a second **HTTP Request** node (e.g.
`.../rest/v1/analysis_reports?select=week_end&order=week_end.desc&limit=1`),
wire it into the Code node, and add a rule there:

```js
// example: ads reports older than 9 days
const ads = $('Supabase: ads reports').all().map((i) => i.json);
const adLatest = ads.length ? ads[0].week_end : null;
if (!adLatest || ageDays(adLatest) > 9) {
  problems.push('Ads reports are stale (latest: ' + adLatest + ').');
}
```

The same pattern works for any Supabase table with a date column.

## Security

- The bot token and Supabase key live **only in n8n credentials** — this workflow
  file contains only placeholders. Never commit real keys.
- This repo has a security scan (`server/security_review.py`) that would catch a
  secret pasted into files — keep keys in n8n, not in the JSON.

## risk-radar-telegram-alert.json

A ready-made workflow that pings your Telegram **only when the market risk radar goes
hot** — so a nervous market reaches you without you opening the app.

File: [`risk-radar-telegram-alert.json`](./risk-radar-telegram-alert.json)

**Cloud-driven, laptop-independent.** It reads the same `market_prices` table in
Supabase that the nightly sync keeps fresh, then recomputes the radar composite (VIX,
gold, oil, EURUSD) with the **exact same thresholds** as `server/risk_radar.py` — the
single source of truth. Because it reads the cloud, it fires **whether or not the local
app is running**. Silence means calm/elevated; a message means hot.

Flow: `Schedule (daily 9:20)` → `Code: compute radar from Supabase` →
`IF: hot? (score ≥ 4/8)` → `Telegram: alert`.

### Setup
1. **Telegram bot + chat id** — same as the data-freshness section above.
2. **Environment variables in n8n** (Settings → Variables, or the container env):
   `SUPABASE_URL`, `SUPABASE_ANON_KEY` (anon key is enough — read only), and
   `TELEGRAM_CHAT_ID`.
3. **Import** `risk-radar-telegram-alert.json`, set the **Telegram API** credential on
   the alert node.
4. **Test**: temporarily change `score >= 4` to `score >= 0` in the Code node and
   **Execute Workflow** → you should get a message. Restore `>= 4`.
5. **Enable**. Runs every morning at 9:20; change the time in the Schedule node.

The four radar tickers (`^VIX`, `GC=F`, `CL=F`, `EURUSD=X`) must be in your market
watchlist so the sync stores them in Supabase; otherwise those components read as
"missing" and the score is understated. The app can also surface the same radar in the
Market tab when it's running — this workflow is the always-on cloud counterpart.

## Market barometer collectors (JSearch + Apify)

Two ready-made monthly workflows that feed the **Market barometer** (Career tab) with
how many postings exist for **your roles** on popular job boards — so the tab tracks
real market demand against your inbound, instead of a hand-typed guess.

- [`barometer-jsearch-collector.json`](./barometer-jsearch-collector.json) — counts via
  **JSearch (Google for Jobs)**, which aggregates LinkedIn / Indeed / Glassdoor / … in
  one query. Cheaper, stabler, broad coverage. Needs `RAPIDAPI_JSEARCH_KEY`.
- [`barometer-apify-collector.json`](./barometer-apify-collector.json) — counts via an
  **Apify** job-board scraper actor (LinkedIn/Indeed 1:1; the actor handles anti-bot,
  not you). Closer to "scrape LinkedIn", pricier/slower. Needs `APIFY_TOKEN` + `APIFY_ACTOR`.

Both read the app's **configurable roles + geography** (set them in the Career tab → ⚙️,
stored as `barometer_config`), loop each role, count postings, and `POST` one point to
`/api/market-barometer`. Set `KIST_URL` in n8n if the app isn't at `http://127.0.0.1:8321`
(n8n must be able to reach it — run n8n locally, or expose the app on your LAN).

**It's a relative index, not a true total — on purpose.** None of these sources give a
clean "total openings" number, so each collector uses a **fixed method** (same query,
same page depth / max items) every month. The app turns that proxy into an **index
(base 100)** with a 3-month trend and a direction reading — comparable month-to-month
even though the raw count is a proxy. The raw number + source are shown in the tooltip so
it's never mistaken for a precise total. **Keep the method fixed** (don't change `PAGES` /
`MAX` between months) or the trend breaks.

**Want to compare the two?** Run both for a couple of months and see which gives steadier,
more sensible numbers for your roles/geography — then keep one. The app is source-agnostic;
it just needs points at `/api/market-barometer` with `{month, counts, sources, geo, as_of}`.

The app's `/api/market-barometer` guard blocks cross-origin writes but allows same-origin /
tool requests without an `Origin` header — n8n's HTTP node sends none, so it passes.
