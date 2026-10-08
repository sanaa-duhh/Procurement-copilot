"""Browse the saved experiment without executing an agent or making model calls."""
import csv
import json
from pathlib import Path

import streamlit as st

from ui.components import ACTION_LABELS, ARCHITECTURES, chips, table, text

EXPERIMENT = "openai-comparison-20261008"


def load_benchmark(root: Path) -> tuple[dict, list[dict], dict]:
    directory = root / "evals" / "results" / EXPERIMENT
    report = json.loads((directory / "summary.json").read_text())
    with (directory / "runs.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    records = [json.loads(line) for line in (directory / "decisions.jsonl").read_text().splitlines() if line.strip()]
    meta = report["meta"]
    if not meta["complete"] or meta["result_kind"] != "model_experiment" or meta["repeats"] != 1:
        raise ValueError("The selected report is not a complete single-repeat model comparison")
    keys = {(r["case_id"], r["architecture"]) for r in rows}
    if len(rows) != meta["case_count"] * 2 or len(keys) != len(rows) or keys != {(r["case_id"], r["architecture"]) for r in records}:
        raise ValueError("Comparison records are incomplete or duplicated")
    return report, rows, {(r["case_id"], r["architecture"]): r for r in records}


def render(root: Path) -> None:
    st.title("Compare the architectures")
    text("The same requests, tools and policy controls. Inspect what the extra reviewer changes.", "intro")
    try:
        report, rows, records = load_benchmark(root)
    except (OSError, ValueError, KeyError) as exc:
        st.warning("The saved architecture comparison could not be loaded. No benchmark values are being substituted.")
        with st.expander("Report details"):
            text(str(exc))
        return
    meta, summary = report["meta"], report["summary"]
    st.caption(f"Saved OpenAI evaluation · {meta['case_count']} cases per architecture · {meta['model']} · {meta['effort']} reasoning · {meta['generated_at']} · browsing makes no API calls")
    a, b = st.columns(2, gap="medium")
    with a:
        st.html('<article class="architecture-card recommended"><div class="eyebrow">Recommended for supervised use</div><h3>Single agent</h3><div class="body-text">One agent gathers evidence and recommends an action. Code enforces policy before a human reviews it.</div><div class="flow">Request → Agent + tools → Policy checks → Human</div></article>')
    with b:
        st.html('<article class="architecture-card"><div class="eyebrow">Alternative tested</div><h3>Analyst + reviewer</h3><div class="body-text">An analyst gathers evidence. A second role reviews the evidence package and recommends an action.</div><div class="flow">Request → Analyst + tools → Reviewer → Policy checks → Human</div></article>')
    def count(arch, metric):
        sub = [r for r in rows if r["architecture"] == arch]
        return f"{sum(r[metric] == 'True' for r in sub)}/{len(sub)}"
    metrics = [
        ["Final decision passes", count("single", "end_to_end_success"), count("staged", "end_to_end_success")],
        ["Raw draft passes, before corrections", count("single", "raw_all_correct"), count("staged", "raw_all_correct")],
        ["Average analysis time", *[f"{summary[a]['avg_latency_ms']/1000:.1f} s" for a in ("single", "staged")]],
        ["Average model calls", *[f"{summary[a]['avg_llm_calls']:.2f}" for a in ("single", "staged")]],
        ["Average executed tool calls", *[f"{summary[a]['avg_tool_calls']:.2f}" for a in ("single", "staged")]],
        ["Average estimated token cost", *[f"${summary[a]['avg_est_cost_usd']:.3f}" for a in ("single", "staged")]],
        ["Field corrections across all requests", *[sum(int(r["guardrail_corrections"]) for r in rows if r["architecture"] == a) for a in ("single", "staged")]],
    ]
    table(["Measured result", "Single agent", "Analyst + reviewer"], metrics)
    reduction = 100*(1-summary["single"]["avg_latency_ms"]/summary["staged"]["avg_latency_ms"])
    text(f"The single agent used {reduction:.0f}% less time in this run. The second role added useful observations, but the results did not establish enough quality improvement to justify its extra calls.")
    st.caption("One trial per architecture on a small, mostly policy-driven test set. This supports a supervised pilot; it does not establish production reliability. Costs are estimates before cache discounts.")
    st.subheader("Inspect a case")
    st.caption("Start with the disagreement: both designs preserve Security and Privacy reviews, but choose a different first step.")
    case_ids = sorted({r["case_id"] for r in rows})
    titles = {r["case_id"]: r["title"] for r in rows}
    case_id = st.selectbox("Evaluation case", case_ids, index=case_ids.index("SYN-17") if "SYN-17" in case_ids else 0,
                           format_func=lambda c: f"{c} · {titles[c]}", key="comparison_case")
    for arch, col in zip(("single", "staged"), st.columns(2, gap="large")):
        with col:
            row = next(r for r in rows if r["case_id"] == case_id and r["architecture"] == arch)
            record = records[(case_id, arch)]
            decision = record["decision"] or {}
            st.markdown(f"**{ARCHITECTURES[arch]}**")
            passing = row["end_to_end_success"] == "True"
            st.html(f'<div class="outcome{"" if passing else " miss"}">{"Final checks passed" if passing else "Final check did not match the label"} · Raw draft {"passed" if row["raw_all_correct"] == "True" else "needed review"}</div>')
            text(ACTION_LABELS.get(decision.get("next_action"), decision.get("next_action", "No decision")), "request-heading")
            if decision.get("required_approvals"):
                chips(decision["required_approvals"])
            text(decision.get("rationale") or "No model rationale is available for this result.")
            if row.get("failures"):
                st.caption("Scoring detail: " + row["failures"])
            with st.expander("Draft and policy corrections"):
                text(row.get("guardrail_correction_detail") or "No field corrections.")
                if row.get("raw_failures"):
                    text("Raw-draft scoring: " + row["raw_failures"])
                st.json(record.get("draft"), expanded=False)
    if case_id == "SYN-17":
        st.info("The staged result is a sequencing disagreement, not an omitted privacy control. The label requires specialist reviews first; the staged agent checks the existing licence first. The original score is retained.")
    with st.expander("How the experiment was run"):
        st.write("Six public cases, four other starter requests and eight additional edge cases. Both architectures use the same OpenAI model, reasoning setting, tools and final policy checks. Case order and architecture order were shuffled with seed 42.")
        st.write("The raw draft is scored before code corrections, and the final decision is scored afterwards. Provider errors remain failures even if the policy fallback returns a safe recommendation. Selected evidence achieved exact support in both designs; this does not independently validate free-form rationale.")
        st.write("Vendor calls exercise the supplied API handlers in-process in this experiment. The application uses HTTP. The model calls in the experiment are real.")
        st.caption("Measured source: 0de3dc7. A later money-formatting fix was verified separately in four threshold trials; those trials are not pooled into these results. Failed integration attempts are retained in the repository.")
        prices = meta.get("prices_usd_per_million")
        if prices:
            st.caption(f"Cost inputs: USD {prices[0]:g} per million input tokens and USD {prices[1]:g} per million output tokens. These are recorded experiment assumptions, not a current billing quote.")
    a, b = st.columns(2)
    directory = root / "evals" / "results" / EXPERIMENT
    a.download_button("Download comparison CSV", (directory/"runs.csv").read_bytes(), "architecture_comparison.csv", "text/csv", key="download_comparison", on_click="ignore", width="stretch")
    b.download_button("Download decision memo", (root/"docs/architecture_decision.md").read_text(), "architecture_decision.md", "text/markdown", key="download_memo", on_click="ignore", width="stretch")
