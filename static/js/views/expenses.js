const SUB_LABELS = {
  "subscription-work": "💼 Work / business",
  "subscription-entertainment": "🎬 Entertainment",
  "subscription-health": "🚴 Health / sport",
  "subscription-other": "🔧 Other",
};

function _row(i, cm) {
  const inv = i.invoice
    ? `<button data-inv="${i.id}" class="badge" style="cursor:pointer;background:#1f6f4a;color:#fff;border:none" title="click to unmark">📄 Invoiced</button>`
    : `<button data-inv="${i.id}" class="badge" style="cursor:pointer;opacity:.55" title="click to mark as a business expense with an invoice">no invoice</button>`;
  const yearly = (i.billing || "monthly") === "yearly";
  const bill = yearly
    ? `<button data-bill="${i.id}" class="badge" style="cursor:pointer;background:#2b5f8f;color:#fff;border:none" title="billed yearly (amount = 1/12) — click to switch to monthly">📅 yearly</button>`
    : `<button data-bill="${i.id}" class="badge" style="cursor:pointer;opacity:.7" title="billed monthly — an annual plan is often 15–20% cheaper; click once you switch">monthly</button>`;
  return `<tr>
    <td>${esc(i.name)}</td>
    <td>${inv}</td>
    <td>${bill}</td>
    <td>${esc(i.payer)}</td>
    <td>${i.essential ? "✓" : ""}</td>
    <td style="text-align:right" data-val="${i.id}">${(i.currency || window.APP_CURRENCY || "PLN") !== (window.APP_CURRENCY || "PLN") ? `<span title="${i.fx_missing ? "no rate in the cache — amount not converted" : "rate " + fmt.num(i.fx_rate, 4)}">${fmt.num(i.latest_amount_ccy, 2)} ${i.currency} ${i.fx_missing ? "⚠️" : "≈ " + fmt.money(i.latest_amount)}</span>` : fmt.money(i.latest_amount)}</td>
    <td class="muted">${i.latest_month || "—"}</td>
    <td><button data-upd="${i.id}" title="${i.current_month_set ? "amount for " + cm + " already entered — correct it" : "enter the new amount effective from " + cm}">Change amount</button></td>
    <td><button class="danger" data-del="${i.id}">✕</button></td>
  </tr>`;
}

function _table(items, cm, emptyMsg) {
  if (!items.length) return `<div class="empty">${emptyMsg}</div>`;
  return `<table><thead><tr>
    <th>Name</th><th>Invoiced?</th><th>Billing</th><th>Payer</th><th>Essential</th>
    <th style="text-align:right">Amount</th><th title="effective since">Since</th><th></th><th></th>
  </tr></thead><tbody>${items.map((i) => _row(i, cm)).join("")}</tbody></table>`;
}

// Invoice checklist: ticks per month live in the browser (a helper for the monthly
// bookkeeping review, not financial data).
const _invKey = (m) => "kist.invoiceCheck." + m;
function _invLoad(m) { try { return JSON.parse(localStorage.getItem(_invKey(m)) || "{}"); } catch { return {}; } }
function _invSave(m, v) { try { localStorage.setItem(_invKey(m), JSON.stringify(v)); } catch { /* no browser storage */ } }
function _invOnly() { try { return localStorage.getItem("kist.invoiceOnly") === "1"; } catch { return false; } }

