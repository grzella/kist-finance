#!/usr/bin/env python3
"""Seed a FRESH database with obviously-fake sample data so a new clone
shows a working app. Refuses to run if data already exists (protects real data).

Usage:  python3 seed.py [--force]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "server"))
import config  # noqa: E402
config.setup()
import db  # noqa: E402
import engine_bridge as eb  # noqa: E402
import planner  # noqa: E402
import market  # noqa: E402

db.init_db()          # base tables (accounts, transactions, goals, debts…)
planner.ensure_tables()

existing = eb._rows("select count(*) c from wealth_items")
if existing and existing[0]["c"] > 0 and "--force" not in sys.argv:
    print("DB already has data — skipping seed. Use --force to add sample data anyway.")
    sys.exit(0)

print("Seeding sample data (fake persona: Alex Demo)…")

# --- settings ---
planner.set_settings({
    "monthly_savings": 6000,
    "annual_bonus_net": 40000,
    "tax_salary_gross_annual": 240000,
    "tax_rental_monthly": 2500,
    "cf_monthly_surplus": 6000,
    "cf_safety_buffer": 30000,
    "cf_liquid_start": 40000,
    "fixed_costs": '{"total_mine": 9000, "essential_mine": 7000, "items": ['
                   '{"name": "Mortgage (Sample City)", "monthly": 3500, "payer": "me", "essential": true},'
                   '{"name": "Groceries", "monthly": 1500, "payer": "me", "essential": true},'
                   '{"name": "Utilities", "monthly": 900, "payer": "me", "essential": true},'
                   '{"name": "Transport", "monthly": 700, "payer": "me", "essential": true},'
                   '{"name": "Insurance", "monthly": 400, "payer": "me", "essential": true},'
                   '{"name": "Subscriptions", "monthly": 300, "payer": "me", "essential": false},'
                   '{"name": "Fun / misc", "monthly": 700, "payer": "me", "essential": false},'
                   '{"name": "Auto-invest (ETF)", "monthly": 1000, "payer": "me", "essential": false}]}',
})

# --- debt (sample mortgage) ---
debt_id = planner.add_debt({
    "name": "Mortgage — Sample City apartment",
    "balance": 320000, "interest_rate": 6.5, "minimum_payment": 3500, "type": "mortgage",
})

# --- wealth items ---
planner.add_wealth_item({"name": "Cash (checking)", "kind": "cushion", "owner": "me", "value": 25000})
planner.add_wealth_item({"name": "Emergency savings", "kind": "cushion", "owner": "me", "value": 30000})
planner.add_wealth_item({"name": "ETF portfolio (broker)", "kind": "investment", "owner": "me", "value": 85000})
planner.add_wealth_item({"name": "Company shares (RSU)", "kind": "investment", "owner": "me", "value": 60000})
planner.add_wealth_item({"name": "Pension account", "kind": "investment", "owner": "me", "value": 45000})
planner.add_wealth_item({"name": "Salary (net, monthly)", "kind": "income", "owner": "me", "value": 14000})
planner.add_wealth_item({
    "name": "Apartment — Sample City", "kind": "investment", "owner": "me",
    "value": 620000, "linked_debt_id": debt_id})

# --- goals ---
planner.add_goal({"name": "House abroad — 50% deposit", "target_amount": 400000,
                  "current_amount": 0, "monthly_contribution": None})
planner.add_goal({"name": "Work-optional — 1.5M liquid portfolio", "target_amount": 1500000,
                  "current_amount": 190000, "monthly_contribution": None})

# --- offers (sample inbound) ---
planner.add_offer({"company": "Acme Corp", "role": "Engineering Manager", "total_monthly": 42000,
                   "work_model": "hybrid", "status": "new", "received_at": "2026-05-10",
                   "notes": "Sample offer — demo data.", "tier": 2})
planner.add_offer({"company": "Globex", "role": "Senior Engineering Manager", "total_monthly": 55000,
                   "work_model": "remote", "status": "interviewing", "received_at": "2026-06-18",
                   "notes": "Sample offer — demo data.", "tier": 1})

# --- RSU grant (sample) ---
market.update_rsu({"ticker": "AAPL", "grant_value_usd": 100000, "shares_held": 200,
                   "shares_next_vest": 100})

print("✅ Sample data seeded. Start the app:  ./run.sh")
print("   Tip: toggle demo mode in Control Center to mask all figures.")
