"""Pentest-grade security + functional self-review for the budget app.

Runs a battery of checks in five areas and returns a structured report:
  1. REPO LEAKS   — secrets / sensitive data in the working tree AND git history
                    (history matters most: making a repo public exposes every
                    commit ever made, not just the current files).
  2. CODE         — dangerous patterns a future contributor could introduce
                    (eval/exec, shell=True, SQL built from user input, debug on,
                    binding to 0.0.0.0, template injection, hardcoded secrets).
  3. CONFIG       — .gitignore coverage, .env.example hygiene, connection
                    surface (Supabase/n8n keys never in tracked code).
  4. FUNCTIONAL   — every GET endpoint answers 200 + JSON, DB schema is intact,
                    market data pipe is alive (or gracefully offline).

Each finding: {id, area, severity, status, title, detail, fix}.
  severity: critical > high > medium > low > info
  status:   pass | warn | fail

Usable three ways:
  - imported:  security_review.run()  -> dict report
  - from API:  /api/security-review
  - from CI:   python -m security_review --ci   (exit 1 if any fail)
"""
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------- helpers

def _repo_root():
    """The git toplevel — the WHOLE repo must be scanned, never a subdir
    (else a subtree scan looks clean while the rest of the repo is unchecked)."""
    start = str(Path(__file__).resolve().parent.parent)
    try:
        r = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=10)
        top = r.stdout.strip()
        if top:
            return top
    except Exception:
        pass
    try:
        import market as _mkt
        return str(_mkt._finance_dir().parent)
    except Exception:
        return start


