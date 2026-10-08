"""Drive the Streamlit product UI headlessly with the scripted mock model."""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(autouse=True)
def mock_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")


def test_ui_renders_request_evidence_and_recommendation():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "Procurement Request Copilot"
    at.sidebar.button[0].click().run()          # Run analysis
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "Approvals required" in body
    assert "Next step" in body
    assert any("Evidence" in s.value for s in at.subheader)
    assert len(at.dataframe) == 1               # evidence table rendered


def test_ui_human_action_requires_reviewer_name():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.button[0].click().run()
    form_button = [b for b in at.button if b.label == "Record decision"][0]
    form_button.click().run()
    assert any("reviewer name is required" in e.value for e in at.error)


def test_changing_architecture_hides_old_decision():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.button[0].click().run()
    assert len(at.dataframe) == 1
    at.sidebar.radio[0].set_value("staged").run()
    assert not at.exception
    assert len(at.dataframe) == 0


def test_editing_same_new_request_id_hides_old_decision():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.radio[1].set_value("New request").run()
    [b for b in at.sidebar.button if b.label == "Run analysis"][0].click().run()
    assert len(at.dataframe) == 1
    [t for t in at.sidebar.text_input if t.label == "Product name"][0].set_value("Changed product")
    [b for b in at.sidebar.button if b.label == "Use this request"][0].click().run()
    assert not at.exception
    assert len(at.dataframe) == 0
