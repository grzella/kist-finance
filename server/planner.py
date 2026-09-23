"""planner — facade over the planner_* modules (split on 2026-09-05).

Re-exports only the names someone reaches as `planner.X` / `P.X` (`planner.wealth_summary()` etc.);
a helper used inside one module is imported from that module.
The code lives in:
  planner_core        Core: app tables, settings, audit log, shared helpers (_num, _now, _zl).
  planner_wealth      Wealth: items and values, live pricing, trend, monthly net-worth snapshot.
  planner_expenses    Fixed expenses: per-month items (carry-forward), currencies, cost hints.
  planner_goals       Goals: projection, ETA, extra inflows (bonus/vests), goal-path scenarios.
  planner_career      Career: job offers (stats vs current), job-market barometer.
  planner_debts       Loans: amortisation, meta, payoff pace, variable-rate projection, overpayments.
  planner_recs        Recommendation engine with memory and outcomes, cushion, essential costs, brokerage portfolio.
  planner_business    Side business: revenue/cost ledger, action plan, marketing (Supabase).
  planner_cashflow    Cash-flow: net liquidity timeline, tax summary.
  planner_allocation  Asset allocation: classes, targets, 5/25 drift, leverage.
  planner_freshness   Data freshness: update bar, reminders (auto + manual), recompute derived.
  planner_ops         Ops: health / Control Center, data inventory, git, GitHub activity.
  planner_fire        FIRE / work-optional: projection, cone, snapshots and progress tracking.

Monkeypatching in tests: `planner.X` works for calls BETWEEN modules (they go through the proxy);
a call made inside one module is patched in that module (`planner_ops.X`).
"""
from planner_core import (  # noqa: F401
    WEALTH_KINDS,
    _now,
    ensure_tables,
    _audit,
    audit_log,
    get_setting,
    get_json_setting,
    set_settings,
    set_settings_public,
    monthly_surplus,
    settings,
    _num,
    get_app_config,
    save_app_config,
    _months_between,
)
from planner_wealth import (  # noqa: F401
    wealth_summary,
    add_wealth_item,
    update_wealth_item,
    delete_wealth_item,
    add_wealth_value,
    ensure_monthly_snapshot,
)
from planner_expenses import (  # noqa: F401
    add_expense_item,
    update_expense_item,
    delete_expense_item,
    set_expense_value,
    expense_item_history,
    expense_summary,
    wealth_item_history,
)
from planner_goals import (  # noqa: F401
    list_goals,
    add_goal,
    update_goal,
    delete_goal,
    _simulate_path,
    _annual_extras,
    goal_scenarios,
)
from planner_career import (  # noqa: F401
    list_offers,
    add_offer,
    update_offer,
    delete_offer,
    barometer_config,
    list_barometer,
    add_barometer_point,
    delete_barometer_point,
)
from planner_debts import (  # noqa: F401
    list_debts,
    _market_rates,
    add_debt,
    update_debt,
    overpay_debt,
    delete_debt,
)
from planner_recs import (  # noqa: F401
    EXPECTED_MARKET_RETURN,
    _pct_setting,
    capital_gains_tax_pct,
    expected_return_after_tax,
    essential_monthly,
    liquid_cushion,
    set_rec_outcome,
    rec_review,
    _zl,
    recommendation,
    xtb_recommendation,
)
from planner_business import (  # noqa: F401
    biz_summary,
    add_biz_entry,
    delete_biz_entry,
    list_actions,
    add_action,
    update_action,
    delete_action,
    business_marketing,
)
from planner_cashflow import (  # noqa: F401
    CF_DEFAULTS,
    cashflow,
    tax_summary,
)
from planner_allocation import (  # noqa: F401
    _alloc_class,
    allocation,
)
from planner_freshness import (  # noqa: F401
    refresh_derived,
    freshness,
    list_reminders,
    add_reminder,
    update_reminder,
    delete_reminder,
)
from planner_ops import (  # noqa: F401
    health,
    data_inventory,
    git_status,
    _commit_streak,
    github_activity,
)
from planner_fire import (  # noqa: F401
    fire_projection,
    record_fire_snapshot,
)
