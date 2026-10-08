"""AI improvement: one list of "what is, what runs by itself, what to do" for the app's
whole learning loop (local model, RAG memory, answer ratings, lessons, quality eval,
forecasts, data freshness). Every step is computed from data, nothing is written here.
Each section sits in try/except: a missing table or an offline model must not break the view."""
import json
import os
import shlex
import subprocess
from datetime import datetime
from pathlib import Path

import engine_bridge as eb

EVAL_STALE_DAYS = 30


# Improvement roadmap (research 2026-10-06, five threads plus a red team): ideas with a status,
# not tasks for today. phase: done | 1..4 | P (forecasts) | ⏸ (conditional) | X (rejected); status is derived from it.
ROADMAP = [
    {'id': 'D1', 'phase': 'done', 'title': '👍/👎 ratings attributed to lessons; at most 1 lesson in context; lessons kept to whole sentences', 'why': 'Agent-memory literature: weight lessons by feedback and cap how many enter the prompt', 'where': 'both'},
    {'id': 'D2', 'phase': '2', 'title': 'Tune the semantic weight (default 0.5) on your own gold set', 'why': 'BM25 misses inflected word forms; on an inflected-language set a higher semantic weight lifted facts-in-context to 100%', 'criterion': 'recall@6 up on the gold set, no drop elsewhere', 'hours': 1, 'where': 'both'},
    {'id': 'D3', 'phase': 'done', 'title': 'Scheduled quality eval with recorded results', 'why': 'Reason: model change, 30 days, changed question set', 'where': 'both'},
    {'id': 'D4', 'phase': 'done', 'title': 'Incremental RAG reindex, dirty flag cleared', 'why': 'Seconds instead of minutes, so it can run by itself', 'where': 'both'},
    {'id': 'D5', 'phase': 'done', 'title': 'Band calibration counts independent windows', 'why': 'Daily 21-day forecasts overlap; 100 of them are ~5 outcomes', 'where': 'both'},
    {'id': 'D7', 'phase': 'done', 'title': 'App path: Qwen3 thinking off with tools, quality eval measures the app path, recall in the report, ⚠️ on numbers not found in the data', 'why': 'Thinking ate the 700-token budget (empty or cut-off answers, 31 s per question); the eval measured RAG alone, not what the user saw', 'where': 'both'},
    {'id': 'R1', 'phase': '1', 'title': 'Gold set 16 → 50, then 100 (every 👎 and forecast miss is a candidate; a second frozen set)', 'why': 'With 16 questions the confidence interval is 40 pp wide; 10 pp becomes visible at ~100', 'criterion': '≥50 cases in 8 weeks; recall@6, MRR and 👍-rate per category', 'hours': 1, 'where': 'both'},
    {'id': 'R2', 'phase': '1', 'title': 'Wilson CI + exact McNemar in the harness', 'why': 'A/B verdict only with ≥6 flips one way and 0 back; ~30 stdlib lines', 'criterion': 'every result with an interval', 'hours': 1, 'where': 'eval harness'},
    {'id': 'R3', 'phase': '1', 'title': 'Regression gate: pass→fail blocks; prompt version + changelog', 'why': 'Old and new prompt in the same session and seed', 'criterion': 'baseline diff lists per-case flips', 'hours': 1, 'where': 'both'},
    {'id': 'R4', 'phase': '1', 'title': 'LLM call log: prompt hash and version, tokens, ms, finish_reason, rating, eval_case_id', 'why': '90% of observability needs without a service; OTel GenAI has 0 stable attributes', 'criterion': 'one SQL query: which prompt version produced this 👎', 'hours': 1, 'where': 'both'},
    {'id': 'R5', 'phase': '1', 'title': 'Provenance tags on RAG chunks; assistant-written text excluded from retrieval; days since last full re-embed', 'why': 'Self-citing LLM text collapses answers in 79.6% of simulations (RAG Collapse 2026)', 'criterion': 'assistant chunks in context <10%', 'hours': 2, 'where': 'both'},
    {'id': 'R6', 'phase': '2', 'title': 'Numeric questions go to SQL first, one retry on execution error, schema as CREATE TABLE + FKs + samples', 'why': '73% of table retrieval errors are structural; +4–9 pp from one retry', 'criterion': '≥90% exact match on the numeric subset', 'hours': 3, 'where': 'both'},
    {'id': 'R7', 'phase': '2', 'title': 'Lemmatised BM25 for inflected languages, raw tokens kept', 'why': 'Every Polish benchmark lemmatises; dense beats raw BM25 by ~15 pts', 'criterion': 'BM25-only recall@6 +3 questions / 40', 'hours': 2, 'where': 'inflected languages'},
    {'id': 'R8', 'phase': '2', 'title': 'Headers “type · name · date · status” on chunks + type/date filter', 'why': 'Contextual retrieval: −35..−49% failures; metadata in text = largest gain on FinanceBench', 'criterion': 'MRR up, recall@6 100% on the larger set', 'hours': 2, 'where': 'both'},
    {'id': 'R9', 'phase': '2', 'title': 'Context hygiene for an 8B reader: dedupe, top-4/5, best first and second last, profile <150 tokens, “restate facts first”', 'why': '8B models degrade past ~3k retrieved tokens; recitation recovers 14–85% of the loss', 'criterion': '👍-rate up; median prompt ≤2.5k tokens', 'hours': 2, 'where': 'both'},
    {'id': 'R10', 'phase': '2', 'title': 'Lesson governance: weight (1+👍−👎)×decay, UPDATE instead of ADD, auto-off at net ≤ −2, preview before saving', 'why': 'Stale lessons override corrections; “learn from this” is a memory-poisoning write channel', 'criterion': 'A/B with and without lessons: 👍-rate not worse', 'hours': 3, 'where': 'both'},
    {'id': 'R11', 'phase': 'done', 'title': 'Bump llama.cpp b10050 → ≥b11455', 'why': 'Done 2026-10-07: llama.cpp 0.6.0, same eval score, identical embeddings', 'criterion': 'no regression on the quality eval', 'hours': 1, 'where': 'both'},
    {'id': 'R12', 'phase': '⏸', 'title': 'Server flags: KV cache q8_0/q8_0, flash-attn, parallel 1, byte-stable system prompt', 'why': 'Skipped 10/2026: speed is not the problem, and q8 shifts the logprobs R16 depends on', 'criterion': 'revisit when response times start to hurt', 'hours': 1, 'where': 'both'},
    {'id': 'R13', 'phase': '⏸', 'title': 'Model: Qwen3.5-9B Q6_K (thinking off, per-call budget); gpt-oss-20b as the English alternative', 'why': 'The only eval failure was not the model; the migration cost (lessons, tool calls) is known, the gain is not measurable on 16 questions', 'criterion': 'revisit when a 50-question eval shows ≥3 generation errors (right context, wrong answer), a known wrong answer is the model\'s fault, or response times hurt; rewrite lessons before measuring', 'hours': 3, 'where': 'both'},
    {'id': 'R14', 'phase': '⏸', 'title': 'Embedder for inflected languages: multilingual-e5-large or bge-m3 GGUF', 'why': 'PIRB measures generic retrieval, not "amount for a month"; a swap means a full reindex and retuning the semantic weight', 'criterion': 'only when recall (fact in context) shows more than one retrieval miss on 50 questions; build the index in a separate directory', 'hours': 2, 'where': 'inflected languages'},
    {'id': 'R15', 'phase': '3', 'title': 'reasoning_budget_tokens per call (512–1024 on math) instead of on/off', 'why': 'Budget/accuracy curve is steep to ~512; reasoning raises over-confidence', 'criterion': 'numeric-subset accuracy up, p95 unchanged', 'hours': 1, 'where': 'both'},
    {'id': 'R16', 'phase': '4', 'title': 'decide(state, questions) in the Jev shape: single-token labels + “unknown”, renormalised logits, abstain on the bottom 30–50%', 'why': 'Jev audits: without “unknown” accuracy 0.000, with it 0.950; local, no data leaves', 'criterion': 'selective accuracy at 70% coverage ≥ +10 pp', 'hours': 3, 'where': 'both'},
    {'id': 'R17', 'phase': '4', 'title': 'One-temperature calibration after 100–300 labels', 'why': '2.8–6× better ECE with ranking unchanged', 'criterion': 'ECE ≥2× lower', 'hours': 2, 'where': 'both'},
    {'id': 'R18', 'phase': '4', 'title': 'Transaction categorisation with a probability; below threshold ask the user', 'why': 'Classifier fine-tune only with thousands of labels', 'criterion': 'user questions <20%, accuracy on the rest ≥95%', 'hours': 2, 'where': 'both'},
    {'id': 'R19', 'phase': 'P', 'title': 'Forecasts: pool normalised errors across tickers for 21 and 63 days', 'why': 'At 63 days a 120-day window holds ~2 independent windows', 'criterion': 'Winkler ≤ per ticker; coverage ±3 pp (pooled)', 'hours': 2, 'where': 'both'},
    {'id': 'R20', 'phase': 'P', 'title': 'Forecasts: exponentially weighted conformal quantile instead of the 120/40 window', 'why': 'Winkler-optimal window for GARCH-like series is 5–15 observations', 'criterion': '≥5% Winkler at 5 d, no loss at 21 d', 'hours': 2, 'where': 'both'},
    {'id': 'R21', 'phase': 'P', 'title': 'Forecasts: variance inflation when earnings fall inside the horizon (single stocks)', 'why': '>90% jump probability in the post-announcement session', 'criterion': 'coverage with/without earnings both within ±5 pp', 'hours': 2, 'where': 'both'},
    {'id': 'R22', 'phase': 'P', 'title': 'Forecasts: continuous VIX normaliser + separate p10/p90 tails', 'why': 'Nobody has tested a discrete multiplier; implied vol is the best 1-month predictor', 'criterion': 'coverage by VIX tercile ±5 pp', 'hours': 2, 'where': 'both'},
    {'id': 'R23', 'phase': 'P', 'title': 'LLM as narrator of computed descriptors + anomaly flags from code', 'why': 'Narrative faithfulness 0.70 → 0.996 when code computes the numbers', 'criterion': 'no numbers in the narrative outside the descriptors', 'hours': 2, 'where': 'both'},
    {'id': 'R24', 'phase': '⏸', 'title': 'Reranker Qwen3-Reranker-0.6B, retrieve 30 → 5', 'why': 'Only when recall@6 <95% on 60 questions after R6–R8; at ~1k chunks it is mostly latency', 'criterion': 'nDCG@5 +5; rerank <800 ms', 'hours': 2, 'where': 'both'},
    {'id': 'R25', 'phase': '⏸', 'title': 'GEPA with a cloud reflection model, 20–100 examples, 1500-char cap', 'why': 'Only with 50+ cases per prompt; at N=30 GEPA 34% vs seed 62%', 'criterion': 'separate validation set; no pass→fail', 'hours': 4, 'where': 'both'},
    {'id': 'R26', 'phase': '⏸', 'title': 'Speculative decoding (Qwen3.5-0.8B draft or ngram)', 'why': 'Retest after R11; through 10/2026 a loss of 11–24% on M1; revert if <+15%', 'criterion': 'tok/s +15% on 20 prompts', 'hours': 1, 'where': 'both'},
    {'id': 'X1', 'phase': 'X', 'title': 'Fine-tuning the model on own Q&A', 'why': 'Small data sets: “not worth it”; exception: classification with thousands of labels'},
    {'id': 'X2', 'phase': 'X', 'title': 'Mem0 / Letta / Zep', 'why': 'Vendor numbers −25 pp on independent re-run; current lessons already have the recommended shape'},
    {'id': 'X3', 'phase': 'X', 'title': 'GraphRAG', 'why': 'Worse than vanilla on facts, 2.3× latency'},
    {'id': 'X4', 'phase': 'X', 'title': 'HyDE / multi-query with a small model', 'why': '+25–40% time, hallucinations; worse than BM25 on tables'},
    {'id': 'X5', 'phase': 'X', 'title': 'Time-series foundation models (Chronos-2, TimesFM) for bands', 'why': 'Negative R², direction ≈51%, no finance data in pretraining'},
    {'id': 'X6', 'phase': 'X', 'title': 'ACI / PID / EnbPI on top of the rolling quantile', 'why': 'Replay and the 2025 review: no gain without a regime break'},
    {'id': 'X7', 'phase': 'X', 'title': 'MLX instead of llama.cpp', 'why': 'Prefill 1.7–2.2× slower, no JSON schema in mlx_lm'},
    {'id': 'X8', 'phase': 'X', 'title': 'Self-hosted Langfuse, OTel GenAI attributes', 'why': '6 services and 8–16 GiB RAM; 0 stable attributes; a SQLite table (R4) does the job'},
    {'id': 'X9', 'phase': 'X', 'title': 'Jev as a service', 'why': 'No self-hosting, 72.5% vs 84% Claude, 61% of decisions flipped by context'},
    {'id': 'X10', 'phase': 'X', 'title': 'Local LLM judge with a rubric', 'why': 'must-contain checks are better; 99.4% of judge flags were false positives in production'},
    {'id': 'X11', 'phase': 'X', 'title': 'KV cache q4, IQ4_XS, Q8 weights for a 9B', 'why': 'q4 on V breaks numbers; IQ4_XS 2.4× KLD; Q8 1.7× slower for <1% ppl'},
]


