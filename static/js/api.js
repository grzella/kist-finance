// ---------- STATIC DEMO (GitHub Pages) — GETs come from baked JSON snapshots,
// writes are a friendly no-op. Set by demo/build_demo.py; never true in the real app.
function demoStatic() { return !!window.KIST_STATIC_DEMO; }
function demoSnapshotPath(p) {
  return "demo-data/" + p.replace(/^\//, "").replace(/[^A-Za-z0-9._-]/g, "_") + ".json";
}
let _demoToastAt = 0;
function demoToast() {
  if (Date.now() - _demoToastAt < 4000) return;
  _demoToastAt = Date.now();
  let t = document.getElementById("demoToast");
  if (!t) {
    t = document.createElement("div");
    t.id = "demoToast";
    t.style.cssText = "position:fixed;bottom:16px;left:50%;transform:translateX(-50%);" +
      "background:#2c3040;color:#eee;padding:8px 14px;border-radius:8px;z-index:9999;" +
      "font-size:.9em;box-shadow:0 2px 12px rgba(0,0,0,.4)";
    document.body.appendChild(t);
  }
  t.textContent = "🔒 Read-only demo — changes aren't saved. Clone the repo to use it for real.";
  t.style.display = "block";
  clearTimeout(t._hid);
  t._hid = setTimeout(() => { t.style.display = "none"; }, 3500);
}

const api = {
  async get(path) {
    const r = await fetch(demoStatic() ? demoSnapshotPath(path) : path);
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  },
  async send(method, path, body) {
    if (demoStatic()) {
      // compute-only POSTs (e.g. overpayment simulations) have baked responses
      const key = ("post_" + path + "__" + JSON.stringify(body === undefined ? "" : body))
        .replace(/^\//, "").replace(/[^A-Za-z0-9._-]/g, "_") + ".json";
      const r = await fetch("demo-data/" + key).catch(() => null);
      if (r && r.ok) return r.json();
      demoToast();
      return { ok: false, demo: true, error: "Read-only demo — changes aren't saved." };
    }
    const r = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  },
  post(p, b) { return this.send("POST", p, b); },
  put(p, b) { return this.send("PUT", p, b); },
  del(p) { return this.send("DELETE", p); },
};

const fmt = {
  pln: (v) => v == null ? "—" : new Intl.NumberFormat("pl-PL", { style: "currency", currency: "PLN", maximumFractionDigits: 0 }).format(v),
  usd: (v) => v == null ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(v),
  num: (v, d = 2) => v == null ? "—" : Number(v).toLocaleString("pl-PL", { maximumFractionDigits: d }),
  pct: (v, d = 1) => v == null ? "—" : `${Number(v).toFixed(d)}%`,
};

// Grouped money inputs: <input data-num> shows "1 234 567.89", parseNum reads it.
fmt.grouped = (v) => {
  if (v == null || v === "" || isNaN(Number(v))) return "";
  const [int, dec] = Number(v).toFixed(2).replace(/\.00$/, "").split(".");
  const g = int.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return dec ? `${g}.${dec}` : g;
};
function parseNum(elOrStr) {
  const s = typeof elOrStr === "string" ? elOrStr : elOrStr.value;
  const v = parseFloat(String(s).replace(/[\s  ]/g, "").replace(",", "."));
  return isNaN(v) ? NaN : v;
}
document.addEventListener("blur", (e) => {
  const el = e.target;
  if (el.matches && el.matches("input[data-num]")) {
    const v = parseNum(el);
    el.value = isNaN(v) ? "" : fmt.grouped(v);
  }
}, true);

// HTML-escape any value before it goes into innerHTML. Use for free-text and
// especially anything from an external source (e.g. market data synced from
// Supabase) so a crafted string can't inject markup. Numbers/computed values
// don't need it. (The CSP already blocks script execution as a second layer.)
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// ---------- DEMO MODE — masks amounts with a 0-1 pattern (for screenshots) ----------
function demoOn() {
  if (/[?&#](demo|test)\b/.test(location.search + location.hash)) return true;
  return localStorage.getItem("demoMode") === "1";
}
function toggleDemo(on) {
  localStorage.setItem("demoMode", on ? "1" : "0");
  location.reload();
}

// ---------- LANGUAGE (en default, pl via toggle) ----------
function langGet() {
  const q = /[?&#]lang=(pl|en)\b/.exec(location.search + location.hash);
  if (q) return q[1];
  return localStorage.getItem("lang") === "pl" ? "pl" : "en";
}
function langSet(l) {
  localStorage.setItem("lang", l === "pl" ? "pl" : "en");
  location.reload();
}
function _maskInt(v) {
  const d = Math.max(1, String(Math.floor(Math.abs(Number(v) || 0))).length);
  let s = "";
  for (let i = 0; i < d; i++) s += (i % 2 === 0 ? "0" : "1");
  return s.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}
function _maskDec(n) { return n > 0 ? "01".repeat(Math.ceil(n / 2)).slice(0, n) : ""; }
(function wrapDemo() {
  const o = { pln: fmt.pln, usd: fmt.usd, num: fmt.num, pct: fmt.pct, grouped: fmt.grouped, eur: fmt.eur };
  const _CURSYM = { PLN: ["", " zł"], EUR: ["€", ""], USD: ["$", ""], GBP: ["£", ""], CHF: ["", " CHF"] };
  fmt.money = (v) => {
    if (v == null) return "—";
    const [pre, suf] = _CURSYM[window.APP_CURRENCY || "PLN"] || _CURSYM.PLN;
    const body = demoOn() ? _maskInt(v) : fmt.grouped(Math.round(v));
    return pre + body + suf;
  };
  fmt.pln = fmt.money;  // legacy alias — every view formats through the configured currency
  fmt.usd = (v) => v == null ? "—" : (demoOn() ? "$" + _maskInt(v) + "." + _maskDec(2) : o.usd(v));
  fmt.num = (v, d = 2) => v == null ? "—" : (demoOn() ? _maskInt(v) + (d > 0 ? "," + _maskDec(d) : "") : o.num(v, d));
  fmt.pct = (v, d = 1) => v == null ? "—" : (demoOn() ? _maskInt(v) + (d > 0 ? "," + _maskDec(d) : "") + "%" : o.pct(v, d));
  fmt.grouped = (v) => (v == null || v === "" || isNaN(Number(v))) ? "" : (demoOn() ? _maskInt(v) : o.grouped(v));
})();

const CHART_COLORS = ["#4c8dff", "#3ecf8e", "#ffd166", "#ff6b6b", "#b78cff", "#5bd1d7", "#ff9f6b", "#8b91a3"];
Chart.defaults.color = "#8b91a3";
Chart.defaults.borderColor = "#2c3040";
