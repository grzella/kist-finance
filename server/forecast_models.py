"""Forecasting: a shared model engine (pure stdlib, no numpy).

Grounded in research (2026-07, full report: analysis_forecast_models):
- SHORT horizon (1 day–3 months): the direction of a single stock/FX rate can
  NOT be reliably predicted (Meese-Rogoff for FX; ~52% directional accuracy for
  ML stock models ≈ a coin flip). VOLATILITY is predictable (clustering) — so we
  forecast BANDS (ranges), not direction: EWMA λ=0.94 (RiskMetrics) cross-checked
  against empirical quantiles of real N-day moves (catches fat tails EWMA misses).
  The band is the wider of the two. Self-grading: p10–p90 coverage (target ~80%).
- LONG horizon: see long_term_* below (block bootstrap / scenarios).
"""
import math
from statistics import NormalDist

_ND = NormalDist()


# ---------------------------------------------------------------- short term

def log_returns(closes):
    out = []
    for a, b in zip(closes, closes[1:]):
        if a and b and a > 0 and b > 0:
            out.append(math.log(b / a))
    return out


def ewma_vol_daily(returns, lam=0.94):
    """EWMA (RiskMetrics λ=0.94) daily sigma from daily log-returns."""
    if not returns:
        return None
    var = returns[0] ** 2
    for r in returns[1:]:
        var = lam * var + (1 - lam) * r * r
    return math.sqrt(var)


def _quantile(sorted_vals, q):
    if not sorted_vals:
        return None
    idx = q * (len(sorted_vals) - 1)
    lo = int(math.floor(idx)); hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def empirical_nday_quantiles(closes, n, qs=(0.10, 0.50, 0.90)):
    """Quantiles of REAL n-session log-moves (overlapping windows)."""
    moves = []
    for i in range(len(closes) - n):
        a, b = closes[i], closes[i + n]
        if a and b and a > 0 and b > 0:
            moves.append(math.log(b / a))
    if len(moves) < 30:
        return None
    moves.sort()
    return {q: _quantile(moves, q) for q in qs}


def short_term_bands(closes, horizons=(5, 21, 63)):
    """Pasma cen p10/p50/p90 na N sesji: EWMA vs empiryczne kwantyle,
    per quantile we take the wider (conservative) one. Also returns metadata
    for a one-sentence explanation in the UI."""
    if not closes or len(closes) < 60:
        return None
    last = closes[-1]
    rets = log_returns(closes)
    sig = ewma_vol_daily(rets)
    if not sig:
        return None
    z10 = _ND.inv_cdf(0.10)  # ≈ -1.2816
    z90 = _ND.inv_cdf(0.90)
    out = {"last_close": round(last, 4), "ewma_vol_daily_pct": round(sig * 100, 2),
           "ewma_vol_annual_pct": round(sig * math.sqrt(252) * 100, 1), "horizons": []}
    for n in horizons:
        s_n = sig * math.sqrt(n)
        para = {0.10: z10 * s_n, 0.50: 0.0, 0.90: z90 * s_n}
        emp = empirical_nday_quantiles(closes, n) or {}
        merged = {}
        for q in (0.10, 0.50, 0.90):
            e = emp.get(q)
            p = para[q]
            if q == 0.50:
                merged[q] = e if e is not None else 0.0
            elif e is None:
                merged[q] = p
            else:
                # wider band: further from zero toward the given tail
                merged[q] = min(e, p) if q < 0.5 else max(e, p)
        para_only = emp == {}
        out["horizons"].append({
            "days": n,
            "p10": round(last * math.exp(merged[0.10]), 4),
            "p50": round(last * math.exp(merged[0.50]), 4),
            "p90": round(last * math.exp(merged[0.90]), 4),
            "source": "ewma" if para_only else "ewma+empirical(wider quantiles)",
        })
    return out


