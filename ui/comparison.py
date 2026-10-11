"""Browse the saved experiment without executing an agent or making model calls."""
import csv
import json
import os
from pathlib import Path

import streamlit as st

from ui.components import ACTION_LABELS, ARCHITECTURES, chips, display_latency, display_time, hero, table, text
from ui import runs
from ui.history import configuration

EXPERIMENT = "openai-comparison-20261008"
REPLICATION = "openai-repeats-20261011"


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


def load_replication(root: Path) -> list[list[str]] | None:
    """Headline rows from the three-repeat replication, or None if it is absent or incomplete."""
    directory = root / "evals" / "results" / REPLICATION
    try:
        report = json.loads((directory / "summary.json").read_text())
        with (directory / "runs.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, ValueError):
        return None
    meta, summary = report.get("meta", {}), report.get("summary", {})
    if not meta.get("complete") or meta.get("result_kind") != "model_experiment" or set(summary) != {"single", "staged"}:
        return None

    def count(arch: str, metric: str) -> str:
        sub = [r for r in rows if r["architecture"] == arch]
        return f"{sum(r[metric] == 'True' for r in sub)}/{len(sub)}"

    return [
        ["Final decision passes", count("single", "end_to_end_success"), count("staged", "end_to_end_success")],
        ["Raw draft passes, before corrections", count("single", "raw_all_correct"), count("staged", "raw_all_correct")],
        ["Average analysis time", *[f"{summary[a]['avg_latency_ms']/1000:.1f} s" for a in ("single", "staged")]],
        ["Average estimated token cost", *[f"${summary[a]['avg_est_cost_usd']:.3f}" for a in ("single", "staged")]],
    ]


def render(root: Path, *, provider: str, model: str) -> None:
    hero("Compare the architectures", "let the evidence decide.",
         "The same requests, tools and policy controls. Explore what a second reviewer changes, and what it costs.",
         key="comparison_hero", eyebrow="02 / THE ARCHITECTURE LAB")
    current, benchmark = st.tabs(["This request", "18-case benchmark"], key="comparison_views", on_change="rerun")
    with current:
        render_current(root, provider=provider, model=model)
    with benchmark:
        render_benchmark(root)


def render_current(root: Path, *, provider: str, model: str) -> None:
    request = st.session_state.get("current_request")
    if not request:
        st.info("Select or enter a request in Review a request. Its two architecture results will appear here.")
        return
    config = configuration(root, provider, model)
    pair_key = runs.context(request, config, "both")
    previous = st.session_state.get("comparison_pair", {})
    pair = previous["runs"] if previous.get("key") == pair_key else {
        arch: runs.latest(root, request, config, arch) for arch in ("single", "staged")}
    text(f"{request.get('product_name') or 'Untitled request'} · {request['request_id']}", "request-heading")
    st.caption("Uses the exact request selected in the review workspace. Existing runs with matching inputs and settings are reused; nothing runs just by opening this page.")
    missing = [a for a in ("single", "staged") if pair[a] is None]
    credentials = provider == "mock" or bool(os.getenv("OPENAI_API_KEY"))
    if provider == "mock":
        st.caption("Scripted demo: this comparison checks the workflow and does not measure model intelligence.")
    else:
        st.caption(f"OpenAI · {model} · {config['effort']} reasoning. Running the missing design uses API credits; running both again pays for two fresh analyses.")
    label = "Compare this request" if len(missing) == 2 else f"Run {ARCHITECTURES[missing[0]].lower()} for comparison" if missing else "Run both again"
    if st.button(label, key="compare_request", type="primary", disabled=not credentials):
        targets = missing or ["single", "staged"]
        if not missing:
            pair = {"single": None, "staged": None}
        if st.session_state.get("architecture") in targets:
            for key in ("decision", "decision_record", "saved_review"):
                st.session_state.pop(key, None)
        failures = []
        for architecture in targets:
            with st.status(f"Running {ARCHITECTURES[architecture].lower()}…", expanded=True) as progress:
                try:
                    record = runs.execute(root, request, config, architecture)
                except Exception as exc:
                    failures.append(f"{ARCHITECTURES[architecture]}: {type(exc).__name__}: {exc}")
                    progress.update(label="Analysis could not finish", state="error")
                else:
                    pair[architecture] = record
                    if st.session_state.get("architecture") == architecture:
                        runs.activate(record, runs.context(request, config, architecture))
                    progress.update(label="Analysis complete" if not record.decision.trace.get("errors") else "Policy fallback; model stage failed",
                                    state="complete" if not record.decision.trace.get("errors") else "error")
        st.session_state["comparison_pair"] = {"key": pair_key, "runs": pair, "failures": failures}
        st.rerun()
    if previous.get("key") == pair_key and previous.get("failures"):
        st.error("The comparison is incomplete. Completed runs were saved; retry only the missing design using the button above.")
        with st.expander("Comparison error details"):
            for failure in previous["failures"]:
                text(failure)
    if st.session_state.get("history_error"):
        st.warning(st.session_state["history_error"])
    if not any(pair.values()):
        st.info("No matching analyses yet. Compare both here, or analyse one in the review workspace and return to run only the other.")
        return
    for arch, column in zip(("single", "staged"), st.columns(2, gap="large")):
        with column:
            st.subheader(ARCHITECTURES[arch])
            record = pair[arch]
            if record is None:
                st.caption("Not run with this request and configuration yet.")
                continue
            decision = record.decision
            st.caption(f"{display_time(record.created_at)} · run {record.run_id[:8]} · {record.config['model']}")
            text(ACTION_LABELS.get(decision.next_action, "No action"), "request-heading")
            if decision.trace.get("errors"):
                st.warning("Model stage failed; this is a deterministic fallback, not a successful model recommendation.")
            text(decision.next_step)
            chips(decision.required_approvals)
            with st.expander("Evidence and required information"):
                for evidence in decision.evidence:
                    text(evidence.finding)
                    text(f"{evidence.source} · {evidence.reference}", "evidence-source")
                st.write("Required information:")
                for item in decision.missing_information or ["No mandatory intake fields are missing."]:
                    text(item)
                if decision.risk_flags:
                    chips(decision.risk_flags, risk=True)
            with st.expander("Raw draft and policy corrections"):
                for correction in decision.telemetry.guardrail_corrections or ["No field corrections."]:
                    text(correction)
                st.json(decision.trace.get("draft", {}), expanded=False)
    if all(pair.values()):
        first, second = pair["single"].decision, pair["staged"].decision
        different = []
        for field, label in [("next_action", "next action"), ("required_approvals", "approvals"),
                             ("missing_information", "required information"), ("risk_flags", "risk flags")]:
            a, b = getattr(first, field), getattr(second, field)
            differs = set(a) != set(b) if isinstance(a, list) else a != b
            if differs:
                different.append(label)
        if different:
            st.warning("The designs differ on: " + ", ".join(different) + ". Inspect the evidence and policy corrections before choosing a next step.")
        else:
            st.success("Both designs agree on the next action, approvals, required information and risk flags.")
        table(["This request", "Single agent", "Analyst + reviewer"], [
            ["Analysis time", *[display_latency(r.decision.telemetry.latency_ms) for r in pair.values()]],
            ["Model calls", *[r.decision.telemetry.llm_calls for r in pair.values()]],
            ["Executed tool calls", *[r.decision.telemetry.tool_calls for r in pair.values()]],
            ["Input / output tokens", *[f"{r.decision.telemetry.input_tokens:,} / {r.decision.telemetry.output_tokens:,}" for r in pair.values()]],
            ["Policy field corrections", *[len(r.decision.telemetry.guardrail_corrections) for r in pair.values()]],
        ])
        st.caption("These are independent runs on the same request and configuration; vendor evidence may change between runs. This request has no labelled answer, so agreement is not an accuracy score. Use the fixed 18-case benchmark to assess the overall architecture choice.")
    st.caption("Saved results can also be opened from the review workspace under the matching analysis approach.")
    st.download_button("Download this comparison", json.dumps({"kind": "unlabelled_request_comparison", "request": request,
                       "config": config, "runs": {a: r.payload() if r else None for a, r in pair.items()}}, indent=2, default=str),
                       "request_comparison.json", "application/json", on_click="ignore", key="download_request_comparison")


def render_benchmark(root: Path) -> None:
    st.subheader("The saved architecture experiment")
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
    st.caption("One trial per architecture on a small, mostly policy-driven test set. Costs are estimates before cache discounts.")
    replication = load_replication(root)
    if replication:
        st.subheader("Replication: three repeats")
        st.caption("The same 18 cases rerun three times per architecture on source commit 334034e, 11 October 2026. 54 trials per architecture.")
        table(["Measured result", "Single agent", "Analyst + reviewer"], replication)
        text("The single agent passed every trial. The staged reviewer failed SYN-17 in all three repeats and PUB-02 and PUB-03 in some, preferring to check the existing tool before required reviews or adding an unneeded Privacy review. Review order is now a policy rule; replaying the saved drafts under it lifts staged to 52/54 final, while its raw drafts stay at 42/54.")
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
        st.caption("Measured source: fd4f419. A later money-formatting fix was verified separately in four threshold trials; those trials are not pooled into these results. A three-repeat replication on source commit `334034e` is shown above.")
        prices = meta.get("prices_usd_per_million")
        if prices:
            st.caption(f"Cost inputs: USD {prices[0]:g} per million input tokens and USD {prices[1]:g} per million output tokens. These are recorded experiment assumptions, not a current billing quote.")
    a, b = st.columns(2)
    directory = root / "evals" / "results" / EXPERIMENT
    a.download_button("Download comparison CSV", (directory/"runs.csv").read_bytes(), "architecture_comparison.csv", "text/csv", key="download_comparison", on_click="ignore", width="stretch")
    b.download_button("Download decision memo", (root/"docs/architecture_decision.md").read_text(), "architecture_decision.md", "text/markdown", key="download_memo", on_click="ignore", width="stretch")
