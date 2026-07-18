"""AI prompt log (observability — a local counterpart to Simon Willison's `llm`).

Every /api/llm/ask lands in the llm_log table: the prompt, the mode, whether RAG
was used, and the answers (local / cloud / synthesis). So you can see what you
ask, what the model answers, and whether the AI actually helps — all kept locally
(.finance, git-ignored). Zero dependencies; we don't pull in `llm` as a package
(ethos: Flask only).
"""
import uuid
from datetime import datetime

import engine_bridge as eb


def ensure_tables():
    eb._exec("""create table if not exists llm_log (
        id text primary key, ts text not null, mode text, prompt text,
        rag_used integer default 0, local_ok integer, local_text text,
        cloud_ok integer, cloud_text text, synthesis_text text)""")


def record(prompt, out):
    """Store one question + its answers. Best-effort (never breaks the request)."""
    try:
        ensure_tables()
        local = out.get("local") or {}
        cloud = out.get("cloud") or {}
        syn = out.get("synthesis") or {}
        eb._exec(
            "insert into llm_log (id, ts, mode, prompt, rag_used, local_ok, local_text, "
            "cloud_ok, cloud_text, synthesis_text) values (?,?,?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, datetime.now().isoformat(timespec="seconds"),
             out.get("mode"), (prompt or "")[:2000], 1 if out.get("rag_used") else 0,
             1 if local.get("ok") else 0, (local.get("text") or "")[:4000],
             1 if cloud.get("ok") else 0, (cloud.get("text") or "")[:4000],
             (syn.get("text") or "")[:4000]))
    except Exception:
        pass


def recent(n=25):
    try:
        ensure_tables()
        return eb._rows(
            "select ts, mode, prompt, rag_used, local_ok, local_text, cloud_ok, "
            "cloud_text, synthesis_text from llm_log order by ts desc limit ?", (int(n),))
    except Exception:
        return []


def stats():
    try:
        ensure_tables()
        r = eb._rows("select count(*) c, coalesce(sum(rag_used),0) rg, "
                     "coalesce(sum(cloud_ok),0) cl from llm_log")[0]
        return {"total": r["c"], "rag_grounded": r["rg"], "cloud_calls": r["cl"]}
    except Exception:
        return {"total": 0, "rag_grounded": 0, "cloud_calls": 0}
