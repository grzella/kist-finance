"""planner_allocation — Asset allocation: classes, targets, 5/25 drift, leverage.

Split out of planner.py on 2026-09-05 (code moved 1:1; other modules are reached through `P`).
"""

import engine_bridge as eb
from planner_proxy import P

# ---------- asset allocation ----------

ALLOC_TARGETS = {  # target % of net wealth (UI-editable model)
    "real_estate": 55, "etf": 22, "rsu": 4,
    "cash": 8, "retirement": 5, "car": 6,
}
ALLOC_LABELS = {
    "real_estate": "🏠 Real estate (equity)", "etf": "🌍 Stocks/ETF (brokerage)",
    "rsu": "💎 RSU shares", "cash": "💵 Cash", "retirement": "🏦 Retirement (pension accounts)",
    "car": "🚗 Car (consumable)",
}
# saved alloc_targets may predate the key rename — accept old keys on read
_ALLOC_LEGACY = {"nieruchomosci": "real_estate", "team": "rsu", "gotowka": "cash",
                 "emerytalne": "retirement", "auto": "car"}


def _alloc_class(name):
    n = name.lower()
    if "mieszkan" in n or "dom" in n or "nieruchom" in n or "estate" in n or "apartment" in n:
        return "real_estate"
    if "xtb" in n or "etf" in n or "broker" in n:
        return "etf"
    if "rsu" in n or "espp" in n or "stock grant" in n:
        return "rsu"
    if "ikze" in n or "ike" in n or "ppk" in n or "emerytal" in n or "pension" in n or "401k" in n:
        return "retirement"
    if "cash" in n or "checking" in n or "account" in n or "saving" in n:
        return "cash"
    if " ev" in n or "auto" in n or "samoch" in n or "car" in n or "vehicle" in n:
        return "car"
    return None


def alloc_targets():
    """Targets from the alloc_targets setting (UI-editable), falling back to
    the built-in defaults. Values are % of net wealth."""
    import json as _json
    t = dict(ALLOC_TARGETS)
    raw = P.get_setting("alloc_targets")
    if raw:
        try:
            for k, v in _json.loads(raw).items():
                k = _ALLOC_LEGACY.get(k, k)
                if k in t and P._num(v) is not None:
                    t[k] = float(v)
        except ValueError:
            pass
    return t


def _leverage(w):
    """Leverage: debt/assets + real-estate LTV + a monthly trend, so that
    falling debt is VISIBLE. Series use carry-forward: debt balances from
    debt_values, assets from the wealth trend."""
    debts = w.get("debts") or []
    debt_total = w.get("debt_total") or 0
    assets = w.get("total") or 0
    re_val = 0.0
    for it in w.get("items", []):
        if _alloc_class(it.get("name", "")) == "real_estate" \
                and (it.get("latest_value") or 0) > 0:
            re_val += it["latest_value"]
    mort = sum(d["balance"] for d in debts) if debts else 0
    out = {
        "debt_total": round(debt_total, 0),
        "assets_total": round(assets, 0),
        "debt_to_assets_pct": round(100 * debt_total / assets, 1) if assets else None,
        "ltv_pct": round(100 * mort / re_val, 1) if re_val else None,
        "re_value": round(re_val, 0),
    }
    # trend: debt balance carried forward per debt + assets from the wealth trend
    rows = eb._rows("select debt_id, month, balance from debt_values "
                    "order by month, created_at")
    per_debt = {}
    for r in rows:
        per_debt.setdefault(r["debt_id"], []).append((r["month"], r["balance"]))
    asset_by_month = {t["month"]: t["total"] for t in (w.get("trend") or [])}
    months = sorted(set(asset_by_month)
                    | {m for srs in per_debt.values() for m, _ in srs})
    trend = []
    prev_assets = None
    for m in months:
        dtot = 0.0
        for srs in per_debt.values():
            past = [v for (mm, v) in srs if mm <= m]
            if past:
                dtot += past[-1]
        a = asset_by_month.get(m, prev_assets)
        prev_assets = a
        trend.append({"month": m, "debt": round(dtot, 0),
                      "assets": round(a, 0) if a else None,
                      "pct": round(100 * dtot / a, 1) if a else None})
    out["trend"] = trend
    return out


def allocation():
    w = P.wealth_summary()
    targets = alloc_targets()
    classes = {k: 0.0 for k in ALLOC_TARGETS}
    for it in w.get("items", []):
        if it.get("kind") in ("income",):
            continue
        cls = _alloc_class(it.get("name", ""))
        if not cls:
            continue
        # use equity for debt-linked (real estate), else latest value
        val = it.get("equity") if it.get("equity") is not None else (it.get("latest_value") or 0)
        classes[cls] += val or 0
    total = sum(classes.values()) or 1
    rows = []
    for k in ALLOC_TARGETS:
        pct = round(100 * classes[k] / total, 1)
        target = targets[k]
        drift = round(pct - target, 1)
        # 5/25 rule (Bernstein): rebalance at ±5pp absolute or 25% relative drift
        breach = abs(drift) >= 5 or (target > 0 and abs(drift) >= 0.25 * target)
        rows.append({
            "key": k, "label": ALLOC_LABELS[k], "value": round(classes[k], 0),
            "pct": pct, "target": target, "model": ALLOC_TARGETS[k], "drift": drift,
            "flag": ("too much" if drift > 0 else "add more") if breach else "ok",
        })
    rows.sort(key=lambda r: -r["value"])
    customized = bool(P.get_setting("alloc_targets"))
    hints = []
    re_row = next(r for r in rows if r["key"] == "real_estate")
    if re_row["pct"] > 65:
        hints.append(f"Real estate is {re_row['pct']}% of wealth — heavy concentration. After the loan is paid off, direct surpluses into liquid assets (VWCE), not more concrete.")
    etf_row = next(r for r in rows if r["key"] == "etf")
    if etf_row["pct"] < 15:
        hints.append(f"Stocks/ETF only {etf_row['pct']}% — the main direction for new contributions (e.g. a broad index ETF such as VWCE) to diversify away from real estate and the employer.")
    rsu_row = next(r for r in rows if r["key"] == "rsu")
    if rsu_row["pct"] > 4:
        hints.append(f"RSU shares {rsu_row['pct']}% — plus future vests. Sell at vest, do not accumulate (risk: salary+bonus+shares in one company).")
    return {"rows": rows, "total": round(total, 0), "hints": hints,
            "targets_customized": customized, "leverage": _leverage(w)}
