"""Read-only SQL access for the local AI (tool calling).

Lets the local model CHECK real numbers in the user's database instead of
guessing from RAG excerpts. Defense in depth: the connection is opened
read-only at the SQLite level (file:...?mode=ro), on top of that only a single
SELECT/WITH statement passes validation, and results are capped at MAX_ROWS.
Every tool round-trip ends up in the prompt log like any other AI call.
"""
import json
import re
import sqlite3
import time

import db as _db

MAX_ROWS = 40
# Wall-clock budget for ONE SELECT. `sqlite3(timeout=...)` is only a busy-timeout
# on LOCKS — it does NOT bound query compute time. Without this, the model (e.g.
# steered by content injected via RAG/market text) could emit an unbounded
# cartesian product / aggregate and freeze the single Flask worker.
QUERY_SECONDS = 3.0
# progress handler fires every N SQLite VM instructions; non-zero return aborts
_PROGRESS_OPS = 10000

_FORBID = re.compile(
    r"(?i)(^|[^a-z0-9_])(insert|update|delete|drop|alter|create|attach|detach"
    r"|pragma|vacuum|reindex|replace|begin|commit)($|[^a-z0-9_])")


def _connect():
    path = _db.get_finance_dir() / "finance.db"
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
    con.row_factory = sqlite3.Row
    return con


def schema_summary(max_cols=14):
    """Compact 'table(col, col…)' map handed to the model in the tool description."""
    try:
        con = _connect()
        tables = [r[0] for r in con.execute(
            "select name from sqlite_master where type='table' "
            "and name not like 'sqlite_%' order by name")]
        parts = []
        for t in tables:
            cols = [r[1] for r in con.execute(f"pragma table_info({t})")][:max_cols]
            parts.append(f"{t}({', '.join(cols)})")
        con.close()
        return "; ".join(parts)
    except Exception:
        return ""


def run_select(sql=""):
    """Execute ONE SELECT and return rows as dicts; any violation → error dict."""
    q = (sql or "").strip().rstrip(";").strip()
    if not re.match(r"(?i)^(select|with)\b", q):
        return {"ok": False, "error": "only a single SELECT (or WITH…SELECT) is allowed"}
    if ";" in q:
        return {"ok": False, "error": "multiple statements are not allowed"}
    if _FORBID.search(q):
        return {"ok": False, "error": "write/DDL keywords are not allowed"}
    try:
        con = _connect()
        deadline = time.monotonic() + QUERY_SECONDS
        # abort the query once it exceeds the time budget (guards against a DoS
        # via a heavy JOIN/aggregate, which fetchmany() does not bound)
        con.set_progress_handler(
            lambda: 1 if time.monotonic() > deadline else 0, _PROGRESS_OPS)
        try:
            rows = [dict(r) for r in con.execute(q).fetchmany(MAX_ROWS)]
        finally:
            con.set_progress_handler(None, 0)
            con.close()
        return {"ok": True, "rows": rows, "truncated": len(rows) == MAX_ROWS}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def ask_local(ask, system):
    """Local model with the read-only `query_db` tool; plain chat when the server has no
    tool support or the tool run yields nothing. Returns (text, via_tools, tool_results).
    Shared by the app and the local eval, so the eval measures the answer the user sees."""
    import llm_local
    try:
        sch = schema_summary()
        if sch:
            tools = [{"type": "function", "function": {
                "name": "query_db",
                "description": "Run ONE read-only SQL SELECT against the user's "
                               "local finance database (SQLite) to check real "
                               "numbers before answering. Tables: " + sch,
                "parameters": {"type": "object", "required": ["sql"],
                               "properties": {"sql": {"type": "string", "description": "a single SELECT statement"}}}}}]
            seen = []
            def query_db(sql=""):
                res = run_select(sql)
                seen.append(json.dumps(res, ensure_ascii=False, default=str))
                return res
            lt = llm_local.chat_with_tools(ask, tools, {"query_db": query_db}, system=system)
            if lt is not None:
                return lt, True, "\n".join(seen)
    except Exception:
        pass
    return llm_local.chat(ask, system=system, think=False), False, ""


_NUM = re.compile(r"\d+(?:[ \u00a0.,]\d+)*")


def _digits(tok):
    return re.sub(r"\D", "", tok).strip("0")


def unsourced_numbers(answer, evidence):
    """Numbers in the answer that appear nowhere in the evidence (context, question, SQL
    results): computed, rounded or invented. Compared as digit strings, so "1 280,00"
    matches "1280.0" in either locale; only numbers with 3+ digits or a fraction count."""
    have = {_digits(t) for t in _NUM.findall(evidence or "")}
    out = []
    for tok in _NUM.findall(answer or ""):
        d = _digits(tok)
        if (len(d) >= 3 or re.search(r"[.,]\d", tok)) and d and d not in have and tok not in out:
            out.append(tok)
    return out
