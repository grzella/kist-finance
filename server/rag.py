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
import json
import math
import re
import uuid
from datetime import datetime

import engine_bridge as eb

# hybrid weighting: how much semantic (cosine) vs lexical (BM25) in the blend
_SEMANTIC_WEIGHT = 0.5

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
    # semantic RAG: an optional per-chunk embedding (JSON array, L2-normalized)
    try:
        eb._exec("alter table rag_chunks add column embedding text")
    except Exception:
        pass  # column already exists


def _tok(s):
    return [t for t in _TOKEN.findall((s or "").lower()) if len(t) >= 2 and t not in _STOP]


def _normalize(vec):
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / n for x in vec]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


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
    """Rebuild the index from scratch. Returns the number of chunks.

    If a local embedding server is reachable, each chunk is embedded (stored
    L2-normalized) so search can run the semantic + lexical hybrid. If not,
    chunks are stored without embeddings and search stays pure BM25."""
    import llm_local
    ensure_tables()
    eb._exec("delete from rag_chunks")
    use_emb = llm_local.embed("probe") is not None   # one probe, not per-chunk
    now = datetime.now().isoformat(timespec="seconds")
    n = 0
    for source, ref, text in _gather():
        emb = None
        if use_emb:
            vec = llm_local.embed(text)
            if vec:
                emb = json.dumps(_normalize(vec))
        eb._exec("insert into rag_chunks (id, source, ref, text, created_at, embedding) "
                 "values (?,?,?,?,?,?)",
                 (uuid.uuid4().hex, source, ref, text, now, emb))
        n += 1
    return n


def _bm25_scores(query, rows):
    """{row_index: bm25} for rows whose text lexically overlaps the query."""
    q = set(_tok(query))
    if not q:
        return {}
    docs = [_tok(r["text"]) for r in rows]
    N = len(docs)
    avgdl = sum(len(d) for d in docs) / N or 1
    df = {}
    for toks in docs:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    k1, b = 1.5, 0.75
    out = {}
    for i, toks in enumerate(docs):
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
            out[i] = s
    return out


def search(query, k=5):
    """Hybrid ranking: BM25 (lexical) blended with cosine similarity of query and
    chunk embeddings (semantic), when embeddings are present. Degrades to pure
    BM25 when no chunk has an embedding. Returns [{source, ref, text, score}]."""
    if not query or not query.strip():
        return []
    try:
        rows = eb._rows("select source, ref, text, embedding from rag_chunks")
    except Exception:
        return []
    if not rows:
        return []

    bm = _bm25_scores(query, rows)                      # index -> bm25
    has_emb = any(r.get("embedding") for r in rows)
    cos = {}
    if has_emb:
        import llm_local
        qv = llm_local.embed(query)
        if qv:
            qn = _normalize(qv)
            for i, r in enumerate(rows):
                if r.get("embedding"):
                    try:
                        cos[i] = max(0.0, _dot(qn, json.loads(r["embedding"])))
                    except Exception:
                        pass

    if not bm and not cos:
        return []
    bm_max = max(bm.values()) if bm else 0.0
    cos_max = max(cos.values()) if cos else 0.0
    w = _SEMANTIC_WEIGHT if cos else 0.0                 # no semantic → pure lexical
    scored = []
    for i in set(bm) | set(cos):
        bn = (bm.get(i, 0.0) / bm_max) if bm_max else 0.0
        cn = (cos.get(i, 0.0) / cos_max) if cos_max else 0.0
        score = (1 - w) * bn + w * cn
        if score > 0:
            scored.append((score, rows[i]))
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
    n, emb = 0, 0
    try:
        n = eb._rows("select count(*) c from rag_chunks")[0]["c"]
        emb = eb._rows("select count(*) c from rag_chunks where embedding is not null")[0]["c"]
    except Exception:
        pass
    engine = "BM25 + semantic (hybrid)" if emb else "BM25 (lexical, offline)"
    if not n:
        hint = "click “Reindex” in Control to build the index from your data"
    elif not emb:
        hint = ("lexical only — run an embedding server (LOCAL_EMBED_URL) and Reindex "
                "to enable semantic search")
    else:
        hint = ""
    return {"available": True, "engine": engine, "chunks": n, "embedded": emb, "hint": hint}
