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
st.html(f"<style>{(ROOT/'ui/styles.css').read_text()}</style>")

provider = os.getenv("LLM_PROVIDER", "openai")
model = configured_model(provider)
mode = "Scripted demo" if provider == "mock" else "Live OpenAI"
st.html('<div class="brandbar"><div class="brand"><span class="brand-mark" aria-hidden="true">P</span>Procurement Copilot</div>'
        f'<div class="mode"><span class="mode-dot" aria-hidden="true"></span>{esc(mode)} · Human approval required</div></div>')

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
    comparison.render(ROOT)

st.html(f'<div class="footer-note">Policy snapshot {esc(reference_date())} · Synthetic assessment data · Reviews are recorded locally; a human completes the approval process.</div>')
