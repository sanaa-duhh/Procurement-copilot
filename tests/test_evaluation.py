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


def test_replication_panel_reads_the_saved_three_repeat_run():
    from pathlib import Path

    from ui.comparison import load_replication

    rows = load_replication(Path(__file__).resolve().parents[1])
    assert rows is not None
    by_metric = {r[0]: r[1:] for r in rows}
    assert by_metric["Final decision passes"] == ["54/54", "47/54"]
    assert by_metric["Raw draft passes, before corrections"] == ["54/54", "42/54"]


def test_replication_panel_is_hidden_when_results_are_missing(tmp_path):
    from ui.comparison import load_replication

    assert load_replication(tmp_path) is None


def test_replay_reruns_the_policy_layer_on_saved_drafts_without_tool_calls():
    import json
    from collections import Counter
    from pathlib import Path

    from replay import replay_record

    root = Path(__file__).resolve().parents[1]
    cases = {c["case_id"]: c for c in json.loads((root / "evals" / "cases.json").read_text())}
    records = [json.loads(line) for line in (root / "evals/results/openai-repeats-20261011/decisions.jsonl").read_text().splitlines() if line.strip()]
    passed = Counter(r["architecture"] for r in map(lambda rec: replay_record(rec, cases[rec["case_id"]]), records) if r["all_correct"])
    assert passed == {"single": 54, "staged": 52}
