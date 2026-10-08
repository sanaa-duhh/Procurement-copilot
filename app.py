"""Procurement review workspace and the saved architecture comparison.

Presentation lives in ui/. The starter-compatible analysis pipeline remains in
src/solution.py, shared by the application and the evaluation runner.
"""
import os
from pathlib import Path

import streamlit as st

from src.data_access import load_employees, load_requests
from src.llm import configured_model
from src.rules import reference_date
from ui import comparison, review
from ui.components import esc

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Procurement Copilot", page_icon=":material/fact_check:", layout="wide", initial_sidebar_state="collapsed")
st.set_option("client.toolbarMode", "minimal")
if "light_mode" not in st.session_state:
    st.session_state["light_mode"] = st.query_params.get("theme") == "light"


def remember_theme() -> None:
    # Keep the selected appearance when this URL is refreshed, per browser tab.
    st.query_params["theme"] = "light" if st.session_state["light_mode"] else "dark"


theme = "light" if st.session_state.get("light_mode", False) else "dark"
st.html(f"<style>{(ROOT/f'ui/themes/{theme}.css').read_text()}\n{(ROOT/'ui/styles.css').read_text()}</style>")

provider = os.getenv("LLM_PROVIDER", "openai")
model = configured_model(provider)
mode = "Scripted demo" if provider == "mock" else "Live OpenAI"
with st.container(key="app_header"):
    identity, appearance = st.columns([5, 1], vertical_alignment="center")
    with identity:
        st.html('<div class="brandbar"><div class="brand"><span class="brand-mark" aria-hidden="true">P</span><div>Procurement Copilot<div class="brand-subtitle">EVIDENCE BEFORE COMMITMENT</div></div></div>'
                f'<div class="mode"><span class="mode-dot" aria-hidden="true"></span>{esc(mode)}</div></div>')
    with appearance:
        st.toggle("Light mode", key="light_mode", on_change=remember_theme)

review_tab, comparison_tab = st.tabs(["Review a request", "Compare architectures"], key="workspace_tabs", on_change="rerun")
with review_tab:
    try:
        requests = load_requests()
        employees = load_employees().set_index("employee_id").to_dict(orient="index")
    except (OSError, ValueError, KeyError) as exc:
        st.error("The request records could not be loaded. Check the supplied data files before starting a review.")
        with st.expander("Technical details"):
            st.text(f"{type(exc).__name__}: {exc}")
    else:
        review.render(requests, employees, provider=provider, model=model, audit_log=ROOT/"logs/human_decisions.jsonl")
with comparison_tab:
    comparison.render(ROOT, provider=provider, model=model)

st.html(f'<div class="footer-note">Policy snapshot {esc(reference_date())} · Synthetic assessment data · Reviews are recorded locally; a human completes the approval process.</div>')
