from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.data_access import get_request
from src.solution import handle_request_payload
from ui.history import RunStore, benchmark_runs, configuration, new_run
from ui.intake import resolve_requester

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def record(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    request = get_request("REQ-1007")
    return new_run(request, configuration(ROOT, "mock", "mock"), handle_request_payload(request, "staged"))


def test_roundtrip_retains_original_evidence_trace_and_run_identity(tmp_path, record):
    path = tmp_path/"runs.sqlite3"
    RunStore(path).save(record)
    restored = RunStore(path).list_runs(record.request, "staged")[0]
    assert restored.run_id == record.run_id
    assert restored.decision.model_dump() == record.decision.model_dump()
    assert restored.decision.trace == record.decision.trace
    assert restored.config == record.config
    assert RunStore(path).list_runs(record.request, "single") == []
    assert RunStore(path).list_runs({**record.request, "annual_cost_usd": 100}) == []


def test_run_is_immutable_and_duplicate_saves_are_idempotent(tmp_path, record):
    store = RunStore(tmp_path/"runs.sqlite3")
    store.save(record)
    store.save(record)
    assert len(store.list_runs()) == 1
    record.decision.next_step = "different next step"
    with pytest.raises(ValueError, match="cannot be overwritten"):
        store.save(record)


def test_concurrent_saves_keep_one_complete_record(tmp_path, record):
    path = tmp_path/"runs.sqlite3"
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: RunStore(path).save(record), range(8)))
    assert len(RunStore(path).list_runs()) == 1


def test_mismatched_request_cannot_be_stored(tmp_path, record):
    record.request["annual_cost_usd"] = 1
    with pytest.raises(ValueError, match="does not match"):
        RunStore(tmp_path/"runs.sqlite3").save(record)


def test_analysis_identity_tracks_data_and_model_but_ignores_theme(tmp_path):
    (tmp_path/"data").mkdir()
    policy = tmp_path/"data/policy.md"
    policy.write_text("original")
    initial = configuration(tmp_path, "openai", "model-a")
    (tmp_path/"ui").mkdir()
    (tmp_path/"ui/styles.css").write_text("different colours")
    assert configuration(tmp_path, "openai", "model-a") == initial
    assert configuration(tmp_path, "openai", "model-b") != initial
    policy.write_text("changed policy")
    assert configuration(tmp_path, "openai", "model-a") != initial


def test_benchmark_history_requires_exact_request_and_keeps_provenance():
    request = get_request("REQ-1007")
    records = benchmark_runs(ROOT, request, "single")
    assert len(records) == 1
    assert records[0].origin == "benchmark"
    assert records[0].config["provider"] == "openai"
    assert benchmark_runs(ROOT, {**request, "annual_cost_usd": 1}, "single") == []


def test_names_are_resolved_exactly_with_id_and_ambiguity_checks():
    directory = {"E001": {"name": "Sarah Lee", "department": "Marketing"}}
    assert resolve_requester("  sarah   LEE ", "", directory)[0] == "E001"
    assert resolve_requester("Unknown Person", "", directory)[0] == ""
    assert resolve_requester("Unknown Person", "E001", directory)[0] == ""
    directory["E002"] = {"name": "Sarah Lee", "department": "Engineering"}
    assert resolve_requester("Sarah Lee", "", directory)[0] == ""
    assert resolve_requester("Sarah Lee", "E002", directory)[0] == "E002"
