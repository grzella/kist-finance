"""Minimal self-contained SQLite layer for the finance app.

Single database at <FINANCE_PROJECT_DIR>/.finance/finance.db. No external
dependencies — replaces the finance-assistant skill's db module so the app
runs standalone. Base tables live here; app-specific tables are created by
planner.ensure_tables().
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def get_finance_dir() -> Path:
    base = os.environ.get("FINANCE_PROJECT_DIR", str(Path.home()))
    d = Path(base) / ".finance"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_db_path() -> Path:
    return get_finance_dir() / "finance.db"


@contextmanager
def get_conn():
    """SQLite connection with WAL + row factory; commits on success, rolls back on error."""
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_BASE_SCHEMA = """
create table if not exists accounts (
  id text primary key, name text not null, type text not null,
  balance real default 0, currency text default 'EUR', institution text, updated_at text not null);
create table if not exists transactions (
  id text primary key, account_id text not null, date text not null, amount real not null,
  type text default 'expense', currency text not null, category text, description text,
  source text default 'manual', payee text, created_at text not null);
create index if not exists idx_transactions_account on transactions(account_id);
create index if not exists idx_transactions_date on transactions(date);
create index if not exists idx_transactions_category on transactions(category);
create index if not exists idx_transactions_type on transactions(type);
create table if not exists budget_categories (
  id integer primary key autoincrement, month text not null, category text not null,
  limit_amount real not null, actual_amount real default 0, currency text default 'EUR',
  unique(month, category));
create index if not exists idx_budget_month on budget_categories(month);
create table if not exists goals (
  id text primary key, name text not null, target_amount real not null, current_amount real default 0,
  target_date text, currency text default 'EUR', status text default 'active',
  created_at text not null, updated_at text not null);
create table if not exists debts (
  id text primary key, name text not null, balance real not null, interest_rate real not null,
  minimum_payment real not null, type text default 'loan', currency text default 'EUR', updated_at text not null);
create table if not exists snapshots (
  id integer primary key autoincrement, type text not null, date text not null, data text not null);
create index if not exists idx_snapshots_type_date on snapshots(type, date);
create table if not exists holdings (
  id text primary key, name text not null, ticker text, asset_class text, quantity real default 0,
  purchase_price real, current_price real, currency text default 'EUR', updated_at text not null);
"""


def init_db() -> None:
    """Create base tables if missing (idempotent)."""
    with get_conn() as conn:
        conn.executescript(_BASE_SCHEMA)
