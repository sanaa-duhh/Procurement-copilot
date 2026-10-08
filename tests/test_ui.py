"""Interaction checks: a model run requires a click; reviews and browsing do not bill."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ui import review

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(autouse=True)
def mock_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")


@pytest.fixture
def calls(monkeypatch):
    actual = review.handle_request_payload
    recorded = []
    def run(request, **kwargs):
        recorded.append((dict(request), kwargs))
        return actual(request, **kwargs)
    monkeypatch.setattr(review, "handle_request_payload", run)
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
    monkeypatch.setattr(review, "handle_request_payload", fail)
    at.button(key="analyse").click().run()
    assert not at.exception
    with pytest.raises(KeyError):
        at.session_state["decision"]
    assert any("No new recommendation was saved" in e.value for e in at.error)
