"""Local RAG (pure stdlib, zero dependencies) — BM25 lexical search over your data.

No embeddings, no external service, no SQLite extensions: works out of the box
and 100% offline. Indexes the app's own text (goals, wealth items, job offers,
business entries, saved analyses) into rag_chunks, then ranks with BM25 to ground
AI answers in your actual numbers.

Why BM25, not sqlite-vec: macOS ships a stock Python with SQLite extension
loading disabled (no enable_load_extension), and a local llama-server serves no
embeddings without `--embeddings`. Lexical BM25 gives a working, private RAG with
none of that machinery. An embedding backend can be added later.
"""
import math
import re
import uuid
from datetime import datetime

import engine_bridge as eb

_TOKEN = re.compile(r"[0-9a-zA-Ząćęłńóśźż]+")
# short PL/EN stoplist — drops noise, keeps content words
_STOP = set((
    "the a an of to in on for and or is are was were be as at by with from that this it "
    "i w z ze na do od po za o u co to nie tak jest są być oraz albo lub bo że się dla "
    "przez pod nad przy jako czy ale gdy już tez też ten ta to te"
).split())


def ensure_tables():
    eb._exec("""create table if not exists rag_chunks (
        id text primary key, source text not null, ref text default '',
        text text not null, created_at text not null)""")


def _tok(s):
    return [t for t in _TOKEN.findall((s or "").lower()) if len(t) >= 2 and t not in _STOP]


def _gather():
    """Collect (source, ref, text) from the app's own data. Each source is
    wrapped in try/except so a missing table never breaks a reindex."""
    out = []

    def add(source, ref, text):
        text = (text or "").strip()
        if len(text) >= 3:
            out.append((source, str(ref or "")[:120], text[:2000]))

    try:
        for g in eb._rows("select * from goals"):
            name = g.get("name") or g.get("title") or "goal"
            add("goal", name, f"Goal: {name}. {g.get('notes','')} "
                f"target {g.get('target_amount','')} current {g.get('current_amount','')}".strip())
    except Exception:
        pass
    try:
        for w in eb._rows("select * from wealth_items where coalesce(archived,0)=0"):
            add("wealth", w.get("name"), f"Wealth: {w.get('name')} ({w.get('kind','')}) "
                f"{w.get('notes','')}".strip())
    except Exception:
        pass
    try:
        for j in eb._rows("select * from job_offers"):
            add("offer", j.get("company"), f"Job offer: {j.get('company')} — {j.get('role','')}, "
                f"total {j.get('total_monthly','')}/mo. {j.get('notes','')}".strip())
    except Exception:
        pass
    try:
        for b in eb._rows("select * from biz_entries"):
            add("business", b.get("category"), f"Business {b.get('kind','')}: {b.get('category','')} "
                f"{b.get('amount','')} — {b.get('description','')}".strip())
    except Exception:
        pass
    try:
        for s in eb._rows("select key, value from app_settings where key like 'analysis_%'"):
            add("analysis", s.get("key"), f"{s.get('key')}: {s.get('value','')}")
    except Exception:
        pass
    # derived data (computed by planner) — recommendations and reminders
    try:
        import planner
        rec = planner.recommendation()
        recs = (rec.get("items") or rec.get("recs")) if isinstance(rec, dict) else rec
        for r in (recs or []):
            add("recommendation", r.get("area", ""), r.get("text") or r.get("title", ""))
    except Exception:
        pass
    try:
        import planner
        rem = planner.list_reminders()
        for r in ((rem.get("reminders") if isinstance(rem, dict) else rem) or []):
            add("reminder", r.get("title") or r.get("area", ""),
                " ".join(str(r.get(k, "")) for k in ("title", "text", "note", "message") if r.get(k)))
    except Exception:
        pass
    return out


def reindex():
    """Rebuild the index from scratch. Returns the number of chunks."""
    ensure_tables()
    eb._exec("delete from rag_chunks")
    now = datetime.now().isoformat(timespec="seconds")
    n = 0
    for source, ref, text in _gather():
        eb._exec("insert into rag_chunks (id, source, ref, text, created_at) values (?,?,?,?,?)",
                 (uuid.uuid4().hex, source, ref, text, now))
        n += 1
    return n


def search(query, k=5):
    """BM25 ranking. Returns a list of {source, ref, text, score}."""
    q = set(_tok(query))
    if not q:
        return []
    try:
        rows = eb._rows("select source, ref, text from rag_chunks")
    except Exception:
        return []
    if not rows:
        return []
    docs = [(_tok(r["text"]), r) for r in rows]
    N = len(docs)
    avgdl = sum(len(d) for d, _ in docs) / N or 1
    df = {}
    for toks, _ in docs:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    k1, b = 1.5, 0.75
    scored = []
    for toks, r in docs:
        if not toks:
            continue
        tf = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        dl = len(toks)
        s = 0.0
        for t in q:
            if t not in tf:
                continue
            idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * dl / avgdl))
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    return [{"source": r["source"], "ref": r["ref"], "text": r["text"], "score": round(s, 3)}
            for s, r in scored[:k]]


def context_for(query, k=4, max_chars=1400):
    """A context block to inject into an LLM prompt (or '' when nothing matches)."""
    hits = search(query, k=k)
    if not hits:
        return ""
    lines, total = [], 0
    for h in hits:
        line = f"[{h['source']}] {h['text']}"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line)
    return "Context from your own data (use if relevant):\n" + "\n".join(lines)


def status():
    try:
        n = eb._rows("select count(*) c from rag_chunks")[0]["c"]
    except Exception:
        n = 0
    return {"available": True, "engine": "BM25 (stdlib, offline)", "chunks": n,
            "hint": "" if n else "click “Reindex” in Control to build the index from your data"}
