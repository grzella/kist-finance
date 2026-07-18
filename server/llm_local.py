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


def chat(prompt, system=None, max_tokens=400, temperature=0.2):
    """Single completion. Returns text, or None when offline."""
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    body = json.dumps({"messages": msgs, "max_tokens": max_tokens,
                       "temperature": temperature}).encode()
    req = urllib.request.Request(BASE + "/chat/completions", data=body,
                                 headers=_headers({"Content-Type": "application/json"}))
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read())
        return out["choices"][0]["message"]["content"]
    except Exception:
        return None


def categorize_transaction(description, amount, categories):
    """Categorize a transaction locally (data does not leave the machine)."""
    ans = chat(
        f'Transaction: "{description}", amount {amount}. '
        f'Pick exactly ONE category from: {", ".join(categories)}. '
        f'Answer with the category name only.',
        system="You are an expense-categorization assistant. Answer in one word.",
        max_tokens=20)
    if ans:
        ans = ans.strip().strip('."')
        for c in categories:
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
