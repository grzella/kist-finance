"""Security regressions for the AI tool-calling layer (db_tools.run_select).

Surface: the local model can emit SQL through the `query_db` tool. The guard
must (1) allow only a single SELECT/WITH, (2) enforce read-only at the SQLite
level and (3) BOUND QUERY TIME — `sqlite3 timeout` is only a busy-timeout on
locks, not a compute limit. Without (3) a model steered by injected content
(RAG/market text) could freeze the Flask worker with a heavy cartesian
aggregate. Ported from the twin instance.

Tests run on the throwaway DB from conftest (data_dir) — real data untouched.
"""
import time

import pytest


@pytest.fixture()
def dbt(data_dir):
    import config
    config.setup()
    import db_tools
    return db_tools


def test_writes_and_ddl_rejected(dbt):
    for sql in ("delete from goals", "drop table goals",
                "update settings set value='x'", "insert into goals(name) values('x')",
                "pragma table_info(goals)", "attach database '/tmp/e.db' as e",
                "SeLeCt 1; DeLeTe FROM goals", "with x as (select 1) delete from goals"):
        assert dbt.run_select(sql).get("ok") is not True, f"guard let through: {sql!r}"


def test_multi_statement_rejected(dbt):
    assert dbt.run_select("select 1; drop table goals").get("ok") is not True


def test_plain_select_works(dbt):
    r = dbt.run_select("select 1 as x")
    assert r.get("ok") and r["rows"][0]["x"] == 1


def test_connection_is_read_only(dbt):
    con = dbt._connect()
    try:
        with pytest.raises(Exception):
            con.execute("create table _probe(x)")
    finally:
        con.close()


def test_heavy_query_is_time_bounded(dbt):
    """An unbounded cartesian aggregate must be aborted after ~QUERY_SECONDS
    instead of computing forever (DoS of the single worker)."""
    sql = ("with r(n) as (select 1 union all select n+1 from r limit 400) "
           "select count(*) from r a, r b, r c, r d")
    t = time.monotonic()
    r = dbt.run_select(sql)
    elapsed = time.monotonic() - t
    assert elapsed < dbt.QUERY_SECONDS + 2.0, f"query was not aborted ({elapsed:.1f}s)"
    assert r.get("ok") is not True or elapsed < dbt.QUERY_SECONDS
