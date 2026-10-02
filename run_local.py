"""One-command local start: vendor-risk mock API + the copilot UI.

    uv run python run_local.py            # API on :8001, UI on :8501
    uv run python run_local.py --no-ui    # API only (for the evaluation scripts)
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)

API_HOST, API_PORT = "127.0.0.1", int(os.getenv("VENDOR_RISK_PORT", "8001"))
UI_PORT = int(os.getenv("UI_PORT", "8501"))


def start(cmd: list[str]) -> subprocess.Popen:
    return subprocess.Popen(cmd, cwd=ROOT)


def wait_for_api(url: str, proc: subprocess.Popen, timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"Vendor-risk API exited during startup with code {proc.returncode}. "
                f"Is port {API_PORT} already in use?"
            )
        try:
            if requests.get(url, timeout=0.5).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Vendor-risk API did not become ready within {timeout_seconds:.0f}s: {url}")


def _handle_termination(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def credential_notice() -> None:
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    if provider == "mock":
        print("LLM_PROVIDER=mock: the copilot runs on the scripted stand-in model (no credentials needed).")
    elif provider == "anthropic" and not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        print("Note: ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add it, or set LLM_PROVIDER=mock to try the UI offline.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-ui", action="store_true", help="start only the vendor-risk API")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _handle_termination)
    procs: list[subprocess.Popen] = []
    try:
        print(f"Starting vendor-risk API on http://{API_HOST}:{API_PORT} ...")
        api_proc = start([sys.executable, "-m", "uvicorn", "mock_api.app:app", "--host", API_HOST, "--port", str(API_PORT), "--log-level", "warning"])
        procs.append(api_proc)
        wait_for_api(f"http://{API_HOST}:{API_PORT}/health", api_proc)
        print("Vendor-risk API is ready.")
        credential_notice()

        if not args.no_ui:
            try:
                __import__("streamlit")
            except ImportError:
                print("Streamlit is not installed (uv sync / pip install -r requirements.txt). API keeps running; Ctrl+C to stop.")
            else:
                print(f"Starting copilot UI on http://127.0.0.1:{UI_PORT} ...")
                procs.append(start([sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(UI_PORT), "--server.headless", "true"]))

        while True:
            time.sleep(1)
            for proc in procs:
                if proc.poll() is not None:
                    raise RuntimeError(f"A local process exited with code {proc.returncode}")
    except KeyboardInterrupt:
        print("\nStopping local services ...")
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
