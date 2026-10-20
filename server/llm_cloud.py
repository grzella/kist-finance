"""Optional cloud model (Claude) — to compare against the local LLM.

Calls the Anthropic Messages API directly (raw HTTP, stdlib — consistent with
llm_local.py; the app keeps its dependencies minimal). Key from ANTHROPIC_API_KEY
(.env, git-ignored). Model: CLOUD_LLM_MODEL (defaults to claude-fable-5, the newest model).

PRIVACY NOTE: cloud mode SENDS the prompt to Anthropic. The app defaults to
'local' mode (local model only); the user enables the cloud deliberately in
Control Center.
"""
import json
import os
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("CLOUD_LLM_MODEL", "claude-fable-5")


def _key():
    return os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")


def status():
    """Is the cloud configured (key present)? Does not make a request."""
    k = _key()
    return {"online": bool(k), "model": MODEL, "provider": "Anthropic (Claude)",
            "hint": "" if k else "set ANTHROPIC_API_KEY in .env"}


def chat(prompt, system=None, max_tokens=2000):
    """One request to Claude. Returns text or None (no key / error / refusal)."""
    k = _key()
    if not k:
        return None
    body = {"model": MODEL, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    if system:
        body["system"] = system
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode(),
        headers={"x-api-key": k, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read())
    except Exception:
        return None
    if out.get("stop_reason") == "refusal":
        return None
    return "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text") or None