function _invoiceChecklist(items, month) {
  const done = _invLoad(month);
  const n = items.filter((i) => done[i.id]).length;
  const total = items.reduce((a, i) => a + (i.latest_amount || 0), 0);
  const base = window.APP_CURRENCY || "PLN";
  return `<div class="card mt">
    <div class="row" style="justify-content:space-between;align-items:center">
      <h3 style="margin:0">📄 Invoices to check</h3>
      <label class="muted">Month <input type="month" id="invMonth" value="${month}"></label>
    </div>
    <div class="mt"><b class="${n === items.length ? "pos" : ""}">${n} of ${items.length}</b> checked
      <span class="muted">· total ${fmt.money(total)}/mo</span>
      <div style="height:6px;border-radius:3px;background:rgba(127,127,127,.2);margin-top:6px">
        <div style="height:6px;border-radius:3px;width:${items.length ? (100 * n / items.length) : 0}%;background:${CHART_COLORS[1]}"></div></div></div>
    ${items.length ? `<table class="mt"><thead><tr><th style="width:40px">✓</th><th>Item</th><th>Group</th>
      <th style="text-align:right">Amount</th><th>Billing</th></tr></thead><tbody>
      ${items.map((i) => `<tr style="${done[i.id] ? "opacity:.55" : ""}">
        <td><input type="checkbox" data-invchk="${i.id}" ${done[i.id] ? "checked" : ""} aria-label="invoice checked: ${esc(i.name)}"></td>
        <td>${done[i.id] ? `<s>${esc(i.name)}</s>` : esc(i.name)}</td>
        <td class="muted">${(i.category || "").startsWith("subscription-") ? "subscription" : esc(i.entity || "personal")}</td>
        <td style="text-align:right">${(i.currency || base) !== base ? `${fmt.num(i.latest_amount_ccy, 2)} ${i.currency}` : fmt.money(i.latest_amount)}</td>
        <td class="muted">${(i.billing || "monthly") === "yearly" ? "📅 yearly (one invoice a year)" : "monthly"}</td></tr>`).join("")}
      </tbody></table>` : '<div class="empty mt">No item has the “📄 Invoiced” tag.</div>'}
  </div>`;
}

