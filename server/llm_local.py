"""Optional local LLM (llama.cpp) — a private AI brain for sensitive data.

Talks to a local llama-server (OpenAI-compatible API) at http://localhost:8080/v1.
Start the server (after installing llama.cpp, e.g. `brew install llama.cpp`):
  llama-server -hf bartowski/Qwen3-8B-GGUF:Q4_K_M --port 8080 --api-key <secret> \
      --spec-type ngram-simple

The app never *requires* an LLM. When one is running it stays 100% local, so
sensitive numbers never leave the machine — used for things like the AI answers
and the market brief. Everything degrades
gracefully to "offline" when no server is up.
"""
import json
import os
import urllib.request

BASE = os.environ.get("LOCAL_LLM_URL", "http://127.0.0.1:8080/v1")
KEY = os.environ.get("LOCAL_LLM_KEY", "")


def _headers(extra=None):
    h = dict(extra or {})
    if KEY:
        h["Authorization"] = "Bearer " + KEY
    return h


def status():
    """Is the local model alive, and which model is it?"""
    try:
        req = urllib.request.Request(BASE + "/models", headers=_headers())
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read())
        model = (data.get("data") or [{}])[0].get("id", "?")
        return {"online": True, "model": model.split("/")[-1], "url": BASE}
    except Exception as e:
        return {"online": False, "url": BASE, "hint":
                "llama-server -hf bartowski/Qwen3-8B-GGUF:Q4_K_M --port 8080 --api-key <secret> --spec-type ngram-simple",
                "error": str(e)[:80]}


_MODEL_NAME = None


def _model_name():
    global _MODEL_NAME
    if _MODEL_NAME is None:
        _MODEL_NAME = status().get("model") or ""
    return _MODEL_NAME


def chat(prompt, system=None, max_tokens=400, temperature=0.2, json_schema=None,
         think=None):
    """Single completion. Returns text, or None when offline.

    json_schema (optional): a JSON Schema — llama.cpp compiles it into a GBNF
    grammar and CONSTRAINS the output to be valid, schema-conforming JSON at the
    token level. No more parse failures or retries: the model cannot emit
    anything outside the schema.

    think (optional): on models with a toggleable thinking mode (Qwen3 family)
    True/False appends the /think or /no_think soft switch — thinking helps
    multi-step analysis, hurts latency on trivial calls. None = model default.
    """
    if think is not None and "qwen3" in _model_name().lower():
        prompt = prompt + (" /think" if think else " /no_think")
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    payload = {"messages": msgs, "max_tokens": max_tokens, "temperature": temperature}
    if json_schema:
        payload["response_format"] = {"type": "json_schema",
            "json_schema": {"name": "out", "schema": json_schema, "strict": True}}
    req = urllib.request.Request(BASE + "/chat/completions", data=json.dumps(payload).encode(),
                                 headers=_headers({"Content-Type": "application/json"}))
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read())
        return out["choices"][0]["message"]["content"]
    except Exception:
        return None


def chat_json(prompt, schema, system=None, max_tokens=400, temperature=0.2, think=None):
    """Like chat(), but guarantees a dict conforming to `schema` (GBNF), or None."""
    raw = chat(prompt, system=system, max_tokens=max_tokens,
               temperature=temperature, json_schema=schema, think=think)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def chat_with_tools(prompt, tools, handlers, system=None, max_tokens=700,
                    temperature=0.2, max_rounds=4):
    """Agentic loop over llama-server's OpenAI-compatible function calling:
    send tools → execute requested calls locally → feed results back → repeat
    until the model answers in text. Returns the final text, or None when the
    server is offline / doesn't support tools (callers fall back to chat()).

    handlers: {tool_name: callable(**args) -> JSON-serializable result}."""
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    text = None
    for _ in range(max_rounds):
        payload = {"messages": msgs, "max_tokens": max_tokens,
                   "temperature": temperature, "tools": tools}
        req = urllib.request.Request(BASE + "/chat/completions",
                                     data=json.dumps(payload).encode(),
                                     headers=_headers({"Content-Type": "application/json"}))
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                out = json.loads(r.read())
            msg = out["choices"][0]["message"]
        except Exception:
            return None
        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content")
        msgs.append(msg)
        for c in calls:
            fn = (c.get("function") or {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            handler = handlers.get(fn.get("name"))
            try:
                result = handler(**args) if handler else {"error": "unknown tool"}
            except Exception as e:
                result = {"error": str(e)[:200]}
            msgs.append({"role": "tool", "tool_call_id": c.get("id") or fn.get("name"),
                         "content": json.dumps(result, ensure_ascii=False, default=str)[:4000]})
    return text


# --- reranking (optional, third RAG stage) ---
RERANK_URL = os.environ.get("LOCAL_RERANK_URL", "")
RERANK_MODEL = os.environ.get("LOCAL_RERANK_MODEL", "")


def rerank(query, docs, top_n=5):
    """Order docs by true relevance with a local reranker model. Returns a list
    of indices into docs (best first), or None when no reranker is configured —
    RAG then keeps its BM25+cosine order. Run a dedicated server, e.g.:
      llama-server -hf gpustack/bge-reranker-v2-m3-GGUF --embedding --pooling rank --port 8082
    and set LOCAL_RERANK_URL=http://127.0.0.1:8082/v1"""
    if not RERANK_URL or not docs:
        return None
    payload = {"query": query, "documents": list(docs), "top_n": min(top_n, len(docs))}
    if RERANK_MODEL:
        payload["model"] = RERANK_MODEL
    headers = {"Content-Type": "application/json"}
    rk = os.environ.get("LOCAL_RERANK_KEY", "") or KEY
    if rk:
        headers["Authorization"] = "Bearer " + rk
    req = urllib.request.Request(RERANK_URL.rstrip("/") + "/rerank",
                                 data=json.dumps(payload).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            out = json.loads(r.read())
        results = sorted(out.get("results") or [],
                         key=lambda x: -(x.get("relevance_score") or 0))
        idx = [x["index"] for x in results if isinstance(x.get("index"), int)]
        return idx[:top_n] or None
    except Exception:
        return None


# --- embeddings (optional, for semantic RAG) ---
EMBED_URL = os.environ.get("LOCAL_EMBED_URL") or BASE
EMBED_MODEL = os.environ.get("LOCAL_EMBED_MODEL", "")


def embed(text):
    """Embedding vector for text from a local server (OpenAI-compatible
    /embeddings). None if the server serves no embeddings — RAG then stays
    lexical. Run a dedicated embedding server, e.g.:
      llama-server -hf <embed-model-GGUF> --embeddings --port 8081
    and set LOCAL_EMBED_URL=http://127.0.0.1:8081/v1 (+ LOCAL_EMBED_KEY if keyed)."""
    if not text:
        return None
    payload = {"input": text[:8000]}
    if EMBED_MODEL:
        payload["model"] = EMBED_MODEL
    headers = {"Content-Type": "application/json"}
    ek = os.environ.get("LOCAL_EMBED_KEY", "") or KEY
    if ek:
        headers["Authorization"] = "Bearer " + ek
    req = urllib.request.Request(EMBED_URL + "/embeddings",
                                 data=json.dumps(payload).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read())
        return out["data"][0]["embedding"]
    except Exception:
        return None