# States follow PMO RAG reporting (Red / Amber / Green): error = red, broken; todo = amber,
# your action; auto = green, runs by itself (action optional); ok = green.
def _step(area, state, title, detail, action=None):
    return {"area": area, "state": state, "title": title, "detail": detail, "action": action}


def eval_history():
    """Quality-eval results from <data>/eval/*.json (written by an eval harness with --record)."""
    out = []
    for p in _eval_dir().glob("*.json"):
        try:
            r = json.loads(p.read_text())
        except Exception:
            continue
        if isinstance(r, dict) and "passed" in r and "total" in r:
            out.append({"ts": r.get("ts", ""), "passed": r["passed"], "total": r["total"],
                        "model": r.get("model", ""), "file": p.name})
    return sorted(out, key=lambda r: r["ts"])


def _eval_dir():
    return Path(os.environ["FINANCE_PROJECT_DIR"]) / "eval"


def eval_cmd():
    """Argv of the quality eval (a list, no shell): the `ai_eval_cmd` setting (JSON list).
    The app appends `--record <data>/eval/run-<date>.json` itself."""
    import planner
    cmd = planner.get_json_setting("ai_eval_cmd")
    if isinstance(cmd, list) and cmd and all(isinstance(x, str) for x in cmd):
        return cmd
    return None


