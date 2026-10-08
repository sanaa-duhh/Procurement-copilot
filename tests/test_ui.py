"""Interaction checks: a model run requires a click; reviews and browsing do not bill."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ui import review, runs

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(autouse=True)
def mock_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("COPILOT_HISTORY_PATH", str(tmp_path/"analyses.sqlite3"))


@pytest.fixture
def calls(monkeypatch):
    actual = runs.handle_request_payload
    recorded = []
    def run(request, **kwargs):
        recorded.append((dict(request), kwargs))
        return actual(request, **kwargs)
    monkeypatch.setattr(runs, "handle_request_payload", run)
    return recorded


def app():
    return AppTest.from_file(APP, default_timeout=60).run()


def test_analysis_requires_explicit_click_and_renders_review(calls):
    at = app()
    assert not at.exception
    assert at.title[0].value == "Review a purchase"
    assert calls == []
    at.button(key="analyse").click().run()
    assert not at.exception
    assert len(calls) == 1
    assert at.session_state["decision"].human_review_required
    assert {"Evidence", "Human review", "Run details"} <= {t.label for t in at.tabs}
    assert any("Required approvals" in m.value for m in at.markdown)


def test_saving_review_requires_name_and_never_reruns_model(calls, monkeypatch, tmp_path):
    actual_record = review.record_review
    log = tmp_path / "reviews.jsonl"
    monkeypatch.setattr(review, "record_review", lambda path, *args, **kwargs: actual_record(log, *args, **kwargs))
    at = app()
    at.button(key="analyse").click().run()
    next(b for b in at.button if b.label == "Save review").click().run()
    assert any("reviewer name" in e.value for e in at.error)
    next(t for t in at.text_input if t.label == "Reviewer name").set_value("Sanaa")
    next(b for b in at.button if b.label == "Save review").click().run()
    assert not at.exception
    assert any("Saved locally" in s.value for s in at.success)
    next(b for b in at.button if b.label == "Save review").click().run()
    assert len(log.read_text().splitlines()) == 1
    assert len(calls) == 1


def test_architecture_change_invalidates_previous_decision_without_running(calls):
    at = app()
    at.button(key="analyse").click().run()
    at.radio(key="architecture").set_value("staged").run()
    assert not at.exception
    with pytest.raises(KeyError):
        at.session_state["decision"]
    assert len(calls) == 1


def test_request_change_invalidates_previous_decision_without_running(calls):
    at = app()
    at.button(key="analyse").click().run()
    at.selectbox(key="sample_request").set_value("REQ-1007").run()
    assert not at.exception
    with pytest.raises(KeyError):
        at.session_state["decision"]
    assert len(calls) == 1


def test_editing_new_request_invalidates_result_without_running(calls):
    at = app()
    at.radio(key="request_source").set_value("New request").run()
    at.button(key="analyse").click().run()
    assert at.session_state["decision"].next_action == "request_clarification"
    at.text_input(key="new_product").set_value("Updated product").run()
    assert not at.exception
    with pytest.raises(KeyError):
        at.session_state["decision"]
    assert len(calls) == 1


def test_browsing_comparison_does_not_run_analysis_or_clear_existing_result(calls):
    at = app()
    at.selectbox(key="comparison_case").set_value("PUB-01").run()
    assert not at.exception
    assert calls == []
    at.button(key="analyse").click().run()
    run_id = at.session_state["decision"].run_id
    at.selectbox(key="comparison_case").set_value("SYN-17").run()
    assert not at.exception
    assert at.session_state["decision"].run_id == run_id
    assert len(calls) == 1


def test_missing_live_key_disables_analysis(monkeypatch, calls):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    at = app()
    assert not at.exception
    assert at.button(key="analyse").disabled
    assert any("configure OPENAI_API_KEY" in w.value for w in at.warning)
    assert calls == []


def test_theme_switch_preserves_analysis_and_request_without_model_calls(calls):
    at = app()
    assert at.toggle(key="light_mode").value is False
    at.toggle(key="light_mode").set_value(True).run()
    assert not at.exception
    assert calls == []
    at.button(key="analyse").click().run()
    run_id = at.session_state["decision"].run_id
    request_id = at.selectbox(key="sample_request").value
    at.toggle(key="light_mode").set_value(False).run()
    assert not at.exception
    assert at.session_state["decision"].run_id == run_id
    assert at.selectbox(key="sample_request").value == request_id
    assert len(calls) == 1


def test_failed_rerun_does_not_leave_an_old_recommendation(monkeypatch, calls):
    at = app()
    at.button(key="analyse").click().run()
    def fail(*args, **kwargs):
        raise RuntimeError("simulated service error")
    monkeypatch.setattr(runs, "handle_request_payload", fail)
    at.button(key="analyse").click().run()
    assert not at.exception
    with pytest.raises(KeyError):
        at.session_state["decision"]
    assert any("No new recommendation was saved" in e.value for e in at.error)


def test_history_survives_a_new_session_and_explicit_rerun_keeps_both(calls):
    first = app()
    first.button(key="analyse").click().run()
    original = first.session_state["decision"].run_id
    second = app()
    assert len(calls) == 1
    second.button(key="view_saved").click().run()
    assert not second.exception
    assert second.session_state["decision"].run_id == original
    assert len(calls) == 1
    second.button(key="analyse").click().run()
    assert second.session_state["decision"].run_id != original
    assert len(calls) == 2
    assert len(runs.store(Path(APP).parent).list_runs()) == 2


def test_historical_benchmark_opens_without_calls_and_requires_fresh_review(calls):
    at = app()
    at.button(key="view_saved").click().run()
    assert not at.exception
    assert calls == []
    assert at.session_state["decision_record"].origin == "benchmark"
    assert not any(b.label == "Save review" for b in at.button)
    assert any("Historical result" in w.value for w in at.warning)


def test_configuration_change_makes_saved_result_historical(monkeypatch, calls):
    at = app()
    at.button(key="analyse").click().run()
    monkeypatch.setenv("LLM_EFFORT", "high")
    at.run()
    at.button(key="view_saved").click().run()
    assert not at.exception
    assert any("Historical result" in w.value for w in at.warning)
    assert not any(b.label == "Save review" for b in at.button)
    assert len(calls) == 1


def test_free_text_requester_is_preserved_and_unknown_identity_cannot_be_verified(calls):
    at = app()
    at.radio(key="request_source").set_value("New request").run()
    at.text_input(key="new_requester").set_value("Sanaa Newperson").run()
    at.text_input(key="new_department").set_value("Finance").run()
    at.button(key="analyse").click().run()
    assert not at.exception
    request = calls[0][0]
    assert request["requester_name"] == "Sanaa Newperson"
    assert request["requester_id"] == ""
    assert request["declared_department"] == "Finance"
    assert any("employee record" in missing for missing in at.session_state["decision"].missing_information)
    assert at.session_state["decision"].next_action == "request_clarification"


def test_comparison_runs_only_missing_design_and_changes_with_request(calls):
    at = app()
    at.button(key="analyse").click().run()
    original = at.session_state["decision"].run_id
    at.button(key="compare_request").click().run()
    assert not at.exception
    assert [kwargs["architecture"] for _, kwargs in calls] == ["single", "staged"]
    pair = at.session_state["comparison_pair"]["runs"]
    assert pair["single"].run_id == original
    assert pair["staged"] is not None
    at.toggle(key="light_mode").set_value(True).run()
    assert len(calls) == 2
    at.selectbox(key="sample_request").set_value("REQ-1007").run()
    assert at.button(key="compare_request").label == "Compare this request"
    assert len(calls) == 2


def test_comparison_partial_failure_retains_success_and_retries_only_missing(monkeypatch, calls):
    actual = runs.handle_request_payload
    def fail_staged(request, *, architecture):
        if architecture == "staged":
            raise RuntimeError("simulated staged failure")
        return actual(request, architecture=architecture)
    monkeypatch.setattr(runs, "handle_request_payload", fail_staged)
    at = app()
    at.button(key="compare_request").click().run()
    assert not at.exception
    original = at.session_state["comparison_pair"]["runs"]["single"].run_id
    assert at.session_state["comparison_pair"]["runs"]["staged"] is None
    assert any("comparison is incomplete" in e.value for e in at.error)
    monkeypatch.setattr(runs, "handle_request_payload", actual)
    at.button(key="compare_request").click().run()
    assert not at.exception
    assert at.session_state["comparison_pair"]["runs"]["single"].run_id == original
    assert [kwargs["architecture"] for _, kwargs in calls] == ["single", "staged"]


def test_storage_failure_keeps_result_available_and_reports_unsaved(monkeypatch, calls):
    def fail(*args):
        raise OSError("disk unavailable")
    monkeypatch.setattr(runs.RunStore, "save", fail)
    at = app()
    at.button(key="analyse").click().run()
    assert not at.exception
    assert at.session_state["decision"].run_id
    assert any("could not be saved to disk" in w.value for w in at.warning)
    assert len(calls) == 1


def test_fresh_comparison_failure_cannot_leave_old_review_result(monkeypatch, calls):
    at = app()
    at.button(key="compare_request").click().run()
    assert at.session_state["decision"].run_id
    actual = runs.handle_request_payload
    def fail_single(request, *, architecture):
        if architecture == "single":
            raise RuntimeError("simulated fresh single failure")
        return actual(request, architecture=architecture)
    monkeypatch.setattr(runs, "handle_request_payload", fail_single)
    at.button(key="compare_request").click().run()
    assert not at.exception
    assert at.session_state["comparison_pair"]["runs"]["single"] is None
    assert at.session_state["comparison_pair"]["runs"]["staged"] is not None
    with pytest.raises(KeyError):
        at.session_state["decision"]