def short_term_coverage_backtest(closes, n=21, min_obs=60):
    """Walk-forward self-grading of bands: how often the real price after n
    sessions fell inside p10–p90 computed from data available on that day.
    Cel ~80% (pasmo 80-procentowe)."""
    if len(closes) < 120 + n:
        return None
    inside = total = 0
    start = 100
    step = max(1, (len(closes) - n - start) // 120)  # at most ~120 measurement points
    z10, z90 = _ND.inv_cdf(0.10), _ND.inv_cdf(0.90)
    for i in range(start, len(closes) - n, step):
        window = closes[:i + 1]
        rets = log_returns(window[-260:])
        sig = ewma_vol_daily(rets)
        if not sig:
            continue
        s_n = sig * math.sqrt(n)
        emp = empirical_nday_quantiles(window, n) or {}
        lo = min(emp.get(0.10, z10 * s_n), z10 * s_n)
        hi = max(emp.get(0.90, z90 * s_n), z90 * s_n)
        realized = math.log(closes[i + n] / closes[i])
        total += 1
        if lo <= realized <= hi:
            inside += 1
    if total < min_obs:
        return None
    return {"horizon_days": n, "observations": total,
            "band_coverage_pct": round(inside / total * 100, 1), "target_pct": 80}


# ---------------------------------------------------------------- long term

def block_bootstrap_annual(monthly_returns, years, sims=1000, block=24, seed=42):
    """Block bootstrap (~24-month blocks preserve autocorrelation; Cogneau-Zakamouline) on REAL
    monthly returns. Returns percentiles of the ending balance multiplier.
    With no data, fall back to deterministic scenarios (fire_projection)."""
    import random
    if not monthly_returns or len(monthly_returns) < block * 2:
        return None
    rng = random.Random(seed)
    months = years * 12
    finals = []
    for _ in range(sims):
        bal = 1.0
        m = 0
        while m < months:
            start = rng.randrange(0, len(monthly_returns) - block)
            for r in monthly_returns[start:start + block]:
                bal *= (1 + r)
                m += 1
                if m >= months:
                    break
        finals.append(bal)
    finals.sort()
    return {"years": years, "sims": sims, "block_months": block,
            "p10": round(_quantile(finals, 0.10), 3),
            "p50": round(_quantile(finals, 0.50), 3),
            "p90": round(_quantile(finals, 0.90), 3)}


def goal_eta_band(remaining, pace, pace_wobble=0.25):
    """Goal-ETA uncertainty: pace ±25% (empirical volatility of monthly surpluses).
    Returns (months_optimistic, base, pessimistic)."""
    if not pace or pace <= 0 or remaining is None or remaining <= 0:
        return None
    base = remaining / pace
    return {"months_fast": round(remaining / (pace * (1 + pace_wobble)), 1),
            "months_base": round(base, 1),
            "months_slow": round(remaining / (pace * (1 - pace_wobble)), 1),
            "wobble_pct": int(pace_wobble * 100)}


# ---------------------------------------------------------------- samouczenie
# Kalibracja konformalna: pasma budowane z EMPIRYCZNYCH kwantyli znormalizowanych
# a model's own past errors (z = real log-move / predicted sigma_n). When a model
# systematically underestimates a ticker's volatility, its bands widen by
# themselves — no LLM, pure statistics (conformal prediction).

def conformal_quantiles(residuals_z, min_n=40):
    """10/90 quantiles of normalized historical forecast errors.
    None when there's too little data (then the engine uses theory + price quantiles)."""
    if not residuals_z or len(residuals_z) < min_n:
        return None
    zs = sorted(residuals_z)
    return {"z10": _quantile(zs, 0.10), "z90": _quantile(zs, 0.90), "n": len(zs)}


def short_term_bands_calibrated(closes, residuals_by_h=None, horizons=(5, 21, 63)):
    """Like short_term_bands, but if we have ≥40 settled own-forecasts for a
    horizon, the band quantiles come from OUR errors (self-learning)."""
    base = short_term_bands(closes, horizons)
    if not base:
        return None
    last = base["last_close"]
    sig = base["ewma_vol_daily_pct"] / 100.0
    for h in base["horizons"]:
        cq = conformal_quantiles((residuals_by_h or {}).get(h["days"]))
        if cq:
            s_n = sig * math.sqrt(h["days"])
            h["p10"] = round(last * math.exp(cq["z10"] * s_n), 4)
            h["p90"] = round(last * math.exp(cq["z90"] * s_n), 4)
            h["source"] = f"self-calibrated ({cq['n']} scored own forecasts)"
            h["calibrated"] = True
    return base
