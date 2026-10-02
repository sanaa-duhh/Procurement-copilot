from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import src  # noqa: E402,F401  (loads .env)

REQUIRED_MODULES = [
    "fastapi",
    "uvicorn",
    "pydantic",
    "pandas",
    "requests",
    "dotenv",
    "streamlit",
    "httpx",
    "anthropic",
]


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"[ OK ] {message}")


def check_python() -> None:
    if sys.version_info < (3, 11):
        fail(f"Python 3.11+ is required/recommended. Detected: {sys.version.split()[0]}")
    ok(f"Python {sys.version.split()[0]}")


def check_imports() -> None:
    missing: list[str] = []
    for module_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(module_name)
    if missing:
        fail(
            "Missing packages: "
            + ", ".join(missing)
            + ". Run: python -m pip install -r requirements.txt"
        )
    ok("Required starter packages import successfully")


def check_data() -> None:
    data = ROOT / "data"
    required = [
        "employees.csv",
        "department_budgets.csv",
        "software_catalog.csv",
        "vendors.csv",
        "purchase_history.csv",
        "requests.json",
        "vendor_risk.json",
        "procurement_policy.md",
    ]
    missing = [name for name in required if not (data / name).is_file()]
    if missing:
        fail("Missing data files: " + ", ".join(missing))

    with (data / "employees.csv").open(encoding="utf-8", newline="") as f:
        employees = list(csv.DictReader(f))
    with (data / "department_budgets.csv").open(encoding="utf-8", newline="") as f:
        budgets = list(csv.DictReader(f))
    with (data / "vendors.csv").open(encoding="utf-8", newline="") as f:
        vendors = list(csv.DictReader(f))
    requests = json.loads((data / "requests.json").read_text(encoding="utf-8"))
    risk = json.loads((data / "vendor_risk.json").read_text(encoding="utf-8"))

    employee_ids = {r["employee_id"] for r in employees}
    departments = {r["department"] for r in budgets}
    vendor_names = {r["vendor_name"] for r in vendors}

    if any(r["requester_id"] not in employee_ids for r in requests):
        fail("At least one request references an unknown employee")
    if any(int(r["annual_software_budget_usd"]) - int(r["committed_usd"]) != int(r["available_usd"]) for r in budgets):
        fail("Budget arithmetic is inconsistent")
    if any(r["vendor_name"] not in vendor_names for r in requests):
        fail("At least one request references a vendor missing from vendors.csv")
    if any(r["vendor_name"] not in risk for r in requests):
        fail("At least one request vendor is missing from vendor_risk.json")
    if any(next(e for e in employees if e["employee_id"] == r["requester_id"])["department"] not in departments for r in requests):
        fail("At least one requester department is missing from department_budgets.csv")

    ok(f"Dataset integrity checks passed ({len(requests)} requests, {len(vendors)} vendors)")


def check_contract_and_evals() -> None:
    from src.contracts import EvidenceItem, ProcurementDecision

    sample = ProcurementDecision(
        request_id="REQ-CHECK",
        recommendation="Manual review",
        evidence=[EvidenceItem(source="setup", finding="Contract validation works")],
        next_step="Continue implementation",
    )
    if sample.request_id != "REQ-CHECK":
        fail("ProcurementDecision contract validation failed")

    cases = json.loads((ROOT / "evals" / "public_cases.json").read_text(encoding="utf-8"))
    request_ids = {
        r["request_id"]
        for r in json.loads((ROOT / "data" / "requests.json").read_text(encoding="utf-8"))
    }
    bad_refs = [c["request_id"] for c in cases if c["request_id"] not in request_ids]
    if bad_refs:
        fail("Public eval references unknown request IDs: " + ", ".join(bad_refs))
    ok(f"Output contract + {len(cases)} public evaluation cases are valid")


def check_policy_engine() -> None:
    """The deterministic layer must agree with the policy on the public cases without any model."""
    from src import rules
    from src.data_access import get_request
    from src.telemetry import RunTelemetryCounter
    from src.tools import ToolRegistry
    from src.tools.policy import gather_evidence

    if rules.reference_date().isoformat() != "2026-09-30":
        fail(f"Policy reference date parsed as {rules.reference_date()}, expected 2026-09-30")
    registry = ToolRegistry(request=get_request("REQ-1005"), telemetry=RunTelemetryCounter())
    findings = rules.evaluate(gather_evidence(registry))
    if "budget_insufficient" not in findings.risk_flags or "Legal" not in findings.required_approvals:
        fail("Policy engine did not flag the budget shortfall / legal review on REQ-1005")
    ok("Deterministic policy engine checks passed")


def check_credentials() -> None:
    import os
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    if provider == "mock":
        ok("LLM_PROVIDER=mock (offline scripted model; evaluation results require a real provider)")
    elif os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"):
        ok(f"Anthropic credentials present (model {os.getenv('MODEL_NAME', 'claude-opus-5')})")
    else:
        print("[WARN] No ANTHROPIC_API_KEY in the environment or .env; the UI and evaluations need it (or LLM_PROVIDER=mock to try offline)")


def check_mock_api() -> None:
    from fastapi.testclient import TestClient
    from mock_api.app import app

    client = TestClient(app)
    health = client.get("/health")
    if health.status_code != 200 or health.json().get("status") != "ok":
        fail("Mock API health endpoint failed")
    known = client.get("/vendor-risk/BrandBoard")
    if known.status_code != 200 or known.json().get("security_review_status") != "not_completed":
        fail("Mock API known-vendor check failed")
    outage = client.get("/vendor-risk/NimbusAI")
    if outage.status_code != 503:
        fail("Mock API simulated-outage check failed")
    ok("Mock vendor-risk API checks passed")


def main() -> None:
    print("FDE Assessment 3 - starter pack pre-flight\n")
    check_python()
    check_imports()
    check_data()
    check_contract_and_evals()
    check_mock_api()
    check_policy_engine()
    check_credentials()
    print("\nPRE-FLIGHT PASSED")
    print("Next: uv run python run_local.py  (API on :8001, UI on :8501)")


if __name__ == "__main__":
    main()
