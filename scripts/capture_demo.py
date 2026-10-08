"""Capture the running scripted demo for the README; no model calls.

Start `uv run python run_local.py --demo --api-port 8002`, then:
uv run --with playwright python scripts/capture_demo.py
Uses an installed Chrome; screenshots are explicitly labelled as demo evidence.
"""
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument("--chrome", default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    parser.add_argument("--output", default="docs/images/demo-conflicting-vendor.png")
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.chrome)
        page = browser.new_page(viewport={"width": 1800, "height": 1150}, device_scale_factor=1)
        page.goto(args.url)
        page.get_by_text("scripted mock", exact=False).wait_for(timeout=30000)
        page.get_by_role("combobox").first.click()
        page.get_by_text("REQ-1007 · SignalWatch Advanced", exact=True).click()
        page.get_by_role("button", name="Run analysis", exact=True).click()
        page.get_by_role("heading", name="Escalate for manual review", exact=True).wait_for(timeout=30000)
        page.screenshot(path=str(output), full_page=True)
        print(f"Saved scripted-demo screenshot: {output}")
        browser.close()


if __name__ == "__main__":
    main()
