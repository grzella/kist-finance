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
  property: renderProperty,
  career: renderCareer,
  commits: renderCommits,
  offers: renderOffers,
  debts: renderDebts,
  business: renderBusiness,
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
  // DEMO MODE: mask value axes (not categories/dates) and disable tooltips
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

// DEMO MODE: mask sensitive words (locations, surname) in the rendered DOM
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
    // mask financial figures in free text (number + unit), sparing dates/counters
    t = t.replace(/(\d[\d   .,]*\d|\d)[   ]?(zł|zl|PLN|EUR|USD|\$|€|k|tys\.?|mln|mld|%|szt\.?)(?=$|\b|\/|\s|,|\.|\))/g,
      (m, num, unit) => _mask01(num.replace(/[^\d]/g, "")) + (/^[a-zA-Zł]/.test(unit) ? " " + unit : unit));
    // mask amounts with the currency symbol BEFORE the number (e.g. $93.29, €120)
    t = t.replace(/([$€])[   ]?(\d[\d   .,]*\d|\d)/g,
      (m, sym, num) => sym + _mask01(num.replace(/[^\d]/g, "")));
    if (t !== n.nodeValue) n.nodeValue = t;
  });
}

// ---------- i18n: DOM translation layer (EN→PL, for the optional "pl" mode) ----------
const _I18N_EXACT = {
  "💰 Budget": "💰 Budżet", "💧 Cash-flow": "💧 Płynność", "💡 Recommendations": "💡 Rekomendacje",
  "🏦 Wealth": "🏦 Majątek", "🧩 Allocation": "🧩 Alokacja", "🎯 Goals": "🎯 Cele",
  "💼 Career": "💼 Kariera", "🏠 Loans": "🏠 Kredyty", "🏛️ Taxes": "🏛️ Podatki",
  "🚁 Business": "🚁 Firma", "📈 Market": "📈 Rynek", "💱 FX": "💱 Waluty",
  "🔮 Forecasts": "🔮 Prognozy", "🛠️ Control": "🛠️ Control",
  "🛠️ Control Center": "🛠️ Control Center", "🛠️ Automation & health": "🛠️ Automatyzacje & health",
  "🔔 Reminders": "🔔 Przypomnienia", "📊 Data in the app": "📊 Dane w aplikacji",
  "Tasks OK": "Zadania OK", "Warnings": "Ostrzeżenia", "Errors": "Błędy", "Refresh": "Odśwież",
  "Check now": "Sprawdź teraz", "🔬 Demo mode": "🔬 Tryb demo",
  "Enable demo mode": "Włącz tryb demo", "Disable demo mode": "Wyłącz tryb demo",
  "🔐 Security & tests": "🔐 Bezpieczeństwo & testy",
  "🔐 Run security & tests": "🔐 Uruchom security & testy",
  "Task": "Zadanie", "Frequency": "Częstotliwość", "Last update": "Ostatni update",
  "Status": "Status", "Details": "Szczegóły",
  "Zero-effort sources": "Źródła bez pracy", "Maintained by Claude": "Utrzymuje Claude",
  "Manual touchpoints / mo": "Ręczne punkty / mies.", "Manual time / mo": "Czas ręczny / mies.",
  "Data": "Dane", "Mode": "Tryb", "Source": "Źródło", "Last upd.": "Ostatnia akt.",
  "Net worth": "Wartość netto", "Income / mo": "Dochody / mies.", "Costs / mo": "Koszty / mies.",
  "Surplus / mo": "Nadwyżka / mies.", "Shares held": "Posiadane akcje",
  "Add": "Dodaj", "Save": "Zapisz", "Delete": "Usuń", "Filter": "Filtruj", "Overpay": "Nadpłać",
  "all categories": "wszystkie kategorie", "Loading…": "Ładowanie…",
};
const _I18N_PHRASES = [
  [/\bmonthly\b/g, "miesięcznie"], [/\bdaily\b/g, "codziennie"], [/\bweekly\b/g, "tygodniowo"],
  [/\boccasionally\b/g, "okazjonalnie"], [/\bon demand\b/g, "na żądanie"], [/\brarely\b/g, "rzadko"],
  [/\bzero effort\b/g, "zero pracy"],
  [/last run:/g, "ostatni run:"], [/\bas of\b/g, "stan na"],
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
  if (langGet() !== "pl") return;
  document.documentElement.lang = "pl";
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
  el.innerHTML = '<div class="empty">Loading…</div>';
  try {
    await fn(el);
    if (demoOn()) { try { maskSensitiveText(el); } catch (e) { console.error("mask", e); } }
    if (langGet() === "pl") { try { translateDom(el); } catch (e) { console.error("i18n", e); } }
  } catch (e) {
    el.innerHTML = `<div class="card"><b>Error:</b> <span class="muted">${e.message}</span></div>`;
  }
}

applyLang();

window.addEventListener("hashchange", route);
route();
