"""planner — facade over the planner_* modules (split on 2026-09-05).

Every name of the former planner.py is still available here (`planner.wealth_summary()` etc.).
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
  planner_ops         Ops: health / Control Center, data inventory, git, GitHub activity, secrets scan.
  planner_fire        FIRE / work-optional: projection, cone, snapshots and progress tracking.

Monkeypatching in tests: `planner.X` works for calls BETWEEN modules (they go through the proxy);
a call made inside one module is patched in that module (`planner_ops.X`).
"""
import uuid
from datetime import date, datetime
import engine_bridge as eb

from planner_core import (  # noqa: F401
    OWNERS,
    WEALTH_KINDS,
    _now,
    ensure_tables,
    _audit,
    audit_log,
    get_setting,
    set_settings,
    _PROTECTED_SETTINGS,
    set_settings_public,
    monthly_surplus,
    settings,
    _num,
    MODULES,
    CORE_VIEWS,
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
    _SUB_CATEGORY_LABELS,
    expense_summary,
    _expense_optimizations,
    wealth_item_history,
)
from planner_goals import (  # noqa: F401
    list_goals,
    _project,
    add_goal,
    update_goal,
    delete_goal,
    _simulate_path,
    _annual_extras,
    goal_scenarios,
)
from planner_career import (  # noqa: F401
    _current_total_monthly,
    list_offers,
    _offers_stats,
    add_offer,
    update_offer,
    delete_offer,
    barometer_config,
    _baro_counts,
    _pct,
    _STREAM_LABEL,
    list_barometer,
    add_barometer_point,
    delete_barometer_point,
)
from planner_debts import (  # noqa: F401
    _amortize,
    _month_key,
    _debt_last_entry,
    _post_month,
    _auto_roll,
    DEBT_META_FIELDS,
    _save_debt_meta,
    _debt_pace,
    list_debts,
    _market_rates,
    _annuity,
    _variable_projection,
    add_debt,
    update_debt,
    overpay_debt,
    delete_debt,
)
from planner_recs import (  # noqa: F401
    EXPECTED_MARKET_RETURN,
    BROKERAGE_HAIRCUT,
    _pct_setting,
    capital_gains_tax_pct,
    expected_return_after_tax,
    essential_monthly,
    liquid_cushion,
    _rec_key,
    _rec_memory,
    REC_OUTCOMES,
    _ensure_rec_log,
    set_rec_outcome,
    rec_review,
    _zl,
    recommendation,
    SINGLE_POSITION_CAP,
    THEME_CAP,
    xtb_recommendation,
)
from planner_business import (  # noqa: F401
    BIZ_KINDS,
    BIZ_CATEGORIES,
    ensure_biz_table,
    biz_summary,
    add_biz_entry,
    delete_biz_entry,
    ACTION_STATUSES,
    ensure_actions_table,
    list_actions,
    add_action,
    update_action,
    delete_action,
    _parse_pyjson,
    business_marketing,
)
from planner_cashflow import (  # noqa: F401
    CF_DEFAULTS,
    _cash_liquid_now,
    cashflow,
    TAX_DEFAULTS,
    tax_summary,
)
from planner_allocation import (  # noqa: F401
    ALLOC_TARGETS,
    ALLOC_LABELS,
    _ALLOC_LEGACY,
    _alloc_class,
    alloc_targets,
    _leverage,
    allocation,
)
from planner_freshness import (  # noqa: F401
    refresh_derived,
    freshness,
    _auto_reminders,
    list_reminders,
    add_reminder,
    update_reminder,
    delete_reminder,
)
from planner_ops import (  # noqa: F401
    _days_since,
    health,
    data_inventory,
    git_status,
    _github_contribution_calendar,
    _commit_streak,
    github_activity,
    security_scan,
)
from planner_fire import (  # noqa: F401
    fire_projection,
    _liquid_now,
    record_fire_snapshot,
    fire_tracking,
)