def eval_due(model=None, hist=None):
    """(is there a reason to run, why). Reasons: never run, the model changed, EVAL_STALE_DAYS
    passed, the question set (gold*.json) changed after the last result."""
    hist = eval_history() if hist is None else hist
    if not hist:
        return True, "no run yet"
    last = hist[-1]
    try:
        age = (datetime.now() - datetime.fromisoformat(last["ts"].replace(" ", "T"))).days
    except ValueError:
        age = 999
    if model and last["model"] and model != last["model"]:
        return True, "the model changed since the last run"
    if age > EVAL_STALE_DAYS:
        return True, f"last run {age} days ago"
    try:
        last_m = (_eval_dir() / last["file"]).stat().st_mtime
        if any(g.stat().st_mtime > last_m for g in _eval_dir().glob("gold*.json")):
            return True, "the question set changed after the last run"
    except OSError:
        pass
    return False, f"last run {age} days ago, current"


def run_eval():
    """Scheduler task: the eval runs only when there is a reason (eval_due) and the local
    model is online. No reason or no command is a success (nothing to do), not a failure."""
    cmd = eval_cmd()
    if not cmd:
        return True
    import llm_local
    st = llm_local.status()
    if not st.get("online"):
        return True
    if not eval_due(st.get("model"))[0]:
        return True
    d = _eval_dir()
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"run-{datetime.now():%Y-%m-%d_%H%M}.json"
    subprocess.run([*cmd, "--record", str(out)], capture_output=True, timeout=1800)
    return out.exists()


