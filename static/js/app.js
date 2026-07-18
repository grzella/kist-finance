const views = {
  wizard: renderWizard,
  dashboard: renderDashboard,
  cashflow: renderCashflow,
  control: renderControl,
  allocation: renderAllocation,
  taxes: renderTaxes,
  currency: renderCurrency,
  reminders: renderReminders,
  data: renderData,
  recs: renderRecs,
  wealth: renderWealth,
  goals: renderGoals,
  italy: renderItaly,
  career: renderCareer,
  commits: renderCommits,
  offers: renderOffers,
  debts: renderDebts,
  firma: renderFirma,
  market: renderMarket,
  forecasts: renderForecasts,
  rsu: renderRsu,
};

let activeCharts = [];
function destroyCharts() {
  activeCharts.forEach((c) => c.destroy());
  activeCharts = [];
}
function trackChart(c) {
  activeCharts.push(c);
  // TRYB DEMO: maskuj osie wartości (nie kategorie/daty) i wyłącz tooltipy
  try {
    if (typeof demoOn === "function" && demoOn() && c && c.config) {
      // Mutate the RAW c.config.options — writing to the c.options resolver
      // proxy recurses infinitely in Chart.js v4. c.update() then rebuilds
      // the chart from the masked options.
      const opts = c.config.options = c.config.options || {};
      opts.plugins = opts.plugins || {};
      opts.plugins.tooltip = { enabled: false };
      if (c.data && c.data.datasets) {
        c.data.datasets.forEach((ds) => {
          if (typeof ds.label === "string") _DEMO_WORDS.forEach(([re, rep]) => { ds.label = ds.label.replace(re, rep); });
        });
      }
      if (c.data && Array.isArray(c.data.labels)) {
        c.data.labels = c.data.labels.map((l) =>
          typeof l === "string" ? _DEMO_WORDS.reduce((s, [re, rep]) => s.replace(re, rep), l) : l);
      }
      // Mask value axes using the ACTUAL runtime scales (works even when the
      // chart declares no options.scales — Chart.js creates them itself),
      // writing the tick callback into the raw config per scale id.
      opts.scales = opts.scales || {};
      Object.keys(c.scales || {}).forEach((k) => {
        const scale = c.scales[k];
        if (scale && scale.axis !== "x") {
          opts.scales[k] = opts.scales[k] || {};
          opts.scales[k].ticks = opts.scales[k].ticks || {};
          opts.scales[k].ticks.callback = () => "▪";
        }
      });
      c.update();
    }
  } catch (e) { console.error("demo chart", e); }
  return c;
}

// TRYB DEMO: maskuj wrażliwe słowa (lokalizacje, nazwisko) w wyrenderowanym DOM
const _DEMO_WORDS = [
  // Add your own sensitive words to mask in demo mode, e.g. [/CityName/g, "City-A"]
];
function _mask01(digits) {
  let s = "";
  for (let i = 0; i < Math.max(1, digits.length); i++) s += (i % 2 === 0 ? "0" : "1");
  return s.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}
function maskSensitiveText(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach((n) => {
    let t = n.nodeValue;
    _DEMO_WORDS.forEach(([re, rep]) => { t = t.replace(re, rep); });
    // maskuj liczby finansowe w wolnym tekście (liczba + jednostka), oszczędzając daty/liczniki
    t = t.replace(/(\d[\d   .,]*\d|\d)[   ]?(zł|zl|PLN|EUR|USD|\$|€|k|tys\.?|mln|mld|%|szt\.?)(?=$|\b|\/|\s|,|\.|\))/g,
      (m, num, unit) => _mask01(num.replace(/[^\d]/g, "")) + (/^[a-zA-Zł]/.test(unit) ? " " + unit : unit));
    // mask amounts with the currency symbol BEFORE the number (e.g. $93.29, €120)
    t = t.replace(/([$€])[   ]?(\d[\d   .,]*\d|\d)/g,
      (m, sym, num) => sym + _mask01(num.replace(/[^\d]/g, "")));
    if (t !== n.nodeValue) n.nodeValue = t;
  });
}

