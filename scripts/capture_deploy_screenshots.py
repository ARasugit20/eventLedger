#!/usr/bin/env python3
"""Capture /health JSON and /docs UI screenshots for deploy evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("EVENTLEDGER_URL", "").rstrip("/"),
    )
    parser.add_argument(
        "--output-dir",
        default="docs/deploy_evidence",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.base_url:
        print("ERROR: pass --base-url or set EVENTLEDGER_URL", file=sys.stderr)
        return 2

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=args.base_url, timeout=30.0, follow_redirects=True) as client:
        health_resp = client.get("/health")
        health_resp.raise_for_status()
        (out / "health_response.json").write_text(
            json.dumps(health_resp.json(), indent=2) + "\n",
            encoding="utf-8",
        )

        docs_resp = client.get("/docs")
        docs_resp.raise_for_status()
        (out / "docs_page.html").write_text(docs_resp.text, encoding="utf-8")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed; saved health JSON and docs HTML only", file=sys.stderr)
        return 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{args.base_url}/health", wait_until="networkidle")
        page.screenshot(path=str(out / "health.png"), full_page=True)
        page.goto(f"{args.base_url}/docs", wait_until="networkidle")
        page.screenshot(path=str(out / "docs.png"), full_page=True)
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
