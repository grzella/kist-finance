async function renderDebts(el) {
  const data = await api.get("/api/debts");
  el.innerHTML = `
    <h2>Kredyty</h2>
    <div class="grid cols-4">
      <div class="card kpi"><div class="label">Kredyty łącznie</div>
        <div class="value">${fmt.pln(data.total)}</div></div>
      <div class="card kpi"><div class="label">Koszt mies. łącznie</div>
        <div class="value">${fmt.pln(data.monthly_cost_total || 0)}</div>
        <div class="sub">raty ${fmt.pln(data.debts.reduce((s, d) => s + (d.minimum_payment || 0), 0))} + ubezpieczenia i inne</div></div>
      <div class="card kpi"><div class="label">Odsetki mies. łącznie</div>
        <div class="value">${fmt.pln(data.debts.reduce((s, d) => s + (d.interest_month || 0), 0))}</div>
        <div class="sub">kapitał: ${fmt.pln(data.debts.reduce((s, d) => s + (d.principal_month || 0), 0))}/mies.</div></div>
      <div class="card kpi"><div class="label">Odsetki do końca</div>
        <div class="value">${fmt.pln(data.debts.reduce((s, d) => s + (d.schedule.total_interest || 0), 0))}</div>
        <div class="sub">przy obecnych ratach</div></div>
    </div>
    <div id="dList" class="mt"></div>
    <details class="card mt">
      <summary style="cursor:pointer;color:var(--muted,#9aa)">➕ Dodaj kredyt (rzadka akcja)</summary>
      <div class="row mt">
        <input id="dName" placeholder="nazwa (np. hipoteka mBank)" style="flex:1">
        <input data-num id="dBalance" placeholder="saldo PLN">
        <input type="number" step="0.01" id="dRate" placeholder="oprocentowanie % rocznie" style="width:200px">
        <input data-num id="dPayment" placeholder="rata mies. PLN" style="width:150px">
      </div>
      <div class="row mt">
        <input type="number" id="dMonthsLeft" placeholder="pozostało rat" style="width:130px">
        <input data-num id="dInsRepay" placeholder="ubezp. spłaty /mies." style="width:170px">
        <input data-num id="dInsProp" placeholder="ubezp. nieruchomości /mies." style="width:200px">
        <input data-num id="dExtra" placeholder="inne koszty /mies." style="width:160px">
        <button class="primary" id="dAdd">Dodaj</button>
      </div>
      <div class="muted mt">Saldo spada samo co miesiąc o część kapitałową raty
        (rata − odsetki); odsetki liczone od bieżącego salda.</div>
    </details>`;

  const list = document.getElementById("dList");
  if (!data.debts.length) {
    list.innerHTML = '<div class="empty">Brak kredytów — dodaj pierwszy poniżej</div>';
  } else {
    list.innerHTML = data.debts.map((d, idx) => {
      const s = d.schedule || {};
      const payoff = s.months == null ? "rata nie pokrywa odsetek!"
        : s.months === 0 ? "spłacony 🎉"
        : (() => {
            const dt = new Date(); dt.setMonth(dt.getMonth() + s.months);
            return `${s.months} mies. → ~${dt.toISOString().slice(0, 7)}`;
          })();
      return `<div class="card mt">
        <div class="row" style="justify-content:space-between">
          <h3 style="margin:0">${d.name}</h3>
          <span class="badge">${fmt.pct(d.interest_rate, 2)} nominalnie
            ${d.effective_rate && d.effective_rate !== d.interest_rate ? `· ${fmt.pct(d.effective_rate, 2)} efektywnie` : ""}</span>
        </div>
        <div class="row mt">
          <b>${fmt.pln(d.balance)}</b>
          <span class="muted">rata ${fmt.pln(d.minimum_payment)}/mies. =
            kapitał <span class="pos">${fmt.pln(d.principal_month)}</span> +
            odsetki <span class="neg">${fmt.pln(d.interest_month)}</span>
            ${d.interest_month_actual ? "(wg banku)" : "(model)"}</span>
        </div>
        <div class="muted">Spłata: ${payoff}
          ${s.total_interest != null ? `· odsetki do końca: ${fmt.pln(s.total_interest)}` : ""}
          ${d.months_left != null ? `· wg banku pozostało rat: ${d.months_left}` : ""}</div>
        ${d.variable_projection ? `<div class="muted mt" style="border-left:3px solid #4c8dff;padding-left:8px">
          <b>Po końcu stałej stopy (${d.variable_projection.fixed_until})</b>, saldo ~${fmt.pln(d.variable_projection.balance_at_switch)}:
          przy dzisiejszym WIBOR ${d.variable_projection.now.wibor}% + marża ${d.variable_projection.margin}% →
          rata <b>${fmt.pln(d.variable_projection.now.rata)}</b> (${fmt.pln(d.variable_projection.now.delta_vs_now)}/mies.)
          ${d.variable_projection.forecast ? `· przy prognozowanym WIBOR ${d.variable_projection.forecast.wibor}% →
          rata <b>${fmt.pln(d.variable_projection.forecast.rata)}</b> (${fmt.pln(d.variable_projection.forecast.delta_vs_now)}/mies.)` : ""}
        </div>` : ""}
        <div class="muted">Koszt mies. łącznie: <b>${fmt.pln(d.monthly_cost_total)}</b>
          = rata ${fmt.pln(d.minimum_payment)}
          ${d.insurance_repayment ? `+ ubezp. spłaty ${fmt.pln(d.insurance_repayment)}` : ""}
          ${d.insurance_property ? `+ ubezp. nieruchomości ${fmt.pln(d.insurance_property)}` : ""}
          ${d.extra_monthly ? `+ inne ${fmt.pln(d.extra_monthly)}` : ""}</div>
        <canvas id="dChart${idx}" height="60" class="mt"></canvas>
        <div class="row mt">
          <input data-num data-dover-in="${d.id}" placeholder="kwota nadpłaty" style="width:160px">
          <button data-dover="${d.id}">Nadpłać</button>
          <input data-num data-dbal-in="${d.id}" placeholder="korekta salda" style="width:160px">
          <button data-dbal="${d.id}">Koryguj saldo</button>
          <button class="danger" data-ddel="${d.id}">Usuń</button>
        </div>
        <div class="row mt">
          <input type="number" data-dml-in="${d.id}" placeholder="pozostało rat" value="${d.months_left ?? ""}" style="width:130px">
          <input data-num data-dir-in="${d.id}" placeholder="ubezp. spłaty" value="${fmt.grouped(d.insurance_repayment)}" style="width:150px">
          <input data-num data-dip-in="${d.id}" placeholder="ubezp. nieruch." value="${fmt.grouped(d.insurance_property)}" style="width:150px">
          <input data-num data-dex-in="${d.id}" placeholder="inne koszty" value="${fmt.grouped(d.extra_monthly)}" style="width:140px">
          <input data-num data-dint-in="${d.id}" placeholder="odsetki mies. wg banku" value="${fmt.grouped(d.interest_month_actual)}" style="width:180px">
          <input data-num data-dcap-in="${d.id}" placeholder="kapitał mies. wg banku" value="${fmt.grouped(d.principal_month_actual)}" style="width:180px">
          <button data-dmeta="${d.id}">Zapisz koszty</button>
        </div>
      </div>`;
    }).join("");

    data.debts.forEach((d, idx) => {
      if (!d.history.length) return;
      trackChart(new Chart(document.getElementById("dChart" + idx), {
        type: "line",
        data: {
          labels: d.history.map((h) => h.month),
          datasets: [{ label: "Saldo", data: d.history.map((h) => h.balance),
            borderColor: CHART_COLORS[3], backgroundColor: "transparent", tension: 0.25 }],
        },
        options: { plugins: { legend: { display: false } } },
      }));
    });
  }

  document.getElementById("dAdd").addEventListener("click", async () => {
    const name = document.getElementById("dName").value.trim();
    const balance = parseNum(document.getElementById("dBalance"));
    if (!name || !balance) { alert("Podaj nazwę i saldo"); return; }
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
      if (isNaN(v) || v <= 0) { alert("Podaj kwotę nadpłaty"); return; }
      await api.post(`/api/debts/${b.dataset.dover}/overpay`, { amount: v });
      route();
    }));
  list.querySelectorAll("[data-dbal]").forEach((b) =>
    b.addEventListener("click", async () => {
      const v = parseNum(list.querySelector(`[data-dbal-in="${b.dataset.dbal}"]`));
      if (isNaN(v)) { alert("Podaj saldo"); return; }
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
      if (!confirm("Usunąć kredyt wraz z historią?")) return;
      await api.del("/api/debts/" + b.dataset.ddel);
      route();
    }));
}
