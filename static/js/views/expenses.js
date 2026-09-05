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
    <td>${i.name}</td>
    <td>${inv}</td>
    <td>${bill}</td>
    <td>${i.payer}</td>
    <td>${i.essential ? "✓" : ""}</td>
    <td style="text-align:right">${(i.currency || "USD") !== (window.APP_CURRENCY || "USD") ? `<span title="${i.fx_missing ? "no rate in the cache — amount not converted" : "rate " + fmt.num(i.fx_rate, 4)}">${fmt.num(i.latest_amount_ccy, 2)} ${i.currency} ${i.fx_missing ? "⚠️" : "≈ " + fmt.usd(i.latest_amount)}</span>` : fmt.usd(i.latest_amount)}</td>
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

async function renderExpenses(el) {
  const s = await api.get("/api/expenses/summary");
  const cm = s.current_month;
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
        <div class="value">${fmt.usd(s.total_mine)}</div>
        <div class="sub">month: ${cm}</div></div>
      <div class="card kpi"><div class="label">Of which essential</div>
        <div class="value">${fmt.usd(s.essential_mine)}</div></div>
      <div class="card kpi"><div class="label">Subscriptions total</div>
        <div class="value">${fmt.usd(subTotal)}</div></div>
      <div class="card kpi"><div class="label">📄 Invoiced total</div>
        <div class="value">${fmt.usd(s.invoiceable_total)}</div>
        <div class="sub">deductible/business costs per month</div></div>
    </div>
    ${(s.optimizations && s.optimizations.length) ? `<div class="card mt" style="border-left:3px solid ${CHART_COLORS[2]}">
      <h3>💡 Cost optimization</h3>
      <ul class="mt" style="margin:0;padding-left:18px">
        ${s.optimizations.map((o) => `<li class="mt ${o.severity === "warn" ? "" : "muted"}">${o.text}</li>`).join("")}
      </ul>
      <div class="muted mt">These hints are computed from your own data — they don't scan the
        market for live deals (that would fit a scheduled job, not a page render).</div>
    </div>` : ""}
    <div class="card mt">
      <h3>Add an item</h3>
      <div class="row">
        <input id="eName" placeholder="name (e.g. Rent)" style="flex:1">
        <input id="eEntity" placeholder="entity (personal / business / rental…)" list="eEntityList" value="personal" style="width:170px">
        <datalist id="eEntityList"><option value="personal"><option value="business">${otherEntities.map((e) => `<option value="${e}">`).join("")}</datalist>
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
        <select id="eCurrency" title="item currency — enter the amount in this currency; converted at the cached rate"><option selected>USD</option><option>EUR</option><option>PLN</option><option>GBP</option></select>
        <input data-num id="eAmount" placeholder="amount (this month)">
        <button class="primary" id="eAdd">Add</button>
      </div>
      <div class="muted mt">An item you don't change doesn't need re-entering every month — it
        automatically "carries" its last amount forward. Only update what actually changed.</div>
    </div>

    <div class="card mt"><h3>Personal</h3>${_table(personal, cm, "No items yet")}</div>

    <div class="card mt"><h3>Subscriptions <span class="muted">(${fmt.usd(subTotal)}/mo)</span></h3>
      ${subGroups.length ? subGroups.map((g) =>
        `<h4 class="mt">${g.label} <span class="muted">${fmt.usd(g.items.reduce((a, i) => a + (i.latest_amount || 0), 0))}</span></h4>${_table(g.items, cm, "—")}`
      ).join("") : '<div class="empty">No subscriptions yet — add one with a category above</div>'}
    </div>

    ${otherEntities.map((ent) => {
      const its = s.items.filter((i) => i.entity === ent && !isSub(i));
      const total = sum(its);
      return `<div class="card mt"><h3>${ent.charAt(0).toUpperCase() + ent.slice(1)} <span class="muted">(${fmt.usd(total)}/mo)</span></h3>
        ${_table(its, cm, "No items yet")}
      </div>`;
    }).join("")}

    <div class="grid cols-2 mt">
      <div class="card"><h3>Monthly trend</h3><canvas id="eChart" height="90"></canvas></div>
      <div class="card"><h3>By category (current month)</h3><canvas id="eCatChart" height="90"></canvas></div>
    </div>`;

  el.querySelectorAll("[data-upd]").forEach((b) =>
    b.addEventListener("click", async () => {
      const item = s.items.find((i) => i.id === b.dataset.upd);
      const v = prompt(`New amount from ${cm} (${(item && item.currency) || ""}) — it carries forward every month until you change it again:`);
      if (v === null || v === "" || isNaN(parseNum(v))) return;
      await api.post(`/api/expenses/items/${b.dataset.upd}/values`,
        { month: cm, amount: parseNum(v) });
      route();
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
