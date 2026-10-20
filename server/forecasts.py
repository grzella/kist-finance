"""Self-contained forecast math. Mortgage overpayment (annuity) — pure stdlib."""
import math


def mortgage_overpayment(payload):
    """Compare current mortgage vs one-time overpayment (term shortening)."""
    balance = float(payload["balance"])
    monthly_payment = float(payload["monthly_payment"])
    months_left = int(payload["months_left"])
    overpayment = float(payload.get("overpayment", 0))

    # implied monthly rate via bisection
    lo, hi = 0.00001, 0.02
    for _ in range(100):
        r = (lo + hi) / 2
        calc = balance * r / (1 - (1 + r) ** -months_left)
        if calc > monthly_payment:
            hi = r
        else:
            lo = r
    r = (lo + hi) / 2

    total_now = monthly_payment * months_left
    p2 = balance - overpayment
    if p2 <= 0:
        return {"error": "overpayment >= balance"}
    n2 = -math.log(1 - p2 * r / monthly_payment) / math.log(1 + r)
    total_after = monthly_payment * n2 + overpayment
    return {
        "implied_annual_rate_pct": round(r * 12 * 100, 2),
        "months_left_now": months_left,
        "months_left_after": round(n2, 1),
        "months_saved": round(months_left - n2, 1),
        "years_saved": round((months_left - n2) / 12, 2),
        "interest_now": round(total_now - balance, 0),
        "interest_saved": round(total_now - total_after, 0),
    }