def status():
    steps, hist = [], []

    model = None
    try:
        import llm_local
        st = llm_local.status()
        model = st.get("model") if st.get("online") else None
        steps.append(_step("model", "ok" if model else "error", "Local model",
                           f"running: {model}" if model else "offline: without it the AI neither answers nor embeds",
                           None if model else {"kind": "info", "label": "start your llama-server (see README)"}))
    except Exception:
        pass

    try:
        import planner
        import rag
        rs = rag.status()
        dirty = planner.get_setting("rag_dirty") == "1"
        missing = rs.get("chunks", 0) - rs.get("embedded", 0)
        ok = not dirty and missing <= 0
        steps.append(_step("rag", "ok" if ok else "auto", "AI memory (RAG)",
                           f"{rs.get('chunks', 0)} chunks, {rs.get('embedded', 0)} embedded. "
                           + ("New data: it indexes itself before the next AI question (and weekly on schedule). "
                              "The button does it now, usually in seconds, because embeddings of unchanged chunks are carried over."
                              if dirty else "")
                           + (f"{missing} chunks without an embedding (the embedding server was offline); they get one at the next indexing." if missing > 0 else "")
                           + ("Current." if ok else ""),
                           None if ok else {"kind": "reindex", "label": "Refresh now"}))
    except Exception:
        pass

    try:
        import llm_log
        r = llm_log.stats()
        recent = r["unrated_recent"]
        steps.append(_step("ratings", "todo" if recent else "ok", "Rate answers 👍/👎",
                           (f"{recent} answers from the last 30 days unrated. " if recent else "All recent answers rated. ")
                           + f"Rated {r['rated']} of {r['total']} in total (👍 {r['up']} · 👎 {r['down']}). "
                           "Ratings tell whether the lessons help.",
                           {"kind": "scroll", "label": "Go to the log", "target": "aiLogBox"} if recent else None))
    except Exception:
        pass

    try:
        import experience
        lessons = experience.listing()
        bad = [x for x in lessons if x["bad"]]
        used = sum(1 for x in lessons if x["used"])
        if not lessons:
            steps.append(_step("lessons", "todo", "Lessons", "No lessons yet. On a good answer click 💡 “Learn from this”.",
                               {"kind": "scroll", "label": "Go to the log", "target": "aiLogBox"}))
        else:
            steps.append(_step("lessons", "todo" if bad else "ok", "Lessons",
                               f"Lessons: {len(lessons)}, used in answers: {used}"
                               + (f". {len(bad)} rated worse than they help: review and prune" if bad else ". None is harmful")
                               + ". At most one lesson enters the context at a time.",
                               {"kind": "scroll", "label": "Review lessons", "target": "expBox"} if bad else None))
    except Exception:
        pass

    try:
        hist = eval_history()
        due, why = eval_due(model, hist)
        cmd = eval_cmd()
        auto = bool(cmd) and bool(model)
        last = hist[-1] if hist else None
        score = f"Score {last['passed']}/{last['total']} ({last['ts']}, {last['model']}). " if last else "No results yet. "
        if not due:
            how = "Re-runs by itself when the model changes, 30 days pass or you add a question to the set."
        elif auto:
            how = "Runs by itself at the next schedule check (task “AI quality eval”, daily). You can also run the command now."
        elif not model:
            how = "Will not run by itself: the local model is offline."
        else:
            how = "Will not run by itself: no eval command (setting ai_eval_cmd, a JSON list of arguments that records {ts, model, passed, total} into <data>/eval/)."
        steps.append(_step("eval", ("auto" if auto else "todo") if due else "ok", "AI quality eval",
                           f"{score}{why[0].upper()}{why[1:]}. {how}",
                           {"kind": "cmd", "label": "Command", "cmd": shlex.join([*cmd, "--record", "<data>/eval/run-<date>.json"])} if cmd else None))
    except Exception:
        pass

    try:
        import planner_recs
        planner_recs._ensure_rec_log()
        n = eb._rows("select count(*) n from rec_log where resolved_at is not null and outcome is null")[0]["n"]
        steps.append(_step("recs", "todo" if n else "ok", "Recommendation outcomes",
                           f"{n} resolved without an outcome: mark done / rejected / obsolete." if n else
                           "Every resolved one has an outcome (a change of numbers only is marked by itself).",
                           {"kind": "link", "label": "Recommendations", "href": "#recs"} if n else None))
    except Exception:
        pass

    try:
        import market
        last = market._ft_rows("select max(made_on) d from forecast_track")[0]["d"]
        sc = market.forecast_selfscore()
        cov = ", ".join(f"{h['days']}d {h['coverage_pct']}%" for h in sc.get("horizons", []))
        stale = not last or (datetime.now().date() - datetime.fromisoformat(last).date()).days > 4
        steps.append(_step("forecasts", "error" if stale else "auto", "Price forecasts (self-calibration)",
                           (f"The cycle is not running: last forecast {last}. " if stale else f"Daily by itself, last {last}. ")
                           + f"Band hit rate (target 80%): {cov}. Nothing to tune by hand: the bands calibrate on their own errors.",
                           {"kind": "link", "label": "Calibration", "href": "#forecasts"}))
    except Exception:
        pass

    try:
        import planner
        fr = planner.freshness()
        due = fr.get("due") or []
        n_plan = eb._rows("select count(*) n from fire_snapshots where plan_flow is not null")[0]["n"]
        steps.append(_step("data", "todo" if due else "ok", "Fresh data (fuel for the AI and forecasts)",
                           (f"{len(due)} items to update (~{fr.get('total_minutes')} min). " if due else "Data is current. ")
                           + f"FIRE snapshots with a frozen plan: {n_plan} (they feed “plan vs actual”).",
                           {"kind": "link", "label": "Dashboard", "href": "#dashboard"} if due else None))
    except Exception:
        pass

    try:
        import schedules
        failed = schedules.failed_tasks()
        steps.append(_step("schedules", "error" if failed else "ok", "Scheduled tasks",
                           ("Failing: " + "; ".join(f"{f['label']} ({str(f.get('error', ''))[:60]})" for f in failed)
                            + ". The learning loop stalls until they pass." if failed else
                            "Every task of the learning loop (reindex, forecasts, quality eval) last ran without an error."),
                           {"kind": "link", "label": "Schedules", "href": "#data"} if failed else None))
    except Exception:
        pass

    phase_status = {"done": "done", "X": "rejected", "⏸": "conditional"}
    roadmap = [dict(r, status=phase_status.get(r["phase"], "idea")) for r in ROADMAP]
    try:  # R1 is computed from data: how many questions the gold set has
        n_gold = sum(len(json.loads(g.read_text())) for g in _eval_dir().glob("gold*.json"))
        r1 = next(r for r in roadmap if r["id"] == "R1")
        r1["title"] += f" (today: {n_gold})"
        if n_gold >= 50:
            r1["status"] = "done"
    except Exception:
        pass
    order = {"error": 0, "todo": 1, "auto": 2, "ok": 3}
    steps.sort(key=lambda s: order.get(s["state"], 9))
    return {"steps": steps, "todo": sum(1 for s in steps if s["state"] == "todo"),
            "errors": sum(1 for s in steps if s["state"] == "error"), "progress": {"eval": hist}, "roadmap": roadmap}
