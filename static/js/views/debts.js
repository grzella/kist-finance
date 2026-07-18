async function renderDebts(el) {
  const data = await api.get("/api/debts");
  el.innerHTML = `
    <h2>Loans</h2>
    <div class="grid cols-4">
      <div class="card kpi"><div class="label">Loans total</div>
        <div class="value">${fmt.pln(data.total)}</div></div>
      <div class="card kpi"><div class="label">Total monthly cost</div>
        <div class="value">${fmt.pln(data.monthly_cost_total || 0)}</div>
        <div class="sub">installments ${fmt.pln(data.debts.reduce((s, d) => s + (d.minimum_payment || 0), 0))} + insurance and other</div></div>
      <div class="card kpi"><div class="label">Total monthly interest</div>
        <div class="value">${fmt.pln(data.debts.reduce((s, d) => s + (d.interest_month || 0), 0))}</div>
        <div class="sub">principal: ${fmt.pln(data.debts.reduce((s, d) => s + (d.principal_month || 0), 0))}/mo</div></div>
      <div class="card kpi"><div class="label">Interest to maturity</div>
        <div class="value">${fmt.pln(data.debts.reduce((s, d) => s + (d.schedule.total_interest || 0), 0))}</div>
        <div class="sub">at current installments</div></div>
    </div>
    <div id="dList" class="mt"></div>
    <details class="card mt">
      <summary style="cursor:pointer;color:var(--muted,#9aa)">➕ Add a loan (rare action)</summary>
      <div class="row mt">
        <input id="dName" placeholder="name (e.g. mBank mortgage)" style="flex:1">
        <input data-num id="dBalance" placeholder="balance PLN">
        <input type="number" step="0.01" id="dRate" placeholder="interest rate %/yr" style="width:200px">
        <input data-num id="dPayment" placeholder="monthly installment PLN" style="width:150px">
      </div>
      <div class="row mt">
        <input type="number" id="dMonthsLeft" placeholder="installments left" style="width:130px">
        <input data-num id="dInsRepay" placeholder="repayment insurance /mo" style="width:170px">
        <input data-num id="dInsProp" placeholder="property insurance /mo" style="width:200px">
        <input data-num id="dExtra" placeholder="other costs /mo" style="width:160px">
        <button class="primary" id="dAdd">Add</button>
      </div>
      <div class="muted mt">The balance drops automatically each month by the principal part of the installment
        (installment − interest); interest is computed on the current balance.</div>
    </details>`;

  const list = document.getElementById("dList");
  if (!data.debts.length) {
    list.innerHTML = '<div class="empty">No loans — add the first one below</div>';
  } else {
    list.innerHTML = data.debts.map((d, idx) => {
      const s = d.schedule || {};
      const payoff = s.months == null ? "the installment does not cover the interest!"
        : s.months === 0 ? "paid off 🎉"
        : (() => {
            const dt = new Date(); dt.setMonth(dt.getMonth() + s.months);
            return `${s.months} mo → ~${dt.toISOString().slice(0, 7)}`;
          })();
      return `<div class="card mt">
        <div class="row" style="justify-content:space-between">
          <h3 style="margin:0">${d.name}</h3>
          <span class="badge">${fmt.pct(d.interest_rate, 2)} nominal
            ${d.effective_rate && d.effective_rate !== d.interest_rate ? `· ${fmt.pct(d.effective_rate, 2)} effective` : ""}</span>
        </div>
        <div class="row mt">
          <b>${fmt.pln(d.balance)}</b>
          <span class="muted">installment ${fmt.pln(d.minimum_payment)}/mo =
            principal <span class="pos">${fmt.pln(d.principal_month)}</span> +
            interest <span class="neg">${fmt.pln(d.interest_month)}</span>
            ${d.interest_month_actual ? "(per bank)" : "(model)"}</span>
        </div>
        <div class="muted">Payoff: ${payoff}
          ${s.total_interest != null ? `· interest to maturity: ${fmt.pln(s.total_interest)}` : ""}
          ${d.months_left != null ? `· installments left per bank: ${d.months_left}` : ""}</div>
        ${d.variable_projection ? `<div class="muted mt" style="border-left:3px solid #4c8dff;padding-left:8px">
          <b>After the fixed rate ends (${d.variable_projection.fixed_until})</b>, balance ~${fmt.pln(d.variable_projection.balance_at_switch)}:
          at today's WIBOR ${d.variable_projection.now.wibor}% + margin ${d.variable_projection.margin}% →
          installment <b>${fmt.pln(d.variable_projection.now.rata)}</b> (${fmt.pln(d.variable_projection.now.delta_vs_now)}/mo)
          ${d.variable_projection.forecast ? `· at the forecast WIBOR ${d.variable_projection.forecast.wibor}% →
          installment <b>${fmt.pln(d.variable_projection.forecast.rata)}</b> (${fmt.pln(d.variable_projection.forecast.delta_vs_now)}/mo)` : ""}
        </div>` : ""}
        <div class="muted">Total monthly cost: <b>${fmt.pln(d.monthly_cost_total)}</b>
          = installment ${fmt.pln(d.minimum_payment)}
          ${d.insurance_repayment ? `+ repayment insurance ${fmt.pln(d.insurance_repayment)}` : ""}
          ${d.insurance_property ? `+ property insurance ${fmt.pln(d.insurance_property)}` : ""}
          ${d.extra_monthly ? `+ other ${fmt.pln(d.extra_monthly)}` : ""}</div>
        <canvas id="dChart${idx}" height="60" class="mt"></canvas>
        <div class="row mt">
          <input data-num data-dover-in="${d.id}" placeholder="overpayment amount" style="width:160px">
          <button data-dover="${d.id}">Overpay</button>
          <input data-num data-dbal-in="${d.id}" placeholder="balance correction" style="width:160px">
          <button data-dbal="${d.id}">Adjust balance</button>
          <button class="danger" data-ddel="${d.id}">Delete</button>
        </div>
        <div class="row mt">
          <input type="number" data-dml-in="${d.id}" placeholder="installments left" value="${d.months_left ?? ""}" style="width:130px">
          <input data-num data-dir-in="${d.id}" placeholder="repayment insurance" value="${fmt.grouped(d.insurance_repayment)}" style="width:150px">
          <input data-num data-dip-in="${d.id}" placeholder="property insurance" value="${fmt.grouped(d.insurance_property)}" style="width:150px">
          <input data-num data-dex-in="${d.id}" placeholder="other costs" value="${fmt.grouped(d.extra_monthly)}" style="width:140px">
          <input data-num data-dint-in="${d.id}" placeholder="monthly interest per bank" value="${fmt.grouped(d.interest_month_actual)}" style="width:180px">
          <input data-num data-dcap-in="${d.id}" placeholder="monthly principal per bank" value="${fmt.grouped(d.principal_month_actual)}" style="width:180px">
          <button data-dmeta="${d.id}">Save costs</button>
        </div>
      </div>`;
    }).join("");

    data.debts.forEach((d, idx) => {
      if (!d.history.length) return;
      trackChart(new Chart(document.getElementById("dChart" + idx), {
        type: "line",
        data: {
          labels: d.history.map((h) => h.month),
          datasets: [{ label: "Balance", data: d.history.map((h) => h.balance),
            borderColor: CHART_COLORS[3], backgroundColor: "transparent", tension: 0.25 }],
        },
        options: { plugins: { legend: { display: false } } },
      }));
    });
  }

  document.getElementById("dAdd").addEventListener("click", async () => {
    const name = document.getElementById("dName").value.trim();
    const balance = parseNum(document.getElementById("dBalance"));
    if (!name || !balance) { alert("Enter a name and balance"); return; }
    const ml = parseInt(document.getElementById("dMonthsLeft").value, 10);
    await api.post("/api/debts", {
      name, balance,
      interest_rate: parseFloat(document.getElementById("dRate").value) || 0,
      minimum_payment: parseNum(document.getElementById("dPayment")) || 0,
      months_left: isNaN(ml) ? null : ml,
      insurance_repayment: parseNum(document.getElementById("dInsRepay")) || 0,
      insurance_property: parseNum(document.getElementById("dInsProp")) || 0,
      extra_monthly: parseNum(document.getElementById("dExtra")) || 0,
    });
    route();
  });
  list.querySelectorAll("[data-dover]").forEach((b) =>
    b.addEventListener("click", async () => {
      const v = parseNum(list.querySelector(`[data-dover-in="${b.dataset.dover}"]`));
      if (isNaN(v) || v <= 0) { alert("Enter an overpayment amount"); return; }
      await api.post(`/api/debts/${b.dataset.dover}/overpay`, { amount: v });
      route();
    }));
  list.querySelectorAll("[data-dbal]").forEach((b) =>
    b.addEventListener("click", async () => {
      const v = parseNum(list.querySelector(`[data-dbal-in="${b.dataset.dbal}"]`));
      if (isNaN(v)) { alert("Enter a balance"); return; }
      await api.put("/api/debts/" + b.dataset.dbal, { balance: v });
      route();
    }));
  list.querySelectorAll("[data-dmeta]").forEach((b) =>
    b.addEventListener("click", async () => {
      const id = b.dataset.dmeta;
      const ml = parseInt(list.querySelector(`[data-dml-in="${id}"]`).value, 10);
      await api.put("/api/debts/" + id, {
        months_left: isNaN(ml) ? null : ml,
        insurance_repayment: parseNum(list.querySelector(`[data-dir-in="${id}"]`)) || 0,
        insurance_property: parseNum(list.querySelector(`[data-dip-in="${id}"]`)) || 0,
        extra_monthly: parseNum(list.querySelector(`[data-dex-in="${id}"]`)) || 0,
        interest_month_actual: parseNum(list.querySelector(`[data-dint-in="${id}"]`)) || null,
        principal_month_actual: parseNum(list.querySelector(`[data-dcap-in="${id}"]`)) || null,
      });
      route();
    }));
  list.querySelectorAll("[data-ddel]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Delete this loan along with its history?")) return;
      await api.del("/api/debts/" + b.dataset.ddel);
      route();
    }));
}
