"""AI prompt log (observability — a local counterpart to Simon Willison's `llm`).

Every /api/llm/ask lands in the llm_log table: the prompt, the mode, whether RAG
was used, and the answers (local / cloud / synthesis). So you can see what you
ask, what the model answers, and whether the AI actually helps — all kept locally
(.finance, git-ignored). Zero dependencies; we don't pull in `llm` as a package
(ethos: Flask only).
"""
import json
import uuid
from datetime import datetime, timedelta

import engine_bridge as eb


_MIGRATED = False


def ensure_tables():
    eb._exec("""create table if not exists llm_log (
        id text primary key, ts text not null, mode text, prompt text,
        rag_used integer default 0, local_ok integer, local_text text,
        cloud_ok integer, cloud_text text, synthesis_text text, rating integer, lessons text)""")
    # rating: 1 / -1 from the user; lessons: JSON list of the experience refs that were
    # in the context — together they tell whether a learned lesson actually helps
    global _MIGRATED
    if _MIGRATED:
        return
    for col, ddl in (("rating", "integer"), ("lessons", "text")):  # databases from before 10/2026
        try:
            eb._exec(f"alter table llm_log add column {eb._ident(col)} {ddl}")
        except Exception:
            pass
    _MIGRATED = True


def record(prompt, out):
    """Store one question + its answers. Best-effort (never breaks the request).
    Returns the log id (for rating), or None."""
    try:
        ensure_tables()
        local = out.get("local") or {}
        cloud = out.get("cloud") or {}
        syn = out.get("synthesis") or {}
        lessons = [s.get("ref", "") for s in (out.get("sources") or []) if s.get("source") == "experience"]
        lid = uuid.uuid4().hex
        eb._exec(
            "insert into llm_log (id, ts, mode, prompt, rag_used, local_ok, local_text, "
            "cloud_ok, cloud_text, synthesis_text, lessons) values (?,?,?,?,?,?,?,?,?,?,?)",
            (lid, datetime.now().isoformat(timespec="seconds"),
             out.get("mode"), (prompt or "")[:2000], 1 if out.get("rag_used") else 0,
             1 if local.get("ok") else 0, (local.get("text") or "")[:4000],
             1 if cloud.get("ok") else 0, (cloud.get("text") or "")[:4000],
             (syn.get("text") or "")[:4000], json.dumps(lessons) if lessons else None))
        return lid
    except Exception:
        return None


def rate(lid, rating):
    """👍 (1) / 👎 (-1) / clear (0) on one logged answer."""
    ensure_tables()
    r = int(rating)
    if r not in (-1, 0, 1):
        raise ValueError("rating must be -1, 0 or 1")
    eb._exec("update llm_log set rating=? where id=?", (r or None, str(lid)))


def lesson_stats():
    """{lesson ref: {used, up, down}} — how often each lesson was in the context and how
    the answers it shaped were rated."""
    out = {}
    try:
        ensure_tables()
        for row in eb._rows("select lessons, rating from llm_log where lessons is not null"):
            for ref in json.loads(row["lessons"] or "[]"):
                s = out.setdefault(ref, {"used": 0, "up": 0, "down": 0})
                s["used"] += 1
                s["up"] += row["rating"] == 1
                s["down"] += row["rating"] == -1
    except Exception:
        pass
    return out


def recent(n=25):
    try:
        ensure_tables()
        return eb._rows(
            "select id, ts, mode, prompt, rag_used, local_ok, local_text, cloud_ok, "
            "cloud_text, synthesis_text, rating from llm_log order by ts desc limit ?", (int(n),))
    except Exception:
        return []


def stats(recent_days=30):
    """Counts for the log summary and the ratings step (unrated = last `recent_days`)."""
    since = (datetime.now() - timedelta(days=recent_days)).isoformat(timespec="seconds")
    try:
        ensure_tables()
        r = eb._rows("select count(*) c, coalesce(sum(rag_used),0) rg, coalesce(sum(cloud_ok),0) cl, "
                     "coalesce(sum(rating is not null),0) rated, coalesce(sum(rating=1),0) up, "
                     "coalesce(sum(rating=-1),0) down, coalesce(sum(rating is null and ts >= ?),0) unrated "
                     "from llm_log", (since,))[0]
        return {"total": r["c"], "rag_grounded": r["rg"], "cloud_calls": r["cl"], "rated": r["rated"],
                "up": r["up"], "down": r["down"], "unrated_recent": r["unrated"]}
    except Exception:
        return {"total": 0, "rag_grounded": 0, "cloud_calls": 0, "rated": 0, "up": 0, "down": 0, "unrated_recent": 0}
