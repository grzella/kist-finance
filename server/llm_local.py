"""Optional local LLM (llama.cpp) — a private AI brain for sensitive data.

Talks to a local llama-server (OpenAI-compatible API) at http://localhost:8080/v1.
Start the server (after installing llama.cpp, e.g. `brew install llama.cpp`):
  llama-server -hf bartowski/Qwen2.5-3B-Instruct-GGUF:Q4_K_M --port 8080 --api-key <secret>

The app never *requires* an LLM. When one is running it stays 100% local, so
sensitive numbers never leave the machine — used for things like transaction
categorization and narrating why a forecast band was missed. Everything degrades
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
                "llama-server -hf bartowski/Qwen2.5-3B-Instruct-GGUF:Q4_K_M --port 8080 --api-key <secret>",
                "error": str(e)[:80]}


def chat(prompt, system=None, max_tokens=400, temperature=0.2, json_schema=None):
    """Single completion. Returns text, or None when offline.

    json_schema (optional): a JSON Schema — llama.cpp compiles it into a GBNF
    grammar and CONSTRAINS the output to be valid, schema-conforming JSON at the
    token level. No more parse failures or retries: the model cannot emit
    anything outside the schema.
    """
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


def chat_json(prompt, schema, system=None, max_tokens=400, temperature=0.2):
    """Like chat(), but guarantees a dict conforming to `schema` (GBNF), or None."""
    raw = chat(prompt, system=system, max_tokens=max_tokens,
               temperature=temperature, json_schema=schema)
    if not raw:
        return None
    try:
        return json.loads(raw)
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


def categorize_transaction(description, amount, categories):
    """Categorize a transaction locally (data does not leave the machine).

    Uses GBNF (an enum in the JSON Schema) — the model MUST pick one of the
    given categories, so the result is always valid (no free-text parsing).
    """
    cats = list(categories)
    schema = {"type": "object", "additionalProperties": False,
              "required": ["category"],
              "properties": {"category": {"type": "string", "enum": cats}}}
    data = chat_json(
        f'Transaction: "{description}", amount {amount}. '
        f'Pick the best category from: {", ".join(cats)}.',
        schema,
        system="You are an expense-categorization assistant.",
        max_tokens=30)
    if data and data.get("category") in cats:
        return data["category"]
    # Fallback for servers without response_format support: text matching.
    ans = chat(
        f'Transaction: "{description}", amount {amount}. '
        f'Pick exactly ONE category from: {", ".join(cats)}. '
        f'Answer with the category name only.',
        system="You are an expense-categorization assistant. Answer in one word.",
        max_tokens=20)
    if ans:
        ans = ans.strip().strip('."')
        for c in cats:
            if c.lower() in ans.lower():
                return c
    return None


def explain_forecast_miss(ticker, horizon_days, predicted_band, realized):
    """Narrate why a forecast band was missed (commentary, not math — the
    calibration itself is computed in forecast_models)."""
    return chat(
        f"Forecast band for {ticker} over {horizon_days} sessions: "
        f"{predicted_band}. Actual: {realized}. In 2-3 sentences: what could have "
        f"driven the move outside the band, and what it teaches about this asset's volatility.",
        system="You are a concise market analyst. No disclaimers.",
        max_tokens=150)
