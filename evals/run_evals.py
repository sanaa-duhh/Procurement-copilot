"""Full evaluation: both architectures, same cases, same checks.

    uv run python evals/run_evals.py                      # single + staged, all 18 cases, 1 repeat
    uv run python evals/run_evals.py --repeats 3          # latency variance
    uv run python evals/run_evals.py --cases public       # the six starter cases only
    uv run python evals/run_evals.py --provider mock      # offline smoke run (written to results/mock/, never reported)

Per case it records: starter minimum checks, next-action correctness, exact
approval set, risk-flag correctness, missing-information handling, evidence
grounding, latency, LLM/tool calls, tokens, and how many guardrail corrections
the model's raw draft needed. The raw draft is scored with the same checks so
the architectures can be compared before and after the deterministic layer.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from run_public_evals import evaluate as public_evaluate  # noqa: E402

from src.contracts import ProcurementDecision  # noqa: E402
from src.data_access import get_request  # noqa: E402
from src.guardrails import canonical_approval, canonical_flag  # noqa: E402
from src.llm import get_llm_client  # noqa: E402
from src.solution import handle_request_payload  # noqa: E402

PUBLIC_CASES = {c["case_id"]: c for c in json.loads((ROOT / "evals" / "public_cases.json").read_text(encoding="utf-8"))}

# USD per million tokens; used only for the indicative cost column.
PRICES = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0), "claude-haiku-4-5": (1.0, 5.0), "claude-fable-5-1": (10.0, 50.0)}


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def score(expectations: dict[str, Any], *, next_action: str | None, approvals: list[str], flags: list[str],
          missing: list[str], human_review: bool) -> dict[str, Any]:
    approvals_c = {canonical_approval(a) for a in approvals} - {None}
    flags_c = {canonical_flag(f) for f in flags} - {None}
    failures: list[str] = []

    expected_actions = expectations.get("next_action_any")
    next_ok = True
    if expected_actions is not None:
        next_ok = next_action in expected_actions
        if not next_ok:
            failures.append(f"next_action '{next_action}' not in {expected_actions}")

    approvals_ok = True
    if "required_approvals_exact" in expectations:
        expected = set(expectations["required_approvals_exact"])
        approvals_ok = approvals_c == expected
        if not approvals_ok:
            failures.append(f"approvals {sorted(approvals_c)} != {sorted(expected)}")
    for name in expectations.get("approvals_must_not_contain", []):
        if name in approvals_c:
            approvals_ok = False
            failures.append(f"unexpected approval {name}")

    flags_ok = True
    for name in expectations.get("risk_flags_must_contain", []):
        if name not in flags_c:
            flags_ok = False
            failures.append(f"missing flag {name}")
    for name in expectations.get("risk_flags_must_not_contain", []):
        if name in flags_c:
            flags_ok = False
            failures.append(f"unexpected flag {name}")

    missing_ok = True
    if "max_missing_information" in expectations and len(missing) > expectations["max_missing_information"]:
        missing_ok = False
        failures.append(f"{len(missing)} missing-information items > {expectations['max_missing_information']}")
    if "min_missing_information" in expectations and len(missing) < expectations["min_missing_information"]:
        missing_ok = False
        failures.append(f"{len(missing)} missing-information items < {expectations['min_missing_information']}")

    human_ok = human_review == expectations.get("human_review_required", True)
    if not human_ok:
        failures.append("human_review_required wrong")

    return {
        "next_action_correct": next_ok,
        "approvals_correct": approvals_ok,
        "flags_correct": flags_ok,
        "missing_info_correct": missing_ok,
        "human_review_correct": human_ok,
        "policy_followed": approvals_ok and flags_ok and missing_ok,
        "all_correct": next_ok and approvals_ok and flags_ok and missing_ok and human_ok,
        "failures": failures,
    }


def grounding(evidence: list[dict[str, Any]], tools_ran: set[str]) -> float | None:
    if not evidence:
        return None
    ok = sum(1 for e in evidence if str(e.get("source", "")) in tools_ran)
    return round(ok / len(evidence), 3)


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------

def load_cases(which: str) -> list[dict[str, Any]]:
    cases = json.loads((ROOT / "evals" / "cases.json").read_text(encoding="utf-8"))
    if which == "public":
        cases = [c for c in cases if c["case_id"].startswith("PUB")]
    return cases


def run_case(case: dict[str, Any], architecture: str, llm: Any, repeat: int) -> dict[str, Any]:
    request = case["request"] if "request" in case else get_request(case["request_id"])
    saved = os.environ.get("VENDOR_RISK_BASE_URL")
    if case.get("simulate_vendor_outage"):
        os.environ["VENDOR_RISK_BASE_URL"] = "http://127.0.0.1:9"   # discard port: connection refused
    started = time.perf_counter()
    error = None
    try:
        decision = handle_request_payload(request, architecture=architecture, llm=llm)
    except Exception as exc:  # the harness must keep going and record the failure
        decision = None
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if case.get("simulate_vendor_outage"):
            if saved is None:
                os.environ.pop("VENDOR_RISK_BASE_URL", None)
            else:
                os.environ["VENDOR_RISK_BASE_URL"] = saved
    latency_ms = round((time.perf_counter() - started) * 1000, 1)

    row: dict[str, Any] = {
        "case_id": case["case_id"], "request_id": request["request_id"], "title": case["title"],
        "architecture": architecture, "repeat": repeat, "latency_ms": latency_ms,
    }
    if decision is None:
        row.update({"error": error, "all_correct": False, "schema_valid": False})
        return row

    ProcurementDecision.model_validate(decision.model_dump())
    tel = decision.telemetry
    trace = decision.trace
    draft = trace.get("draft") or {}
    findings = trace.get("findings") or {}
    tools_ran = {e["tool"] for e in trace.get("tool_log", [])} | {"policy_checks", "run_policy_checks"}
    agent_tools = set(trace.get("agent_tools_called") or [])
    llm_errors = [e for e in trace.get("errors", [])]

    final = score(case["expectations"], next_action=decision.next_action, approvals=decision.required_approvals,
                  flags=decision.risk_flags, missing=decision.missing_information, human_review=decision.human_review_required)
    raw = score(case["expectations"], next_action=draft.get("next_action"), approvals=draft.get("required_approvals") or [],
                flags=draft.get("risk_flags") or [], missing=draft.get("missing_information") or [],
                human_review=True) if draft else {k: False for k in final} | {"failures": ["no draft"]}
    public_failures = public_evaluate(decision, PUBLIC_CASES[case["case_id"]]["expectations"]) if case["case_id"] in PUBLIC_CASES else None

    in_tok, out_tok = tel.input_tokens, tel.output_tokens
    price = PRICES.get(tel.model or "", (0.0, 0.0))
    row.update({
        "schema_valid": True,
        "public_min_checks_passed": (not public_failures) if public_failures is not None else "",
        "public_failures": " | ".join(public_failures or []),
        **{k: v for k, v in final.items() if k != "failures"},
        "failures": " | ".join(final["failures"]),
        "raw_next_action_correct": raw["next_action_correct"],
        "raw_approvals_correct": raw["approvals_correct"],
        "raw_flags_correct": raw["flags_correct"],
        "raw_policy_followed": raw["policy_followed"],
        "raw_all_correct": raw["all_correct"],
        "raw_failures": " | ".join(raw["failures"]),
        "guardrail_corrections": len(tel.guardrail_corrections),
        "guardrail_correction_detail": " | ".join(tel.guardrail_corrections),
        "evidence_items": len(decision.evidence),
        "final_grounding_rate": grounding([e.model_dump() for e in decision.evidence], tools_ran),
        "draft_evidence_items": len(draft.get("evidence") or []),
        "draft_grounding_rate": grounding(draft.get("evidence") or [], tools_ran),
        "agent_tool_coverage": round(len(agent_tools & set(findings and {"get_requester_profile", "check_budget", "search_software_catalog", "get_vendor_registry_record", "get_vendor_risk_assessment", "get_purchase_history", "run_policy_checks"})) / 7, 3),
        "llm_calls": tel.llm_calls, "tool_calls": tel.tool_calls, "input_tokens": in_tok, "output_tokens": out_tok,
        "est_cost_usd": round(in_tok / 1e6 * price[0] + out_tok / 1e6 * price[1], 4),
        "stage_latency_ms": json.dumps(tel.stage_latency_ms),
        "llm_errors": " | ".join(llm_errors),
        "next_action": decision.next_action, "required_approvals": ", ".join(decision.required_approvals),
        "risk_flags": ", ".join(decision.risk_flags), "model": tel.model,
        "_decision": decision.model_dump(), "_draft": draft, "_trace_errors": llm_errors,
    })
    return row


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def _rate(rows: list[dict[str, Any]], key: str) -> float:
    vals = [r.get(key) for r in rows if isinstance(r.get(key), bool)]
    return round(100 * sum(vals) / len(vals), 1) if vals else float("nan")


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    vals = [r[key] for r in rows if isinstance(r.get(key), (int, float)) and r.get(key) is not None]
    return round(statistics.fmean(vals), 2) if vals else float("nan")


def _p95(rows: list[dict[str, Any]], key: str) -> float:
    vals = sorted(r[key] for r in rows if isinstance(r.get(key), (int, float)))
    if not vals:
        return float("nan")
    return round(vals[min(len(vals) - 1, int(round(0.95 * (len(vals) - 1))))], 1)


def summarise(rows: list[dict[str, Any]], architectures: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for arch in architectures:
        sub = [r for r in rows if r["architecture"] == arch]
        out[arch] = {
            "runs": len(sub),
            "errors": sum(1 for r in sub if r.get("error")),
            "all_correct_pct": _rate(sub, "all_correct"),
            "next_action_correct_pct": _rate(sub, "next_action_correct"),
            "policy_followed_pct": _rate(sub, "policy_followed"),
            "human_review_correct_pct": _rate(sub, "human_review_correct"),
            "public_min_checks_pct": _rate(sub, "public_min_checks_passed"),
            "raw_all_correct_pct": _rate(sub, "raw_all_correct"),
            "raw_next_action_correct_pct": _rate(sub, "raw_next_action_correct"),
            "raw_policy_followed_pct": _rate(sub, "raw_policy_followed"),
            "draft_grounding_rate": _mean(sub, "draft_grounding_rate"),
            "final_grounding_rate": _mean(sub, "final_grounding_rate"),
            "agent_tool_coverage": _mean(sub, "agent_tool_coverage"),
            "guardrail_corrections_per_case": _mean(sub, "guardrail_corrections"),
            "avg_latency_ms": _mean(sub, "latency_ms"),
            "p95_latency_ms": _p95(sub, "latency_ms"),
            "avg_llm_calls": _mean(sub, "llm_calls"),
            "avg_tool_calls": _mean(sub, "tool_calls"),
            "avg_input_tokens": _mean(sub, "input_tokens"),
            "avg_output_tokens": _mean(sub, "output_tokens"),
            "avg_est_cost_usd": _mean(sub, "est_cost_usd"),
        }
    return out


def write_markdown(summary: dict[str, Any], rows: list[dict[str, Any]], architectures: list[str], meta: dict[str, Any], path: Path) -> None:
    metrics = [
        ("Cases fully correct (action + approvals + flags + missing info + human review)", "all_correct_pct", "%"),
        ("Correct next action", "next_action_correct_pct", "%"),
        ("Policy + deterministic rules followed", "policy_followed_pct", "%"),
        ("Human review flagged correctly", "human_review_correct_pct", "%"),
        ("Starter public minimum checks (6 cases)", "public_min_checks_pct", "%"),
        ("Model draft fully correct *before* guardrail", "raw_all_correct_pct", "%"),
        ("Model draft next action correct *before* guardrail", "raw_next_action_correct_pct", "%"),
        ("Model draft policy-complete *before* guardrail", "raw_policy_followed_pct", "%"),
        ("Draft evidence grounded in a tool that ran", "draft_grounding_rate", "ratio"),
        ("Agent tool coverage (of 7 tools)", "agent_tool_coverage", "ratio"),
        ("Guardrail corrections per case", "guardrail_corrections_per_case", ""),
        ("Avg latency", "avg_latency_ms", "ms"),
        ("p95 latency", "p95_latency_ms", "ms"),
        ("Avg LLM calls", "avg_llm_calls", ""),
        ("Avg tool calls", "avg_tool_calls", ""),
        ("Avg input tokens", "avg_input_tokens", ""),
        ("Avg output tokens", "avg_output_tokens", ""),
        ("Avg indicative cost per case", "avg_est_cost_usd", "USD"),
    ]
    lines = [
        "# Evaluation results",
        "",
        f"Generated {meta['generated_at']} · provider `{meta['provider']}` · model `{meta['model']}` · effort `{meta['effort']}` · "
        f"{meta['case_count']} cases × {meta['repeats']} repeat(s) per architecture · reference date {meta['reference_date']}",
        "",
        "## Architecture comparison",
        "",
        "| Metric | " + " | ".join(architectures) + " |",
        "|---|" + "---:|" * len(architectures),
    ]
    for label, key, unit in metrics:
        cells = []
        for arch in architectures:
            v = summary[arch][key]
            cells.append("n/a" if v != v else (f"{v}{unit}" if unit == "%" else (f"{v:.3f}" if unit == "ratio" else (f"${v:.4f}" if unit == "USD" else f"{v:g}{(' ' + unit) if unit else ''}"))))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", "## Per-case outcomes", ""]
    header = "| Case | Title | " + " | ".join(f"{a}: final" for a in architectures) + " | " + " | ".join(f"{a}: draft" for a in architectures) + " | " + " | ".join(f"{a}: ms" for a in architectures) + " |"
    lines.append(header)
    lines.append("|---|---|" + "---|" * (3 * len(architectures)))
    by_case: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    titles: dict[str, str] = {}
    for r in rows:
        by_case[r["case_id"]][r["architecture"]].append(r)
        titles[r["case_id"]] = r["title"]
    def mark(sub: list[dict[str, Any]], key: str) -> str:
        if not sub:
            return "–"
        ok = sum(1 for r in sub if r.get(key) is True)
        return "pass" if ok == len(sub) else ("fail" if ok == 0 else f"{ok}/{len(sub)}")
    for case_id in sorted(by_case):
        cells = [mark(by_case[case_id][a], "all_correct") for a in architectures]
        cells += [mark(by_case[case_id][a], "raw_all_correct") for a in architectures]
        cells += [f"{_mean(by_case[case_id][a], 'latency_ms'):.0f}" if by_case[case_id][a] else "–" for a in architectures]
        lines.append(f"| {case_id} | {titles[case_id]} | " + " | ".join(cells) + " |")
    failures = [r for r in rows if r.get("failures") or r.get("error")]
    lines += ["", "## Final-decision failures", ""]
    if not failures:
        lines.append("None.")
    for r in failures:
        lines.append(f"- **{r['case_id']}** ({r['architecture']}, repeat {r['repeat']}): {r.get('error') or r['failures']}")
    draft_failures = [r for r in rows if r.get("raw_failures") and not r.get("error")]
    lines += ["", "## Model-draft failures corrected by the guardrail", ""]
    if not draft_failures:
        lines.append("None.")
    for r in draft_failures:
        lines.append(f"- **{r['case_id']}** ({r['architecture']}, repeat {r['repeat']}): {r['raw_failures']}")
    corrections = [r for r in rows if r.get("guardrail_correction_detail")]
    lines += ["", "## Guardrail corrections (detail)", ""]
    if not corrections:
        lines.append("None.")
    for r in corrections:
        lines.append(f"- **{r['case_id']}** ({r['architecture']}, repeat {r['repeat']}): {r['guardrail_correction_detail']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--architectures", nargs="+", choices=["single", "staged"], default=["single", "staged"])
    parser.add_argument("--cases", choices=["public", "all"], default="all")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--provider", choices=["anthropic", "mock"], default=None, help="overrides LLM_PROVIDER")
    parser.add_argument("--out", default=None, help="output directory (default evals/results, or evals/results/mock)")
    parser.add_argument("--allow-degraded", action="store_true", help="keep going and report even if the model failed on some runs")
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    provider = os.getenv("LLM_PROVIDER", "anthropic")
    out_dir = Path(args.out) if args.out else (ROOT / "evals" / "results" / ("mock" if provider == "mock" else ""))
    out_dir.mkdir(parents=True, exist_ok=True)

    llm = get_llm_client()
    cases = load_cases(args.cases)
    rows: list[dict[str, Any]] = []
    print(f"\nEvaluation · provider={provider} model={llm.model} · {len(cases)} cases · repeats={args.repeats} · architectures={args.architectures}\n")
    for architecture in args.architectures:
        for repeat in range(1, args.repeats + 1):
            for case in cases:
                row = run_case(case, architecture, llm, repeat)
                rows.append(row)
                status = "ERROR" if row.get("error") else ("PASS" if row["all_correct"] else "FAIL")
                draft = "" if row.get("error") else f" draft={'ok' if row['raw_all_correct'] else 'fix'} corr={row['guardrail_corrections']}"
                print(f"{status}  {architecture:6s} r{repeat} {row['case_id']}  {row['title'][:48]:48s} {row['latency_ms']:7.0f} ms{draft}")
                if row.get("error"):
                    print(f"       {row['error']}")
                elif row.get("failures"):
                    print(f"       {row['failures']}")
                if row.get("_trace_errors"):
                    print(f"       model errors: {row['_trace_errors']}")

    degraded = [r for r in rows if r.get("error") or r.get("_trace_errors")]
    if degraded and not args.allow_degraded and provider != "mock":
        print(f"\n{len(degraded)} run(s) hit a model error; results not written. Fix credentials/network or pass --allow-degraded.")
        raise SystemExit(2)

    # Per-run CSV, decisions JSONL, summary JSON + Markdown
    fieldnames = [k for k in rows[0].keys() if not k.startswith("_")]
    for r in rows:
        for k in fieldnames:
            r.setdefault(k, "")
    with (out_dir / "runs.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with (out_dir / "decisions.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"case_id": r["case_id"], "architecture": r["architecture"], "repeat": r["repeat"],
                                "decision": r.get("_decision"), "draft": r.get("_draft")}, default=str) + "\n")
    from src.rules import reference_date
    meta = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "provider": provider, "model": llm.model, "effort": os.getenv("LLM_EFFORT", "medium") if provider != "mock" else "n/a",
        "case_count": len(cases), "repeats": args.repeats, "reference_date": str(reference_date()),
    }
    summary = summarise(rows, args.architectures)
    (out_dir / "summary.json").write_text(json.dumps({"meta": meta, "summary": summary}, indent=2), encoding="utf-8")
    write_markdown(summary, rows, args.architectures, meta, out_dir / "summary.md")
    print()
    for arch in args.architectures:
        s = summary[arch]
        print(f"{arch:6s}  fully correct {s['all_correct_pct']}%  next-action {s['next_action_correct_pct']}%  policy {s['policy_followed_pct']}%  "
              f"draft-correct {s['raw_all_correct_pct']}%  corrections/case {s['guardrail_corrections_per_case']}  "
              f"latency {s['avg_latency_ms']} ms  llm {s['avg_llm_calls']}  tools {s['avg_tool_calls']}")
    print(f"\nWritten to {out_dir.relative_to(ROOT)}/ (runs.csv, decisions.jsonl, summary.json, summary.md)")


if __name__ == "__main__":
    main()