// ---------- i18n: warstwa tłumaczenia DOM (PL→EN) ----------
const _I18N_EXACT = {
  "💰 Budżet": "💰 Budget", "💧 Płynność": "💧 Cash-flow", "💡 Rekomendacje": "💡 Recommendations",
  "🏦 Majątek": "🏦 Wealth", "🧩 Alokacja": "🧩 Allocation", "🎯 Cele": "🎯 Goals",
  "💼 Kariera": "💼 Career", "🏠 Kredyty": "🏠 Loans", "🏛️ Podatki": "🏛️ Taxes",
  "🚁 Firma": "🚁 Business", "📈 Rynek": "📈 Market", "💱 Waluty": "💱 FX",
  "🔮 Prognozy": "🔮 Forecasts", "🛠️ Control": "🛠️ Control",
  "🛠️ Control Center": "🛠️ Control Center", "🛠️ Automatyzacje & health": "🛠️ Automation & health",
  "🔔 Przypomnienia": "🔔 Reminders", "📊 Dane w aplikacji": "📊 Data in the app",
  "Zadania OK": "Tasks OK", "Ostrzeżenia": "Warnings", "Błędy": "Errors", "Odśwież": "Refresh",
  "Sprawdź teraz": "Check now", "🔬 Tryb demo": "🔬 Demo mode",
  "Włącz tryb demo": "Enable demo mode", "Wyłącz tryb demo": "Disable demo mode",
  "🔐 Bezpieczeństwo & testy": "🔐 Security & tests",
  "🔐 Uruchom security & testy": "🔐 Run security & tests",
  "Zadanie": "Task", "Częstotliwość": "Frequency", "Ostatni update": "Last update",
  "Status": "Status", "Szczegóły": "Details",
  "Źródła bez pracy": "Zero-effort sources", "Utrzymuje Claude": "Maintained offline",
  "Ręczne punkty / mies.": "Manual points / mo.", "Czas ręczny / mies.": "Manual time / mo.",
  "Dane": "Data", "Tryb": "Mode", "Źródło": "Source", "Ostatnia akt.": "Last upd.",
  "Wartość netto": "Net worth", "Dochody / mies.": "Income / mo.", "Koszty / mies.": "Costs / mo.",
  "Nadwyżka / mies.": "Surplus / mo.", "Posiadane akcje": "Shares held",
  "Dodaj": "Add", "Zapisz": "Save", "Usuń": "Delete", "Filtruj": "Filter", "Nadpłać": "Overpay",
  "wszystkie kategorie": "all categories", "Ładowanie…": "Loading…",
};
const _I18N_PHRASES = [
  [/\bmiesięcznie\b/g, "monthly"], [/\bcodziennie\b/g, "daily"], [/\btygodniowo\b/g, "weekly"],
  [/\bokazjonalnie\b/g, "occasionally"], [/\bna żądanie\b/g, "on demand"], [/\brzadko\b/g, "rarely"],
  [/\bręcznie\b/g, "manual"], [/\bliczone\b/g, "derived"], [/\bzero pracy\b/g, "zero effort"],
  [/ostatni run:/g, "last run:"], [/stan na/g, "as of"],
];
function translateDom(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach((n) => {
    const raw = n.nodeValue;
    const key = raw.trim();
    if (!key) return;
    let out = raw;
    if (_I18N_EXACT[key]) {
      out = raw.replace(key, _I18N_EXACT[key]);
    } else {
      _I18N_PHRASES.forEach(([re, rep]) => { out = out.replace(re, rep); });
    }
    if (out !== raw) n.nodeValue = out;
  });
}
function applyLang() {
  if (langGet() !== "en") return;
  document.documentElement.lang = "en";
  try { translateDom(document.getElementById("nav")); } catch (e) { /* noop */ }
}

let _appCfg = null;
async function appCfg() {
  if (!_appCfg) {
    _appCfg = await api.get("/api/app-config")
      .catch(() => ({ wizard_completed: true, enabled_views: null }));
  }
  return _appCfg;
}
function applyModules(cfg) {
  if (!cfg.enabled_views) return;
  document.querySelectorAll("#nav a").forEach((a) => {
    a.style.display = cfg.enabled_views.includes(a.dataset.view) ? "" : "none";
  });
}

async function route() {
  let name = (location.hash || "#dashboard").slice(1);
  const cfg = await appCfg();
  applyModules(cfg);
  if (!cfg.wizard_completed && name !== "wizard") {
    location.hash = "#wizard";
    return;
  }
  if (cfg.enabled_views && !cfg.enabled_views.includes(name)) name = "dashboard";
  const fn = views[name] || views.dashboard;
  document.querySelectorAll("#nav a").forEach((a) =>
    a.classList.toggle("active", a.dataset.view === name));
  destroyCharts();
  const banner = document.getElementById("demoBanner");
  if (banner) banner.style.display = demoOn() ? "block" : "none";
  const el = document.getElementById("view");
  el.innerHTML = '<div class="empty">Ładowanie…</div>';
  try {
    await fn(el);
    if (demoOn()) { try { maskSensitiveText(el); } catch (e) { console.error("mask", e); } }
    if (langGet() === "en") { try { translateDom(el); } catch (e) { console.error("i18n", e); } }
  } catch (e) {
    el.innerHTML = `<div class="card"><b>Błąd:</b> <span class="muted">${e.message}</span></div>`;
  }
}

applyLang();

window.addEventListener("hashchange", route);
route();
