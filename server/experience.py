"""Experience distillation — self-evolution without retraining (AI Agents in
Depth, ch. 8).

After a good AI answer, the model compresses the question + answer into ONE
short, *transferable* lesson (method, pitfall, rule of thumb) stored in
`agent_experiences`. rag._gather() picks these up, so they get embedded and
retrieved like any other context and are injected as guidance on future similar
questions — the agent gets better without touching a single model weight.

Storing is user-triggered (a "learn from this" click in the prompt log): the
human gate the book insists on, because "not every trajectory deserves to become
experience" — only lessons that transfer. Bad ones are prunable (a DELETE), so
faulty guidance can't accumulate. Everything stays local (.finance, git-ignored).
"""
import uuid
from datetime import datetime

import engine_bridge as eb

_DISTILL = (
    "You are turning a solved personal-finance Q&A into a REUSABLE lesson for a "
    "future assistant. Write ONE short note (2-3 sentences) capturing only the "
    "TRANSFERABLE method: what to check, the pitfall to avoid, the rule of thumb. "
    "Do NOT repeat this user's specific numbers or names — only the generalizable "
    "lesson. If there is no transferable lesson worth keeping, reply with exactly: "
    "NONE.\n\nQUESTION:\n{q}\n\nANSWER:\n{a}"
)


def ensure_tables():
    eb._exec("""create table if not exists agent_experiences (
        id text primary key, question text not null, lesson text not null,
        created_at text not null)""")


def distill(question, answer):
    """Compress a Q+A into a transferable lesson, or None when there isn't one
    (or the AI is offline). Prefers Claude in 'both' mode, else the local model."""
    if not (question and answer):
        return None
    import planner
    prompt = _DISTILL.format(q=str(question)[:1500], a=str(answer)[:3000])
    text = None
    if (planner.get_setting("ai_mode") or "local") == "both":
        try:
            import llm_cloud
            text = llm_cloud.chat(prompt, max_tokens=300)
        except Exception:
            text = None
    if not text:
        try:
            import llm_local
            text = llm_local.chat(prompt, max_tokens=300, think=False)
        except Exception:
            text = None
    if not text:
        return None
    text = text.strip()
    # honor the transferability gate: skip empty / refusals / too-short noise
    if len(text) < 15 or text.upper().startswith("NONE"):
        return None
    return text[:1000]


def save(question, lesson):
    ensure_tables()
    eid = uuid.uuid4().hex
    eb._exec("insert into agent_experiences (id, question, lesson, created_at) "
             "values (?,?,?,?)",
             (eid, str(question or "")[:500], lesson[:1000],
              datetime.now().isoformat(timespec="seconds")))
    _mark_stale()
    return eid


def learn(question, answer):
    """Distill + save in one step. Returns the stored lesson, or None."""
    lesson = distill(question, answer)
    if not lesson:
        return None
    save(question, lesson)
    return lesson


def listing(n=100):
    try:
        ensure_tables()
        return eb._rows("select id, question, lesson, created_at from "
                        "agent_experiences order by created_at desc limit ?", (int(n),))
    except Exception:
        return []


def delete(eid):
    ensure_tables()
    eb._exec("delete from agent_experiences where id = ?", (eid,))
    _mark_stale()


def _mark_stale():
    """A change to the experience set → re-embed before the next AI answer so it
    reflects the new/removed lesson (the RAG index rebuilds on the next ask)."""
    try:
        import planner
        planner.set_settings({"rag_dirty": "1"})
    except Exception:
        pass
