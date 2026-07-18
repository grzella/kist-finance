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