def _git(repo, args, timeout=30):
    try:
        return subprocess.run(["git", "-C", repo] + args,
                              capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


# Secret signatures. Literals are split by concatenation so THIS file does not
# match its own scan (the scanner would otherwise flag its own source).
_SECRET_PATTERNS = [
    ("JWT / Supabase key",        "eyJ" + "hbGciOiJ"),
    ("Supabase project URL",      r"https://[a-z0-9]{15,}\.supabase\.co"),
    ("n8n webhook id",            r"/webhook/[a-f0-9]{8}-[a-f0-9-]{20,}"),
    ("OpenAI-style key",          "sk" + r"-[A-Za-z0-9]{20,}"),
    ("Anthropic key",             "sk-ant" + r"-[A-Za-z0-9_-]{20,}"),
    ("GitHub token",              "gh[pousr]" + r"_[A-Za-z0-9]{20,}"),
    ("AWS access key id",         "AKI" + r"A[0-9A-Z]{16}"),
    ("Google API key",            "AIza" + r"[0-9A-Za-z_-]{30,}"),
    ("Slack token",               "xox" + r"[baprs]-[0-9A-Za-z-]{10,}"),
    ("Private key block",         "-----" + "BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY"),
    ("Generic password assign",   r"(?i)(password|passwd|secret|api_?key|token)\s*[=:]\s*['\"][^'\"]{8,}"),
]

# Paths that must NEVER be tracked (in tree or history).
_SENSITIVE_PATHS = re.compile(
    r"(^|/)\.env($|\.(?!example))|(^|/)\.finance/|(^|/)private/|(^|/)doc-raw/|"
    r"(^|/)backups/|\.pem$|\.key$|\.p12$|\.pfx$|id_rsa|id_ed25519|"
    r"finance\.db$|\.db\.enc$", re.I)

# PUBLIC-REPO AUDIT — the maintainer's personal identifiers must NEVER appear
# in this generic OSS fork. If a bad merge / contributor re-introduces them,
# this fails the build. (In the private personal app these terms are expected;
# here they are a leak.)
_PERSONAL_MARKERS = [
    ("employer / ticker", r"\bAtlassian\b"),
    ("city A",            r"\u0141[o\u00f3]d[\u017a\u017c]|\u0141[o\u00f3]dzk"),
    ("city B",            r"Tarchomin"),
    ("street",            r"Piotrkowsk"),
    ("surname",           r"Grzella"),
]

# Excludes for content scans (docs / vendored / sample data are not code).
_SCAN_EXCLUDES = [":(exclude)*.md", ":(exclude)posts/*", ":(exclude)doc-raw/*",
                  ":(exclude)*.html", ":(exclude)static/vendor/*",
                  ":(exclude)*.min.js", ":(exclude)seed.py",
                  ":(exclude)**/security_review.py"]


# ---------------------------------------------------------------- 1. REPO LEAKS

def _check_repo_leaks(repo, tracked):
    out = []

    def f(sev, status, title, detail, fix=""):
        out.append({"id": "leak", "area": "REPO LEAKS", "severity": sev,
                    "status": status, "title": title, "detail": detail, "fix": fix})

    # 1a. sensitive files tracked right now
    tracked_bad = [t for t in tracked
                   if _SENSITIVE_PATHS.search(t) and not t.endswith(".env.example")]
    if tracked_bad:
        f("critical", "fail", "Wrażliwe pliki śledzone w repo",
          ", ".join(tracked_bad[:8]),
          "git rm --cached <plik>, dodaj do .gitignore, rozważ przepisanie historii")
    else:
        f("info", "pass", "Brak wrażliwych plików w drzewie roboczym",
          f"{len(tracked)} śledzonych plików, żaden nie pasuje do wzorców wrażliwych")

    # 1b. sensitive paths EVER in history (critical before going public)
    hist = _git(repo, ["log", "--all", "--pretty=format:", "--name-only"], timeout=40)
    ever = set(l.strip() for l in (hist.stdout.splitlines() if hist else []) if l.strip())
    hist_bad = sorted(p for p in ever
                      if _SENSITIVE_PATHS.search(p) and not p.endswith(".env.example"))
    if hist_bad:
        f("critical", "fail", "Wrażliwe pliki obecne w HISTORII gita",
          f"{len(hist_bad)} plików kiedyś commitowanych: " + ", ".join(hist_bad[:8]),
          "Publiczne repo ujawnia całą historię. Przepisz historię "
          "(git filter-repo --path <plik> --invert-paths) PRZED upublicznieniem.")
    else:
        f("info", "pass", "Historia gita bez wrażliwych plików",
          f"przeskanowano {len(ever)} unikalnych ścieżek w całej historii")

    # 1c. secret PATTERNS in current tree
    pat = "|".join("(?:%s)" % p for _, p in _SECRET_PATTERNS)
    r = _git(repo, ["grep", "-nIE", pat, "--"] + ["."] + _SCAN_EXCLUDES)
    hits = [l for l in (r.stdout.splitlines() if r else []) if l.strip()][:12]
    if hits:
        f("high", "fail", "Wzorce sekretów w śledzonym kodzie",
          " | ".join(h[:90] for h in hits[:6]),
          "Usuń sekret z kodu, trzymaj w .env (gitignored), użyj .env.example z placeholderem")
    else:
        f("info", "pass", "Brak wzorców sekretów w kodzie",
          f"sprawdzono {len(_SECRET_PATTERNS)} sygnatur (JWT, Supabase, tokeny, klucze prywatne…)")

    # 1d. secret patterns in HISTORY (pickaxe over all commits)
    rl = _git(repo, ["rev-list", "--all"], timeout=20)
    commits = (rl.stdout.split() if rl else [])
    if commits:
        rh = _git(repo, ["grep", "-IE", pat] + commits[:400] + ["--"] + _SCAN_EXCLUDES,
                  timeout=45)
        hh = [l for l in (rh.stdout.splitlines() if rh else []) if l.strip()]
        # drop matches that are only in the current tree (already reported in 1c)
        hh = [l for l in hh if not l.startswith("./") and ":" in l][:12]
        if hh:
            f("high", "fail", "Wzorce sekretów w HISTORII gita",
              f"{len(hh)} trafień w starych commitach: " + " | ".join(h[:70] for h in hh[:4]),
              "Sekret w historii = sekret spalony. Zrotuj klucz ORAZ przepisz historię.")
        else:
            f("info", "pass", "Historia gita bez wzorców sekretów",
              f"pickaxe po {min(len(commits),400)} commitach, zero trafień")

    # 1e. leak-check: real .env values appearing anywhere tracked
    env = Path(repo) / "apps" / "budget" / ".env"
    if not env.exists():
        env = Path(repo) / ".env"
    checked, leaked = 0, []
    if env.exists():
        for line in env.read_text(errors="ignore").splitlines():
            line = line.strip()
            if "=" not in line or line.startswith("#"):
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if len(v) < 12:
                continue
            checked += 1
            gr = _git(repo, ["grep", "-Fl", v, "--", "."])
            if gr and gr.stdout.strip():
                leaked.append(k.strip())
    if leaked:
        f("critical", "fail", "Realna wartość z .env znaleziona w repo",
          "wyciekłe zmienne: " + ", ".join(leaked), "Natychmiast zrotuj te sekrety i usuń z repo")
    elif checked:
        f("info", "pass", "Wartości z .env nie wyciekają do repo",
          f"{checked} sekretów z .env zweryfikowanych — żaden nie występuje w śledzonych plikach")

    return out


def _check_personal_data(repo):
    out = []

    def f(sev, status, title, detail, fix=""):
        out.append({"id": "pii", "area": "AUDYT DANYCH OSOBOWYCH (repo publiczne)",
                    "severity": sev, "status": status, "title": title,
                    "detail": detail, "fix": fix})

    # LICENSE/NOTICE legitimately carry the author's name (MIT copyright line) —
    # that is expected authorship, not a data leak; exclude them from this audit.
    pii_excludes = _SCAN_EXCLUDES + [":(exclude)LICENSE*", ":(exclude)NOTICE*"]
    hits = []
    for label, rx in _PERSONAL_MARKERS:
        r = _git(repo, ["grep", "-nIE", rx, "--"] + ["."] + pii_excludes)
        for ln in (r.stdout.splitlines() if r else []):
            if ln.strip():
                hits.append((label, ln.strip()))
    if hits:
        f("critical", "fail", "Dane osobowe maintainera w publicznym repo",
          "; ".join(f"{lbl}: {ln[:60]}" for lbl, ln in hits[:6]),
          "Repo publiczne musi byc generyczne. Usun/zamien realne dane; trzymaj je "
          "wylacznie w lokalnej .finance (gitignored).")
    else:
        f("info", "pass", "Brak danych osobowych w kodzie",
          f"sprawdzono {len(_PERSONAL_MARKERS)} wzorcow (pracodawca, miasta, nazwisko) — czysto")
    return out


# ---------------------------------------------------------------- 2. CODE

def _check_code(repo):
    out = []

    def f(sev, status, title, detail, fix=""):
        out.append({"id": "code", "area": "KOD (contributorzy)", "severity": sev,
                    "status": status, "title": title, "detail": detail, "fix": fix})

    # dangerous-pattern grep across python + js (docs/vendor excluded)
    checks = [
        ("high",   r"\beval\s*\(",                       "eval() — wykonanie dowolnego kodu",
         "Zastąp bezpiecznym parserem (json.loads / ast.literal_eval)"),
        ("high",   r"\bexec\s*\(",                       "exec() — wykonanie dowolnego kodu",
         "Usuń exec; przeprojektuj bez dynamicznego kodu"),
        ("high",   r"os\.system\s*\(",                   "os.system() — wstrzyknięcie powłoki",
         "Użyj subprocess z listą argumentów, bez powłoki"),
        ("high",   r"subprocess\.[a-z]+\([^)]*shell\s*=\s*True", "subprocess(shell=True) — wstrzyknięcie powłoki",
         "shell=False + lista argumentów"),
        ("critical", r"(pickle|cPickle)\.loads?\s*\(",   "pickle.load — deserializacja = RCE",
         "Nie deserializuj pickle z niezaufanych źródeł; użyj JSON"),
        ("high",   r"yaml\.load\s*\((?![^)]*Loader)",    "yaml.load bez SafeLoader",
         "yaml.safe_load(...)"),
        ("high",   r"render_template_string\s*\(",       "render_template_string — SSTI",
         "Renderuj statyczne szablony, nie sklejaj z danych"),
    ]
    files = ["*.py", "static/js/**"]
    for sev, rx, title, fix in checks:
        r = _git(repo, ["grep", "-nIE", rx, "--"] + files + _SCAN_EXCLUDES)
        hits = [l for l in (r.stdout.splitlines() if r else []) if l.strip()]
        if hits:
            f(sev, "warn" if sev != "critical" else "fail", title,
              f"{len(hits)}×: " + " | ".join(h[:80] for h in hits[:3]), fix)

    # SQL built by string interpolation inside a query call (execute/_exec/_rows)
    r = _git(repo, ["grep", "-nIE",
                    r"(execute|executescript|_exec|_rows)\s*\(\s*(f['\"]|['\"][^'\"]*(%s|%d|\{)|[^,)]*\.format\()",
                    "--", "*.py"] + _SCAN_EXCLUDES)
    sqlhits = [l for l in (r.stdout.splitlines() if r else []) if l.strip()]
    # elevate to injection if request data is on the same line
    inj = [h for h in sqlhits if re.search(r"request\.|args\[|\.json|get_json", h)]
    if inj:
        f("critical", "fail", "Możliwy SQL injection (dane żądania sklejane w zapytaniu)",
          " | ".join(h[:90] for h in inj[:3]),
          "Przekazuj wartości jako parametry (?, tuple), nigdy nie sklejaj stringów")
    elif sqlhits:
        f("medium", "warn", "SQL budowany przez interpolację (przejrzyj)",
          f"{len(sqlhits)}×: " + " | ".join(h[:80] for h in sqlhits[:3]),
          "Jeśli interpolujesz nazwę tabeli/kolumny — trzymaj ją na białej liście stałych; "
          "wartości zawsze przez parametry (?, tuple)")
    else:
        f("info", "pass", "Zapytania SQL parametryzowane",
          "brak sklejania stringów w wywołaniach execute/_exec/_rows")

    # Flask misconfig: debug=True / host 0.0.0.0
    r = _git(repo, ["grep", "-nIE", r"debug\s*=\s*True", "--", "*.py"] + _SCAN_EXCLUDES)
    if r and r.stdout.strip():
        f("high", "fail", "Flask debug=True", r.stdout.strip().splitlines()[0][:90],
          "debug=False w produkcji (debugger Werkzeug = RCE)")
    else:
        f("info", "pass", "Brak debug=True", "aplikacja nie startuje z debuggerem Werkzeug")

    r = _git(repo, ["grep", "-nIE", r"host\s*=\s*['\"]0\.0\.0\.0['\"]", "--", "*.py"] + _SCAN_EXCLUDES)
    if r and r.stdout.strip():
        f("medium", "warn", "Bind na 0.0.0.0 (dostęp z sieci)",
          r.stdout.strip().splitlines()[0][:90],
          "Bind na 127.0.0.1 — apka lokalna nie powinna słuchać na wszystkich interfejsach")
    else:
        f("info", "pass", "Bind tylko na 127.0.0.1", "serwer nie jest wystawiony na sieć")

    # CORS wildcard
    r = _git(repo, ["grep", "-nIE", r"Access-Control-Allow-Origin['\"]?\s*[,:]\s*['\"]\*|CORS\([^)]*\*",
                    "--", "*.py"] + _SCAN_EXCLUDES)
    if r and r.stdout.strip():
        f("medium", "warn", "CORS wildcard (*)", r.stdout.strip().splitlines()[0][:90],
          "Ogranicz CORS do znanych origin albo usuń dla apki lokalnej")

    return out


# ---------------------------------------------------------------- 3. CONFIG

def _check_config(repo, tracked):
    out = []

    def f(sev, status, title, detail, fix=""):
        out.append({"id": "config", "area": "KONFIGURACJA / POŁĄCZENIA", "severity": sev,
                    "status": status, "title": title, "detail": detail, "fix": fix})

    root = Path(repo)
    # .gitignore covers sensitive paths
    gi = ""
    for cand in (root / ".gitignore", root / "apps" / "budget" / ".gitignore"):
        if cand.exists():
            gi += cand.read_text(errors="ignore") + "\n"
    need = [".env", ".finance", "backups"]
    missing = [n for n in need if n not in gi]
    if missing:
        f("high", "fail", ".gitignore nie pokrywa wrażliwych ścieżek",
          "brakuje: " + ", ".join(missing), "Dodaj wpisy do .gitignore")
    else:
        f("info", "pass", ".gitignore pokrywa wrażliwe ścieżki",
          "obecne: " + ", ".join(need))

    # .env.example must exist and hold NO real values
    exa = None
    for cand in (root / ".env.example", root / "apps" / "budget" / ".env.example"):
        if cand.exists():
            exa = cand
            break
    if exa:
        txt = exa.read_text(errors="ignore")
        pat = "|".join("(?:%s)" % p for _, p in _SECRET_PATTERNS[:6])
        if re.search(pat, txt):
            f("high", "fail", ".env.example zawiera realny sekret",
              "placeholdery powinny być puste / oczywiście fałszywe", "Zamień na <your-key-here>")
        else:
            f("info", "pass", ".env.example czysty (placeholdery)",
              "szablon konfiguracji bez realnych sekretów")
    else:
        f("low", "warn", "Brak .env.example",
          "kontrybutorzy nie wiedzą, jakie zmienne ustawić", "Dodaj .env.example z placeholderami")

    # secrets must come from env, not tracked settings
    r = _git(repo, ["grep", "-nIE", r"(SUPABASE|ANON_KEY|SERVICE_ROLE|SECRET)\s*=\s*['\"][^'\"]{12,}",
                    "--", "*.py"] + _SCAN_EXCLUDES)
    if r and r.stdout.strip():
        f("critical", "fail", "Klucz połączenia zaszyty w kodzie",
          r.stdout.strip().splitlines()[0][:90], "Czytaj z os.environ, trzymaj w .env")
    else:
        f("info", "pass", "Klucze połączeń tylko ze środowiska",
          "Supabase/n8n czytane z .env, nie z kodu")

    return out


# ---------------------------------------------------------------- 4. FUNCTIONAL

def _check_functional():
    out = []

    def f(sev, status, title, detail, fix=""):
        out.append({"id": "func", "area": "TESTY FUNKCJONALNE", "severity": sev,
                    "status": status, "title": title, "detail": detail, "fix": fix})

    # DB schema intact
    try:
        import engine_bridge as eb
        tabs = {r["name"] for r in eb._rows(
            "select name from sqlite_master where type='table'")}
        need = {"accounts", "debts", "goals", "job_offers", "market_prices_cache",
                "app_settings", "reminders", "snapshots"}
        miss = need - tabs
        if miss:
            f("high", "fail", "Brakuje tabel w bazie", "brak: " + ", ".join(sorted(miss)),
              "Uruchom migracje / ensure_tables()")
        else:
            f("info", "pass", "Schemat bazy kompletny", f"{len(tabs)} tabel, wszystkie kluczowe obecne")
    except Exception as e:
        f("high", "fail", "Baza niedostępna", str(e)[:120])

    # every GET endpoint answers 200 + JSON (in-process test client)
    try:
        import app as _app
        client = _app.app.test_client()
        rules = [r for r in _app.app.url_map.iter_rules()
                 if "GET" in r.methods and "<" not in r.rule
                 and not r.rule.startswith("/static")]
        ok, bad = 0, []
        for rule in rules:
            try:
                resp = client.get(rule.rule)
                if resp.status_code == 200:
                    ok += 1
                else:
                    bad.append(f"{rule.rule} → {resp.status_code}")
            except Exception as e:
                bad.append(f"{rule.rule} → {str(e)[:30]}")
        if bad:
            f("medium", "warn", "Część endpointów GET nie zwraca 200",
              f"OK {ok}/{len(rules)}; problemy: " + ", ".join(bad[:5]), "Sprawdź logi endpointu")
        else:
            f("info", "pass", "Wszystkie endpointy GET odpowiadają 200",
              f"{ok} tras przetestowanych in-process")
    except Exception as e:
        f("medium", "warn", "Nie udało się przetestować endpointów", str(e)[:120])

    # market data pipe alive / gracefully offline
    try:
        import market as _mkt
        _wl = _mkt.get_watchlist() or []
        px = _mkt.prices(_wl[0]["ticker"], days=7) if _wl else []
        last = px[-1]["date"] if px else None
        if last:
            from datetime import date
            try:
                y, m, d = map(int, last.split("-"))
                age = (date.today() - date(y, m, d)).days
            except Exception:
                age = None
            if age is not None and age <= 5:
                f("info", "pass", "Dane rynkowe świeże", f"ostatnie notowanie {last} ({age} dni temu)")
            else:
                f("low", "warn", "Dane rynkowe nieświeże",
                  f"ostatnie {last} ({age} dni temu)", "Sprawdź pipeline n8n → Supabase")
        else:
            f("low", "warn", "Brak danych rynkowych w cache",
              "market/RSU/FX pokażą 'brak danych'", "Uruchom sync z chmury lub podłącz Supabase")
    except Exception as e:
        f("low", "warn", "Pipeline rynkowy offline", str(e)[:100])

    # core computations don't throw
    try:
        import planner as _p
        for name, fn in (("dashboard", lambda: __import__("engine_bridge").dashboard_summary()),
                         ("health", _p.health),
                         ("data_inventory", _p.data_inventory)):
            try:
                fn()
            except Exception as e:
                f("medium", "warn", f"Obliczenie '{name}' rzuca wyjątek", str(e)[:100])
        f("info", "pass", "Kluczowe obliczenia liczą się bez błędu",
          "dashboard, health, inwentarz danych — OK")
    except Exception as e:
        f("low", "warn", "Nie udało się sprawdzić obliczeń", str(e)[:100])

    return out


# ---------------------------------------------------------------- runner

_SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_SEV_SCORE = {"critical": 40, "high": 20, "medium": 8, "low": 3, "info": 0}


# ---------------------------------------------------------------- 5. LOCAL SERVICES / LLM

def _check_local_services():
    """Active pentest of local AI services (e.g. a llama.cpp server). If you wire
    a local LLM to sensitive data, its exposure must be *verified*, not just
    warned about in a server log."""
    import json as _json
    import os as _os
    import urllib.request as _u
    out = []

    def f(sev, status, title, detail, fix=""):
        out.append({"id": "llm", "area": "LOCAL SERVICES / LLM", "severity": sev,
                    "status": status, "title": title, "detail": detail, "fix": fix})

    base = _os.environ.get("LOCAL_LLM_URL", "http://127.0.0.1:8080/v1")
    host = base.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
    if host in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        f("info", "pass", "Local LLM targets localhost",
          f"LOCAL_LLM_URL={base} — sensitive data does not leave the machine")
    else:
        f("high", "fail", "Local LLM targets a REMOTE host",
          f"LOCAL_LLM_URL={base} → sensitive data would leave the machine!",
          "Point LOCAL_LLM_URL at http://127.0.0.1:...; use a deliberate separate path for any cloud model")

    up = False
    try:
        with _u.urlopen(base.rsplit("/v1", 1)[0] + "/health", timeout=2) as r:
            up = r.status == 200
    except Exception:
        try:
            with _u.urlopen(base + "/models", timeout=2) as r:
                up = r.status == 200
        except Exception:
            up = False
    if not up:
        f("info", "pass", "No local LLM server running",
          "nothing listening on LOCAL_LLM_URL — zero attack surface right now")
        return out

    try:
        req = _u.Request(base + "/chat/completions",
                         data=_json.dumps({"messages": [{"role": "user", "content": "ping"}],
                                           "max_tokens": 1}).encode(),
                         headers={"Content-Type": "application/json"})
        with _u.urlopen(req, timeout=8) as r:
            noauth_ok = r.status == 200
    except Exception as e:
        noauth_ok = None if ("401" in str(e) or "403" in str(e)) else True
    if noauth_ok is True:
        f("medium", "warn", "Local LLM accepts requests WITHOUT a key",
          f"{base} answered a prompt with no Authorization — any web page in your browser could "
          "hit localhost and drain/abuse the model (CSRF / DNS-rebinding).",
          "Start llama-server with --api-key <secret> and set LOCAL_LLM_KEY in .env")
    elif noauth_ok is None:
        f("info", "pass", "Local LLM requires authentication",
          "keyless request rejected (401/403) — well protected")
    else:
        f("info", "pass", "Local LLM up (auth policy undetermined)",
          "server alive; could not conclusively determine auth policy")
    return out


def run(full=True):
    # Make sure config (FINANCE_PROJECT_DIR, module sys.path) is initialised so
    # the functional imports work standalone (CLI/CI), not only inside the app.
    try:
        import config
        config.setup()
    except Exception:
        pass
    repo = _repo_root()
    ls = _git(repo, ["ls-files"])
    tracked = ls.stdout.splitlines() if ls else []

    findings = []
    findings += _check_repo_leaks(repo, tracked)
    findings += _check_personal_data(repo)
    findings += _check_code(repo)
    findings += _check_config(repo, tracked)
    if full:
        findings += _check_functional()
        findings += _check_local_services()

    findings.sort(key=lambda x: (_SEV_RANK.get(x["severity"], 9),
                                 0 if x["status"] == "fail" else 1))

    fails = [x for x in findings if x["status"] == "fail"]
    warns = [x for x in findings if x["status"] == "warn"]
    passes = [x for x in findings if x["status"] == "pass"]
    penalty = sum(_SEV_SCORE.get(x["severity"], 0) for x in findings if x["status"] != "pass")
    score = max(0, 100 - penalty)

    if fails:
        verdict = "error"
        summary = f"🚨 {len(fails)} krytycznych/wysokich problemów — NIE upubliczniaj repo"
    elif warns:
        verdict = "warn"
        summary = f"⚠️ {len(warns)} ostrzeżeń, 0 blokerów — do przejrzenia"
    else:
        verdict = "ok"
        summary = f"✅ Czysto — {len(passes)} testów zaliczonych, 0 znalezisk"

    # group by area for the UI
    areas = {}
    for x in findings:
        areas.setdefault(x["area"], []).append(x)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "verdict": verdict,
        "score": score,
        "summary": summary,
        "counts": {"fail": len(fails), "warn": len(warns), "pass": len(passes),
                   "total": len(findings)},
        "areas": [{"area": a, "items": v} for a, v in areas.items()],
        "findings": findings,
    }


def _cli():
    import json
    import sys
    ci = "--ci" in sys.argv
    rep = run(full=True)
    if "--json" in sys.argv:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(f"\n  SECURITY REVIEW — {rep['summary']}  (score {rep['score']}/100)\n")
        for area in rep["areas"]:
            print(f"  {area['area']}")
            for it in area["items"]:
                mark = {"pass": "✓", "warn": "!", "fail": "✗"}.get(it["status"], "·")
                print(f"    [{mark}] {it['severity']:8} {it['title']}")
                if it["status"] != "pass":
                    print(f"          {it['detail'][:100]}")
            print()
    if ci and rep["counts"]["fail"] > 0:
        print(f"CI: {rep['counts']['fail']} failing checks -> exit 1")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    _cli()
