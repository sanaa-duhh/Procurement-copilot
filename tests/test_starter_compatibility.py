"""The supplied data, API and public harness must survive our refactoring."""
import hashlib
import json
from pathlib import Path

from src.contracts import ProcurementDecision
from src.data_access import get_request
from src.llm import MockClient
from src.solution import handle_request_payload

ROOT = Path(__file__).resolve().parents[1]


def test_preserved_starter_files_match_recorded_original_hashes():
    manifest = json.loads((ROOT / "docs" / "starter_manifest.json").read_text())
    for entry in manifest["files"]:
        if entry["handling"] == "preserved":
            assert hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest() == entry["sha256"], entry["path"]


def test_extended_decision_preserves_the_original_output_contract():
    manifest = json.loads((ROOT / "docs" / "starter_manifest.json").read_text())
    assert ProcurementDecision.model_json_schema() == manifest["procurement_decision_schema"]
    for architecture in ("single", "staged"):
        decision = handle_request_payload(get_request("REQ-1010"), architecture=architecture, llm=MockClient())
        ProcurementDecision.model_validate(decision.model_dump())
