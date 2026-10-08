"""Application run coordination; no analysis is triggered by a read operation."""
import os
from pathlib import Path
import sqlite3

import streamlit as st

from src.audit import request_fingerprint
from src.solution import handle_request_payload
from ui.history import RunStore, new_run

STORAGE_ERRORS = (OSError, sqlite3.Error, ValueError)


def store(root: Path) -> RunStore:
    return RunStore(Path(os.getenv("COPILOT_HISTORY_PATH", str(root/"logs/analyses.sqlite3"))))


def context(request: dict, config: dict, architecture: str) -> tuple:
    return request_fingerprint(request), architecture, request_fingerprint(config)


def saved(root: Path, request=None, architecture=None):
    try:
        return store(root).list_runs(request, architecture)
    except STORAGE_ERRORS:
        st.warning("Saved analyses could not be read. You can still run an analysis; check the local history store.")
        return []


def latest(root: Path, request: dict, config: dict, architecture: str):
    key = context(request, config, architecture)
    if key in st.session_state.get("session_runs", {}):
        return st.session_state["session_runs"][key]
    return next((r for r in saved(root, request, architecture) if r.config == config), None)


def execute(root: Path, request: dict, config: dict, architecture: str):
    st.session_state.pop("comparison_pair", None)
    decision = handle_request_payload(request, architecture=architecture)
    run = new_run(request, config, decision)
    # Persist before touching Streamlit state: a pending UI rerun must not
    # discard a model result that has already completed.
    try:
        store(root).save(run)
    except STORAGE_ERRORS:
        st.session_state["history_error"] = "This analysis is available in this session, but could not be saved to disk. Download it before closing the page."
    else:
        st.session_state.pop("history_error", None)
    st.session_state.setdefault("session_runs", {})[context(request, config, architecture)] = run
    return run


def activate(run, current_context: tuple, *, loaded: bool = False) -> None:
    st.session_state["decision"] = run.decision
    st.session_state["decision_context"] = current_context
    st.session_state["decision_record"] = run
    st.session_state["decision_loaded"] = loaded
    st.session_state.pop("saved_review", None)
