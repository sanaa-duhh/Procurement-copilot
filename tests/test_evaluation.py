"""Ensure the comparison measures failures instead of quietly excluding them."""
from evals.run_evals import load_cases, run_case, summarise
from src.llm import MockClient
from test_reliability import BrokenClient


def test_model_outage_is_not_counted_as_end_to_end_success():
    case = next(c for c in load_cases("all") if c["case_id"] == "EXT-10")
    row = run_case(case, "single", BrokenClient("unavailable"), 1)
    assert row["all_correct"] is True  # safe deterministic fallback
    assert row["end_to_end_success"] is False
    assert row["model_success"] is False
    assert row["raw_all_correct"] is False
    assert row["llm_calls"] == 1


def test_unknown_model_cost_is_unknown_not_free():
    case = next(c for c in load_cases("all") if c["case_id"] == "EXT-10")
    assert run_case(case, "single", MockClient(), 1)["est_cost_usd"] is None


def test_crashes_remain_in_quality_denominators(monkeypatch):
    case = next(c for c in load_cases("all") if c["case_id"] == "EXT-10")
    good = run_case(case, "single", MockClient(), 1)
    def crash(*args, **kwargs):
        raise RuntimeError("fixture crash")
    monkeypatch.setattr("evals.run_evals.handle_request_payload", crash)
    bad = run_case(case, "single", MockClient(), 2)
    summary = summarise([good, bad], ["single"])["single"]
    assert summary["all_correct_pct"] == 50
    assert summary["raw_all_correct_pct"] == 50
    assert summary["next_action_correct_pct"] == 50
    assert summary["end_to_end_success_pct"] == 50
