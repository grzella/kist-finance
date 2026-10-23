"""ailearn.js rendered by the real api.js + view code in Node with a stubbed DOM and fetch
(skipped without node). Covers the empty state, malformed assessments and the score panel."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "static" / "js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

RUNNER = r"""
const fs = require("fs"), vm = require("vm");
const [apiJs, viewJs, payloadFile] = process.argv.slice(2);
const payload = JSON.parse(fs.readFileSync(payloadFile, "utf8"));
const calls = [];
const el = () => ({ _v: "", addEventListener() {}, set value(v) { this._v = v; }, get value() { return this._v; }, textContent: "", disabled: false });
const ids = {};
const ctx = {
  window: { matchMedia: () => ({ matches: false, addEventListener() {} }) }, location: { search: "", hash: "" },
  localStorage: { getItem: () => null, setItem() {} }, navigator: {}, console, URL, JSON, Promise, Math, Date, Number, String, Array, Object, Set, RegExp, Error, isNaN, parseFloat,
  document: { addEventListener() {},
              getElementById: (id) => (ids[id] = ids[id] || el()), querySelectorAll: () => [], documentElement: { classList: { toggle() {} }, setAttribute() {}, dataset: {}, style: {} } },
  fetch: async (url, opts) => { calls.push([(opts && opts.method) || "GET", url]);
    const body = payload[url]; if (body === undefined) return { ok: false, status: 404, text: async () => "nope" };
    return { ok: true, json: async () => body }; },
  getComputedStyle: () => ({ getPropertyValue: () => "" }), route() {},
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(apiJs, "utf8") + "\n" + fs.readFileSync(viewJs, "utf8") + "\nthis.renderAiLearn = renderAiLearn;", ctx);
const node = { innerHTML: "", querySelectorAll: () => [] };
ctx.renderAiLearn(node).then(() => console.log(JSON.stringify({ html: node.innerHTML, calls })))
  .catch((e) => { console.log(JSON.stringify({ error: String(e.stack || e) })); });
"""


def render(tmp_path, content, state=None, history=(), repos=None):
    (tmp_path / "run.js").write_text(RUNNER, encoding="utf-8")
    payload = {"/api/ai-learning": {"content": content, "state": state or {}, "history": list(history)},
               "/api/ai-learning/repos": repos if repos is not None else {"repos": [], "author": ""}}
    (tmp_path / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
    out = subprocess.run(["node", str(tmp_path / "run.js"), str(STATIC / "api.js"),
                          str(STATIC / "views" / "ailearn.js"), str(tmp_path / "payload.json")],
                         capture_output=True, text=True, timeout=30, cwd=tmp_path)
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert "error" not in got, got.get("error")
    return got["html"]


ASSESSMENT = {
    "as_of": "2026-10-23", "score": 2.6, "target": 3, "score_label": "Practitioner", "verdict": "ok",
    "scale": [{"lvl": 2, "name": "Practitioner", "desc": "d"}],
    "skills": [{"id": "rag", "area": "Building", "name": "Retrieval", "status": "partial", "how": "h",
                "evidence": ["repo · dep: chromadb", "<img src=x onerror=alert(1)>"]}],
    "certs": [{"id": "c", "name": "Course", "provider": "p", "cost": "free", "time": "t", "format": "online",
               "priority": "high", "why": "w", "link": "https://example.com"}],
    "generated": {"by": "repos", "narration": "local model", "sources": {"local": 1, "gh": 0}}}


def test_empty_state_offers_scoring_repos_and_the_paste_box(tmp_path):
    html = render(tmp_path, {})
    assert "Score from my repos" in html and 'id="alScoreBtn"' in html and 'id="alRepos"' in html
    assert 'data-savejson="analysis_ai_learning"' in html          # the manual path, like Career and Property
    assert "data-copyprompt=" in html and "scale" in html


@pytest.mark.parametrize("bad", ["not a list", {"x": 1}, 7])
def test_a_scale_of_the_wrong_type_shows_the_empty_state_instead_of_crashing(tmp_path, bad):
    html = render(tmp_path, {"as_of": "2026-01-01", "scale": bad})
    assert 'data-savejson="analysis_ai_learning"' in html


def test_a_numeric_course_format_does_not_break_the_view(tmp_path):
    a = json.loads(json.dumps(ASSESSMENT))
    a["certs"][0]["format"] = 5
    assert "Course" in render(tmp_path, a)


def test_scored_view_shows_evidence_history_and_escapes_everything(tmp_path):
    html = render(tmp_path, ASSESSMENT, history=[
        {"date": "2026-09-01", "score": 1.9, "level": 1, "have": 1, "partial": 5, "missing": 5, "repos": 2, "narration": "template"},
        {"date": "2026-10-23", "score": 2.6, "level": 2, "have": 2, "partial": 5, "missing": 4, "repos": 3,
         "narration": "<b>x</b>"}],
        repos={"repos": ["/work/<b>one</b>"], "author": "A\"B"})
    assert "Evidence: repo · dep: chromadb" in html
    assert "<img src=x" not in html and "&lt;img src=x" in html      # evidence lines are model-adjacent text
    assert "Score history" in html and "2.6" in html and "1.9" in html
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html
    assert "/work/<b>one</b>" not in html                            # repo paths are escaped in the textarea
    assert "Last run 2026-10-23, text by local model." in html
    assert "(1 connected)" in html


def test_view_works_without_history_or_generated_block(tmp_path):
    a = {k: v for k, v in ASSESSMENT.items() if k != "generated"}
    html = render(tmp_path, a)
    assert "Score history" not in html and "Score from my repos" in html