async function renderExpenses(el) {
  const s = await api.get("/api/expenses/summary");
  const cm = s.current_month;
  const invOnly = _invOnly();
  const invItems = s.items.filter((i) => i.invoice);
  const stale = s.items.filter((i) => i.latest_amount != null && !i.current_month_set);
  const missing = s.items.filter((i) => i.latest_amount == null);

  const isSub = (i) => (i.category || "").startsWith("subscription-");
  const personal = s.items.filter((i) => (i.entity || "personal") === "personal" && !isSub(i));
  const subs = s.items.filter(isSub);
  const otherEntities = [...new Set(s.items
    .filter((i) => (i.entity || "personal") !== "personal" && !isSub(i))
    .map((i) => i.entity))].sort();
  const subGroups = Object.keys(SUB_LABELS).map((cat) => ({
    cat, label: SUB_LABELS[cat], items: subs.filter((i) => i.category === cat),
  })).filter((g) => g.items.length);
  const sum = (arr) => arr.reduce((a, i) => a + (i.latest_amount || 0), 0);
  const subTotal = sum(subs);

  el.innerHTML = `
    <h2>Fixed Expenses</h2>
    <div class="grid cols-4">
      <div class="card kpi"><div class="label">Total fixed (mine)</div>
        <div class="value">${fmt.money(s.total_mine)}</div>
        <div class="sub">month: ${cm}</div></div>
      <div class="card kpi"><div class="label">Of which essential</div>
        <div class="value">${fmt.money(s.essential_mine)}</div></div>
      <div class="card kpi"><div class="label">Subscriptions total</div>
        <div class="value">${fmt.money(subTotal)}</div></div>
      <div class="card kpi"><div class="label">📄 Invoiced total</div>
        <div class="value">${fmt.money(s.invoiceable_total)}</div>
        <div class="sub">deductible/business costs per month</div></div>
    </div>
    ${(s.optimizations && s.optimizations.length) || (s.savings_done && s.savings_done.items.length) ? `<div class="card mt" style="border-left:3px solid ${CHART_COLORS[2]}">
      <h3>💡 Cost optimization</h3>
      ${s.savings_done && s.savings_done.items.length ? `<div class="mt" style="padding:10px 12px;border-radius:8px;background:rgba(127,127,127,.08)">
        <b class="pos">✅ Savings achieved: ${fmt.money(s.savings_done.yearly)}/yr</b> <span class="muted">(${fmt.money(s.savings_done.monthly)}/mo)</span>
        <ul style="margin:6px 0 0;padding-left:18px">${s.savings_done.items.map((r) => `<li class="mt">${esc(r.date || "")} · <b>${esc(r.name)}</b>: ${fmt.money(r.before_monthly)} → ${fmt.money(r.after_monthly)}/mo
          <span class="pos">−${fmt.money(r.saved_yearly)}/yr</span>${r.note ? ` <span class="muted">· ${esc(r.note)}</span>` : ""}</li>`).join("")}</ul></div>` : ""}
      <ul class="mt" style="margin:0;padding-left:18px">
        ${s.optimizations.map((o) => `<li class="mt ${o.severity === "warn" ? "" : "muted"}">${o.text}</li>`).join("")}
      </ul>
      ${help(`These hints are computed from your own data; they don't scan the
        market for live deals.`, "where these hints come from")}
    </div>` : ""}
    <div class="row mt">
      <button id="invToggle" class="${invOnly ? "primary" : ""}" aria-pressed="${invOnly}">📄 Invoice items only (${invItems.length})</button>
      <span class="muted" style="font-size:.85em">${invOnly ? "checklist for the monthly invoice review; click to go back to all items" : "show only the items you get an invoice for"}</span>
    </div>
    ${invOnly ? _invoiceChecklist(invItems, window._invMonth || cm) : `
    <div class="card mt">
      <h3>Add an item</h3>
      <div class="row">
        <input id="eName" placeholder="name (e.g. Rent)" style="flex:1">
        <input id="eEntity" placeholder="entity (personal / business / rental…)" list="eEntityList" value="personal" style="width:170px">
        <datalist id="eEntityList"><option value="personal"><option value="business">${otherEntities.map((e) => `<option value="${esc(e)}">`).join("")}</datalist>
        <select id="eCategory">
          <option value="">no category</option>
          <option value="subscription-work">Subscription — work</option>
          <option value="subscription-entertainment">Subscription — entertainment</option>
          <option value="subscription-health">Subscription — health / sport</option>
          <option value="subscription-other">Subscription — other</option>
        </select>
        <select id="eBilling" title="how you pay: monthly, or once a year (enter the amount as 1/12)">
          <option value="monthly" selected>monthly</option><option value="yearly">yearly</option>
        </select>
        <select id="ePayer"><option selected>me</option><option>partner</option><option>tenant</option></select>
        <label style="display:flex;align-items:center;gap:4px"><input type="checkbox" id="eEssential" checked> essential</label>
        <label style="display:flex;align-items:center;gap:4px" title="a business expense you'll get an invoice for"><input type="checkbox" id="eInvoice"> 📄 invoiced</label>
        <select id="eCurrency" title="item currency — enter the amount in this currency; converted at the cached rate">${["PLN", "EUR", "USD", "GBP", "CHF"].map((c) => `<option ${c === (window.APP_CURRENCY || "PLN") ? "selected" : ""}>${c}</option>`).join("")}</select>
        <input data-num id="eAmount" placeholder="amount (this month)">
        <button class="primary" id="eAdd">Add</button>
      </div>
      ${help(`An item you don't change doesn't need re-entering every month — it
        automatically "carries" its last amount forward. Only update what actually changed.
        A new amount applies from the current month and carries forward until you change it again.`, "how amounts work")}
    </div>

    <div class="card mt"><h3>Personal</h3>${_table(personal, cm, "No items yet")}</div>

    <div class="card mt"><h3>Subscriptions <span class="muted">(${fmt.money(subTotal)}/mo)</span></h3>
      ${subGroups.length ? subGroups.map((g) =>
        `<h4 class="mt">${g.label} <span class="muted">${fmt.money(g.items.reduce((a, i) => a + (i.latest_amount || 0), 0))}</span></h4>${_table(g.items, cm, "—")}`
      ).join("") : '<div class="empty">No subscriptions yet — add one with a category above</div>'}
    </div>

    ${otherEntities.map((ent) => {
      const its = s.items.filter((i) => i.entity === ent && !isSub(i));
      const total = sum(its);
      return `<div class="card mt"><h3>${esc(ent.charAt(0).toUpperCase() + ent.slice(1))} <span class="muted">(${fmt.money(total)}/mo)</span></h3>
        ${_table(its, cm, "No items yet")}
      </div>`;
    }).join("")}

    <div class="grid cols-2 mt">
      <div class="card"><h3>Monthly trend</h3><canvas id="eChart" height="90"></canvas></div>
      <div class="card"><h3>By category (current month)</h3><canvas id="eCatChart" height="90"></canvas></div>
    </div>`}`;

  document.getElementById("invToggle").addEventListener("click", () => {
    try { localStorage.setItem("kist.invoiceOnly", invOnly ? "0" : "1"); } catch { /* no browser storage */ }
    route();
  });
  if (invOnly) {
    const month = window._invMonth || cm;
    document.getElementById("invMonth").addEventListener("change", (e) => { window._invMonth = e.target.value || cm; route(); });
    el.querySelectorAll("[data-invchk]").forEach((c) => c.addEventListener("change", () => {
      const done = _invLoad(month);
      if (c.checked) done[c.dataset.invchk] = true; else delete done[c.dataset.invchk];
      _invSave(month, done);
      route();
    }));
    return;
  }

  el.querySelectorAll("[data-upd]").forEach((b) =>
    b.addEventListener("click", () => {
      const item = s.items.find((i) => i.id === b.dataset.upd);
      inlineEdit(el.querySelector(`[data-val="${b.dataset.upd}"]`), {
        value: item && item.latest_amount_ccy != null ? item.latest_amount_ccy : (item && item.latest_amount != null ? item.latest_amount : ""),
        placeholder: `from ${cm} (${(item && item.currency) || ""})`,
        onSave: async (v) => {
          await api.post(`/api/expenses/items/${b.dataset.upd}/values`, { month: cm, amount: v });
          route();
        },
      });
    }));
  el.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Delete this item and its history?")) return;
      await api.del("/api/expenses/items/" + b.dataset.del);
      route();
    }));
  el.querySelectorAll("[data-inv]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const on = btn.textContent.includes("Invoiced");
      await api.put("/api/expenses/items/" + btn.dataset.inv, { invoice: !on });
      route();
    }));
  el.querySelectorAll("[data-bill]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const yearly = btn.textContent.includes("yearly");
      await api.put("/api/expenses/items/" + btn.dataset.bill, { billing: yearly ? "monthly" : "yearly" });
      route();
    }));

  document.getElementById("eAdd").addEventListener("click", async () => {
    const name = document.getElementById("eName").value.trim();
    const amount = parseNum(document.getElementById("eAmount"));
    if (!name) { alert("Enter a name"); return; }
    await api.post("/api/expenses/items", {
      name,
      entity: document.getElementById("eEntity").value.trim() || "personal",
      category: document.getElementById("eCategory").value,
      currency: document.getElementById("eCurrency").value,
      payer: document.getElementById("ePayer").value,
      essential: document.getElementById("eEssential").checked,
      invoice: document.getElementById("eInvoice").checked,
      billing: document.getElementById("eBilling").value,
      amount: isNaN(amount) ? undefined : amount,
      month: cm,
    });
    route();
  });

  if (s.trend.length) {
    trackChart(new Chart(document.getElementById("eChart"), {
      type: "line",
      data: {
        labels: s.trend.map((p) => p.month),
        datasets: [
          { label: "Total", data: s.trend.map((p) => p.total),
            borderColor: CHART_COLORS[1], backgroundColor: "transparent", tension: 0.25 },
          { label: "Essential", data: s.trend.map((p) => p.essential),
            borderColor: CHART_COLORS[2], backgroundColor: "transparent", tension: 0.25 },
        ],
      },
      options: { plugins: { legend: { display: true } } },
    }));
  }
  if (s.by_category.length) {
    trackChart(new Chart(document.getElementById("eCatChart"), {
      type: "bar",
      data: {
        labels: s.by_category.map((c) => c.category),
        datasets: [{ data: s.by_category.map((c) => c.total),
          backgroundColor: CHART_COLORS[0] }],
      },
      options: { indexAxis: "y", plugins: { legend: { display: false } } },
    }));
  }
}
