#!/usr/bin/env python3
"""Regenerate the README screenshots (Ratios, forecast cone, forecast calibration).

Builds the static demo (demo/build_demo.py: throwaway DB with the fake "Alex Demo"
persona, no data from the machine it runs on), serves it from a temp dir on loopback
and captures the cards headless. Nothing private can end up in the PNGs.

Setup (once):
    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt playwright
    .venv/bin/playwright install chromium
Usage:
    .venv/bin/python scripts/screenshots.py [--out docs/screenshots] [--dist DIR]
Needs network for the public Yahoo quotes the demo build pulls (cone and calibration
are empty without them).
"""
import argparse
import functools
import http.server
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent

# file name, hash route, heading text of the card to crop (None = whole view)
SHOTS = [
    ("ratios.png", "metrics", None),
    ("forecast-cone.png", "forecasts", "Net-worth trajectory"),
    ("forecast-calibration.png", "forecasts", "Forecast calibration"),
]


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    ap.add_argument("--dist", help="reuse an already built demo dir instead of building one")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="kist-shots-") as tmp:
        dist = Path(args.dist) if args.dist else Path(tmp) / "dist"
        if not args.dist:
            subprocess.run([sys.executable, str(ROOT / "demo" / "build_demo.py"), "--out", str(dist)],
                           check=True)
        srv = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(dist)))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}/"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
                for name, route, heading in SHOTS:
                    page.goto(base + "#" + route)
                    page.reload()  # hash-only navigation does not re-render a cold page reliably
                    page.wait_for_load_state("networkidle")
                    if heading:
                        target = page.locator(".card").filter(
                            has=page.locator("h3", has_text=heading)).last
                    else:
                        target = page.locator("#view, main").first
                    target.wait_for(timeout=15000)
                    page.wait_for_timeout(1200)  # Chart.js animation
                    # the static demo's "variant isn't baked" toast would float over the card
                    page.add_style_tag(content="#demoToast{display:none !important}")
                    target.screenshot(path=str(out / name))
                    print("saved", out / name)
                browser.close()
        finally:
            srv.shutdown()


if __name__ == "__main__":
    main()
