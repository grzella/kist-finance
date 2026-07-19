# Security Policy

## Reporting a vulnerability

Please use **GitHub's private vulnerability reporting** for this repository
(Security tab → "Report a vulnerability"). Do **not** open a public issue for
security problems, and never include real financial data or secrets in a report.

You can expect an initial response within a few days. Fixes ship as regular
commits/releases; credit is given unless you prefer otherwise.

## Scope & posture

Kist is a **local-first, single-user** app: it binds to `127.0.0.1`, stores data
in a local SQLite file outside the repo, and has no accounts or server-side
components. The most relevant vulnerability classes are therefore: anything that
makes the app listen beyond localhost, code execution via crafted local data,
secrets/PII leaking into the repository, and CSRF/DNS-rebinding against the
local server or a local LLM.

## What already guards the repo

- `server/security_review.py` — secret scan of the tree **and full git
  history**, static dangerous-pattern checks, maintainer personal-data audit,
  config hygiene, endpoint smoke tests and an active probe of any local LLM
  server; runs on every push/PR + weekly in CI and is available from the
  Control Center.
- Scanner-efficacy tests plant synthetic leaks and assert they are caught.
- CI enforces a coverage floor and a bandit gate; CodeQL and Dependabot are on.

## Threat model — the localhost assumption (read before self-hosting)

The API has **no authentication by design**: the security model is "one user, on
their own machine, over loopback." That assumption is what keeps a keyless,
open API safe. **Do not expose it beyond `127.0.0.1`** (no `0.0.0.0` bind, no
reverse proxy to the public internet, no port-forward) — if you do, anyone who
can reach the port has full, unauthenticated access to your finances. If you
need remote access, put it behind a VPN or an authenticating proxy; the app
itself does not authenticate.

Because a browser can reach `127.0.0.1` on your behalf, the app defends the two
attacks that don't need your machine, only your browser:

- **DNS rebinding** — a `before_request` guard rejects any request whose `Host`
  header isn't loopback, so a malicious page that rebinds its domain to
  `127.0.0.1` is refused.
- **CSRF** — state-changing (`POST`/`PUT`/`DELETE`) API calls with a non-loopback
  `Origin`/`Referer` are rejected, so another site can't drive your app.
- Defense in depth: a strict **Content-Security-Policy** (`script-src 'self'`,
  no inline scripts) neutralizes injected markup even if crafted data — e.g.
  market text synced from an external source — reaches the DOM unescaped; plus
  `X-Frame-Options: DENY` and `nosniff`.

The `security_review` suite **actively pentests these guards** (a forged `Host`
and a cross-origin write must both return 403) so a regression fails CI.

## Not in scope

- Multi-user / shared-host deployments (see above — add auth yourself).
- The security of your external integrations (Supabase, n8n, your cloud LLM
  key): treat their data as untrusted input; the app escapes it and frames RAG
  content to the model as data, not instructions, but you own those services.
