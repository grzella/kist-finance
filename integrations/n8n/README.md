# n8n → Telegram: alert świeżości danych

Gotowy workflow n8n, który **codziennie sprawdza, czy pipeline danych żyje**, i
wysyła powiadomienie na Telegram, gdy coś się zepsuje — bez zaglądania do
aplikacji. Monitoruje warstwę chmurową (Supabase), więc działa **niezależnie od
tego, czy lokalna apka jest włączona**.

Plik: [`data-freshness-telegram-alert.json`](./data-freshness-telegram-alert.json)

## Co sprawdza (i czego nie)

- ✅ **Świeżość kursów/FX** — czy tabela `market_prices` w Supabase dostała
  świeże notowania (domyślnie alert, gdy ostatni wpis > 2 dni temu albo tabela
  pusta). To łapie zerwany dzienny sync (n8n → Supabase).
- ➕ Łatwo dołożyć kolejne źródła (np. raporty ads `analysis_reports`) — patrz
  „Rozszerzanie” niżej.
- ❌ **Nie** monitoruje rzeczy lokalnych (backup, security scan) — te pilnują
  launchd/CI, bo nie są widoczne z chmury.

Przepływ: `Schedule (codziennie 23:15)` → `HTTP: Supabase (ostatnia data)` →
`Code: ocena świeżości` → `IF: jest problem?` → `Telegram: wyślij alert`.
Domyślnie powiadomienie idzie **tylko przy problemie** (cisza = wszystko OK).

## Wymagania

- Działający **n8n** (self-hosted lub Cloud).
- **Supabase** — ten sam projekt, z którego korzysta aplikacja (tabela
  `market_prices`). Do odczytu wystarczy **anon key**.
- **Bot Telegram** (token) i Twoje **chat id**.

## Konfiguracja krok po kroku

### 1. Załóż bota Telegram
1. Napisz do [@BotFather](https://t.me/BotFather) → `/newbot` → nazwij bota.
2. Zapisz **token** (postać `123456789:ABC-...`).
3. Napisz cokolwiek do swojego nowego bota (żeby mógł Ci odpisywać).
4. Pobierz swoje **chat id**: najprościej przez [@userinfobot](https://t.me/userinfobot),
   albo otwórz `https://api.telegram.org/bot<TOKEN>/getUpdates` i odczytaj `chat.id`.

### 2. Dodaj credentiale w n8n
- **Telegram API** → wklej token bota. Nazwij np. `Telegram bot`.
- **Header Auth** (dla Supabase) → *Name:* `apikey`, *Value:* Twój Supabase
  **anon key**. Nazwij np. `Supabase anon key (apikey)`.

### 3. Zaimportuj workflow
n8n → *Workflows* → *Import from File* → wskaż `data-freshness-telegram-alert.json`.

### 4. Uzupełnij placeholdery
- Węzeł **„Supabase: ostatnia data kursów”** → w URL zamień
  `https://YOUR-PROJECT.supabase.co` na host swojego projektu; wybierz credential
  Header Auth z kroku 2.
- Węzeł **„Telegram: wyślij alert”** → *Chat ID* = Twoje chat id; wybierz
  credential Telegram.

### 5. Przetestuj
- W węźle **„Oceń świeżość + zbuduj alert”** zmień `MAX_AGE_DAYS` na `-1`
  (wymusi alert), kliknij **Execute Workflow** → powinieneś dostać wiadomość na
  Telegram. Przywróć `MAX_AGE_DAYS = 2`.

### 6. Włącz
Przełącz workflow na **Active**. Odpala się codziennie o 23:15 (po dziennym
syncu ~22:35). Godzinę zmienisz w węźle Schedule (`15 23 * * *`).

## Rozszerzanie o kolejne źródła

Dołóż drugi węzeł **HTTP Request** (np.
`.../rest/v1/analysis_reports?select=week_end&order=week_end.desc&limit=1`),
podłącz go do węzła Code i dopisz w nim regułę:

```js
// przykład: raporty ads starsze niż 9 dni
const ads = $('Supabase: raporty ads').all().map((i) => i.json);
const adLatest = ads.length ? ads[0].week_end : null;
if (!adLatest || ageDays(adLatest) > 9) {
  problems.push('Raporty ads nieświeże (ostatni: ' + adLatest + ').');
}
```

Ten sam wzorzec działa dla dowolnej tabeli Supabase z kolumną daty.

## Bezpieczeństwo

- Token bota i Supabase key żyją **wyłącznie w credentialach n8n** — w tym pliku
  workflow są tylko placeholdery. Nigdy nie commituj realnych kluczy.
- To repo ma skan bezpieczeństwa (`server/security_review.py`), który wyłapałby
  sekret wklejony do plików — trzymaj klucze w n8n, nie w JSON-ie.
