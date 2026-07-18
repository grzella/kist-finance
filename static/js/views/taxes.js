async function renderTaxes(el) {
  const d = await api.get("/api/taxes");
  el.innerHTML = `
    <h2>🧾 Taxes — overview and calendar</h2>
    <div class="muted" style="margin-bottom:12px">Taxes you manage yourself (rental, business) + those withheld automatically, for reference.
      Annual amounts are estimates.</div>

    <div class="grid cols-3">
      <div class="card kpi"><div class="label">Taxes you manage / yr (est.)</div>
        <div class="value">${fmt.pln(d.self_managed_annual)}</div>
        <div class="sub">rental + business social security + business income tax</div></div>
      <div class="card kpi"><div class="label">Next payment</div>
        <div class="value" style="font-size:1.3em">${d.calendar[0] ? d.calendar[0].date : "—"}</div>
        <div class="sub">${d.calendar[0] ? d.calendar[0].what : ""}${d.calendar[0] && d.calendar[0].amount ? " · ~" + fmt.pln(d.calendar[0].amount) : ""}</div></div>
      <div class="card kpi"><div class="label">Annual tax return</div>
        <div class="value" style="font-size:1.3em">${d.calendar[1] ? d.calendar[1].date : "—"}</div>
        <div class="sub">${d.calendar[1] ? d.calendar[1].what : ""}</div></div>
    </div>

    <div class="card mt">
      <h3>Tax sources</h3>
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Source</th><th>Rate</th><th style="text-align:right">Base/yr</th>
          <th style="text-align:right">Tax/yr</th><th>Cadence</th><th>Who</th></tr></thead>
        <tbody>${d.items.map((i) => `<tr>
          <td><b>${i.source}</b>${i.note ? `<div class="muted" style="font-size:.8em">${i.note}</div>` : ""}</td>
          <td>${i.rate}</td>
          <td style="text-align:right">${i.base != null ? fmt.pln(i.base) : "—"}</td>
          <td style="text-align:right">${i.tax != null ? "<b>" + fmt.pln(i.tax) + "</b>" : '<span class="muted">withheld</span>'}</td>
          <td style="font-size:.88em">${i.cadence}</td>
          <td><span class="badge">${i.managed}</span></td>
        </tr>`).join("")}</tbody>
      </table></div>
    </div>

    <div class="card mt" style="border-left:4px solid #3ecf8e">
      <h3 style="margin-top:0">💡 Tax optimizations</h3>
      <ul style="padding-left:18px">${d.optimizations.map((o) => `<li class="mt" style="font-size:.92em">${o}</li>`).join("")}</ul>
    </div>

    <div class="card mt">
      <h3>Assumptions (editable)</h3>
      <div class="row" style="flex-wrap:wrap;gap:12px">
        <label class="muted">Rent/mo (PLN)<br><input data-num id="txRent" value="${fmt.grouped(d.assumptions.tax_rental_monthly)}" style="width:130px"></label>
        <label class="muted">Lump-sum tax rate (%)<br><input data-num id="txRate" value="${d.assumptions.tax_rental_rate}" style="width:110px"></label>
        <label class="muted">Business social security/mo (PLN)<br><input data-num id="txZus" value="${fmt.grouped(d.assumptions.tax_zus_monthly)}" style="width:130px"></label>
        <button class="primary" id="txSave" style="align-self:flex-end">Save</button>
      </div>
    </div>`;

  document.getElementById("txSave").addEventListener("click", async () => {
    await api.put("/api/settings", {
      tax_rental_monthly: parseNum(document.getElementById("txRent")),
      tax_rental_rate: parseNum(document.getElementById("txRate")),
      tax_zus_monthly: parseNum(document.getElementById("txZus")),
    });
    route();
  });
}
