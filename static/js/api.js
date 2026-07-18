const api = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  },
  async send(method, path, body) {
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
  fmt.pln = (v) => v == null ? "—" : (demoOn() ? _maskInt(v) + " zł" : o.pln(v));
  fmt.usd = (v) => v == null ? "—" : (demoOn() ? "$" + _maskInt(v) + "." + _maskDec(2) : o.usd(v));
  fmt.num = (v, d = 2) => v == null ? "—" : (demoOn() ? _maskInt(v) + (d > 0 ? "," + _maskDec(d) : "") : o.num(v, d));
  fmt.pct = (v, d = 1) => v == null ? "—" : (demoOn() ? _maskInt(v) + (d > 0 ? "," + _maskDec(d) : "") + "%" : o.pct(v, d));
  fmt.grouped = (v) => (v == null || v === "" || isNaN(Number(v))) ? "" : (demoOn() ? _maskInt(v) : o.grouped(v));
})();

const CHART_COLORS = ["#4c8dff", "#3ecf8e", "#ffd166", "#ff6b6b", "#b78cff", "#5bd1d7", "#ff9f6b", "#8b91a3"];
Chart.defaults.color = "#8b91a3";
Chart.defaults.borderColor = "#2c3040";
