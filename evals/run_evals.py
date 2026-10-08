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
import hashlib
import math
import platform
import random
import subprocess
from contextlib import nullcontext
from unittest.mock import patch
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
from src.evidence import draft_support
from src.vendor_client import VendorRiskUnavailable
from transport import vendor_transport
from src.llm import get_llm_client  # noqa: E402
from src.solution import handle_request_payload  # noqa: E402

PUBLIC_CASES = {c["case_id"]: c for c in json.loads((ROOT / "evals" / "public_cases.json").read_text(encoding="utf-8"))}
ALL_TOOLS = {"get_requester_profile", "check_budget", "search_software_catalog", "get_vendor_registry_record",
             "get_vendor_risk_assessment", "get_purchase_history", "run_policy_checks"}

# Cost is only estimated when the operator supplies both dated price inputs.
# Unknown model pricing must remain unknown, never silently become $0.
PRICES: dict[str, tuple[float, float]] = {}


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
    outage = patch("src.tools.vendor.get_vendor_risk", side_effect=VendorRiskUnavailable("simulated outage")) if case.get("simulate_vendor_outage") else nullcontext()
    started = time.perf_counter()
    error = None
    try:
        with outage:
            decision = handle_request_payload(request, architecture=architecture, llm=llm)
    except Exception as exc:  # the harness must keep going and record the failure
        decision = None
        error = f"{type(exc).__name__}: {exc}"
    latency_ms = round((time.perf_counter() - started) * 1000, 1)

    row: dict[str, Any] = {
        "case_id": case["case_id"], "request_id": request["request_id"], "title": case["title"],
        "architecture": architecture, "repeat": repeat, "latency_ms": latency_ms,
    }
    if decision is None:
        row.update({"error": error, "schema_valid": False, "model_success": False, "end_to_end_success": False,
                    "all_correct": False, "next_action_correct": False, "policy_followed": False,
                    "human_review_correct": False, "raw_all_correct": False, "raw_next_action_correct": False,
                    "raw_policy_followed": False, "draft_grounding_rate": 0.0, "final_grounding_rate": 0.0})
        if case["case_id"] in PUBLIC_CASES:
            row["public_min_checks_passed"] = False
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
    price = PRICES.get(tel.model or "")
    row.update({
        "schema_valid": True,
        "model_success": bool(draft) and not llm_errors,
        "end_to_end_success": bool(draft) and not llm_errors and final["all_correct"],
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
        "final_grounding_rate": draft_support([e.model_dump() for e in decision.evidence], [{"actor": "code", "tool": "run_policy_checks", "result": findings}]),
        "draft_evidence_items": len(draft.get("evidence") or []),
        "draft_grounding_rate": draft_support(draft.get("evidence") or [], trace.get("tool_log", [])),
        "agent_tool_coverage": round(len(agent_tools & ALL_TOOLS) / len(ALL_TOOLS), 3),
        "llm_calls": tel.llm_calls, "tool_calls": tel.tool_calls, "input_tokens": in_tok, "output_tokens": out_tok,
        "est_cost_usd": round(in_tok / 1e6 * price[0] + out_tok / 1e6 * price[1], 6) if price else None,
        "stage_latency_ms": json.dumps(tel.stage_latency_ms),
        "rate_limit_retries": tel.rate_limit_retries, "rate_limit_wait_ms": tel.rate_limit_wait_ms,
        "llm_errors": " | ".join(llm_errors),
        "next_action": decision.next_action, "required_approvals": ", ".join(decision.required_approvals),
        "risk_flags": ", ".join(decision.risk_flags), "model": tel.model,
        "_decision": decision.model_dump(), "_draft": draft, "_trace_errors": llm_errors, "_trace": trace,
    })
    return row


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def _rate(rows: list[dict[str, Any]], key: str) -> float:
    vals = [r.get(key) for r in rows if isinstance(r.get(key), bool)]
    return round(100 * sum(vals) / len(vals), 1) if vals else None


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    vals = [r[key] for r in rows if isinstance(r.get(key), (int, float)) and r.get(key) is not None]
    return round(statistics.fmean(vals), 6) if vals else None


def _p95(rows: list[dict[str, Any]], key: str) -> float:
    vals = sorted(r[key] for r in rows if isinstance(r.get(key), (int, float)))
    if not vals:
        return None
    return round(vals[min(len(vals) - 1, math.ceil(0.95 * len(vals)) - 1)], 1)


def summarise(rows: list[dict[str, Any]], architectures: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for arch in architectures:
        sub = [r for r in rows if r["architecture"] == arch]
        out[arch] = {
            "runs": len(sub),
            "errors": sum(1 for r in sub if r.get("error")),
            "model_success_pct": _rate(sub, "model_success"),
            "end_to_end_success_pct": _rate(sub, "end_to_end_success"),
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
            "avg_rate_limit_wait_ms": _mean(sub, "rate_limit_wait_ms"),
            "rate_limit_retries": sum(r.get("rate_limit_retries") or 0 for r in sub),
            "avg_tool_calls": _mean(sub, "tool_calls"),
            "avg_input_tokens": _mean(sub, "input_tokens"),
            "avg_output_tokens": _mean(sub, "output_tokens"),
            "avg_est_cost_usd": _mean(sub, "est_cost_usd"),
        }
    return out


def write_markdown(summary: dict[str, Any], rows: list[dict[str, Any]], architectures: list[str], meta: dict[str, Any], path: Path) -> None:
    metrics = [
        ("End-to-end success (real draft + no model error + correct decision)", "end_to_end_success_pct", "%"),
        ("Model stages succeeded", "model_success_pct", "%"),
        ("Final policy checks pass (includes deterministic fallback)", "all_correct_pct", "%"),
        ("Correct next action", "next_action_correct_pct", "%"),
        ("Policy + deterministic rules followed", "policy_followed_pct", "%"),
        ("Human review flagged correctly", "human_review_correct_pct", "%"),
        ("Starter public minimum checks (6 cases)", "public_min_checks_pct", "%"),
        ("Model draft fully correct *before* guardrail", "raw_all_correct_pct", "%"),
        ("Model draft next action correct *before* guardrail", "raw_next_action_correct_pct", "%"),
        ("Model draft policy-complete *before* guardrail", "raw_policy_followed_pct", "%"),
        ("Draft evidence exactly supported by facts available before final guardrail", "draft_grounding_rate", "ratio"),
        ("Agent tool coverage (of 7 tools)", "agent_tool_coverage", "ratio"),
        ("Guardrail corrections per case", "guardrail_corrections_per_case", ""),
        ("Avg latency", "avg_latency_ms", "ms"),
        ("p95 latency", "p95_latency_ms", "ms"),
        ("Avg LLM calls", "avg_llm_calls", ""),
        ("Avg time waiting for rate limits (included in latency)", "avg_rate_limit_wait_ms", "ms"),
        ("Rate-limit retries", "rate_limit_retries", ""),
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
            cells.append("n/a" if v is None else (f"{v}{unit}" if unit == "%" else (f"{v:.3f}" if unit == "ratio" else (f"${v:.4f}" if unit == "USD" else f"{v:g}{(' ' + unit) if unit else ''}"))))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", f"Result kind: **{meta['result_kind']}**. Complete: **{meta['complete']}**. Seed: {meta['seed']}. Transport: {meta['vendor_transport']}.",
              "", "Draft grounding uses exact copied facts; paraphrases count as unsupported. Rationale prose requires human review. LLM calls count logical attempts, including failures; Rate-limit retries are counted separately. Cost is unavailable unless explicit prices were supplied.",
              "", "## Per-case outcomes", ""]
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


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    files = [*ROOT.glob("src/**/*.py"), *ROOT.glob("data/*"), *ROOT.glob("evals/*.py"), *ROOT.glob("evals/*.json"), ROOT / "uv.lock", ROOT / "pyproject.toml"]
    for path in sorted(p for p in files if p.is_file()):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def git_value(args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--architectures", nargs="+", choices=["single", "staged"], default=["single", "staged"])
    parser.add_argument("--cases", choices=["public", "all"], default="all")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--provider", choices=["openai", "mock"], default=None, help="overrides LLM_PROVIDER")
    parser.add_argument("--out", default=None, help="output directory (default evals/results, or evals/results/mock)")
    parser.add_argument("--resume", action="store_true", help="append unattempted trials in --out, retaining all earlier failures")
    parser.add_argument("--allow-degraded", action="store_true", help="keep going and report even if the model failed on some runs")
    parser.add_argument("--vendor-transport", choices=["inprocess", "http"], default="inprocess", help="same FastAPI routes in-process, or an independently running HTTP service")
    parser.add_argument("--case-id", action="append", help="run only these case IDs (repeatable)")
    parser.add_argument("--seed", type=int, default=42, help="seed for paired architecture order")
    parser.add_argument("--input-price", type=float, help="USD per million input tokens, from provider pricing")
    parser.add_argument("--output-price", type=float, help="USD per million output tokens, from provider pricing")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    if (args.input_price is None) != (args.output_price is None):
        parser.error("provide both --input-price and --output-price, or neither")
    if any(v is not None and (not math.isfinite(v) or v < 0) for v in (args.input_price, args.output_price)):
        parser.error("prices must be finite and nonnegative")
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    provider = os.getenv("LLM_PROVIDER", "openai")
    cases = load_cases(args.cases)
    if args.case_id:
        known = {c["case_id"] for c in cases}
        if set(args.case_id) - known:
            parser.error("unknown case ID: " + ", ".join(sorted(set(args.case_id) - known)))
        cases = [c for c in cases if c["case_id"] in args.case_id]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    base = ROOT / "evals" / "results" / ("mock" if provider == "mock" else "live")
    out_dir = Path(args.out).resolve() if args.out else base / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.resume and not args.out:
        parser.error("--resume requires --out pointing to an existing experiment")
    if (out_dir / "trials.jsonl").exists() and not args.resume:
        parser.error("output already contains trials; choose a new directory to preserve prior evidence")
    llm = get_llm_client()
    if args.input_price is not None:
        PRICES[llm.model] = (args.input_price, args.output_price)
    manifest = {"provider": provider, "model": llm.model, "effort": getattr(llm, "effort", "n/a"),
                "cases": [c["case_id"] for c in cases], "architectures": args.architectures,
                "repeats": args.repeats, "seed": args.seed, "source_sha256": source_fingerprint(),
                "vendor_transport": args.vendor_transport, "prices": list(PRICES[llm.model]) if llm.model in PRICES else None}
    manifest_path = out_dir / "manifest.json"
    rows: list[dict[str, Any]] = []
    if args.resume:
        if not manifest_path.exists() or json.loads(manifest_path.read_text()) != manifest:
            parser.error("resume requires the original source, cases, provider/model/effort and experiment settings")
        rows = [json.loads(line) for line in (out_dir / "trials.jsonl").read_text().splitlines() if line.strip()]
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    completed = {(r["case_id"], r["architecture"], r["repeat"]) for r in rows}
    rng = random.Random(args.seed)
    print(f"Evaluation · provider={provider} model={llm.model} · {len(cases)} cases · repeats={args.repeats} · architectures={args.architectures}", flush=True)
    aborted = False
    with vendor_transport(args.vendor_transport), (out_dir / "trials.jsonl").open("a" if args.resume else "w", encoding="utf-8") as checkpoint:
        for repeat in range(1, args.repeats + 1):
            ordered_cases = list(cases)
            rng.shuffle(ordered_cases)
            for case in ordered_cases:
                order = list(args.architectures)
                rng.shuffle(order)
                for architecture in order:
                    if (case["case_id"], architecture, repeat) in completed:
                        continue
                    row = run_case(case, architecture, llm, repeat)
                    rows.append(row)
                    checkpoint.write(json.dumps(row, default=str, allow_nan=False) + "\n")
                    checkpoint.flush()
                    status = "ERROR" if row.get("error") or row.get("_trace_errors") else ("PASS" if row["end_to_end_success"] else "FAIL")
                    print(f"{status} {architecture:6s} r{repeat} {row['case_id']} {row['latency_ms']:.0f} ms · draft={row.get('raw_all_correct', False)}", flush=True)
                    if row.get("error") or row.get("_trace_errors"):
                        print(f"  {row.get('error') or row['_trace_errors']}", flush=True)
                        if not args.allow_degraded and provider != "mock":
                            aborted = True
                            break
                if aborted:
                    break
            if aborted:
                break


    # Per-run CSV, decisions JSONL, summary JSON + Markdown
    fieldnames = list(dict.fromkeys(k for row in rows for k in row if not k.startswith("_")))
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
                                "decision": r.get("_decision"), "draft": r.get("_draft"), "trace": r.get("_trace")}, default=str) + "\n")
    from src.rules import reference_date
    meta = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "provider": provider, "model": llm.model, "effort": getattr(llm, "effort", "n/a"),
        "case_count": len(cases), "repeats": args.repeats, "reference_date": str(reference_date()),
        "result_kind": "scripted_smoke" if provider == "mock" else "model_experiment",
        "complete": len(rows) == len(cases) * len(args.architectures) * args.repeats, "actual_runs": len(rows), "seed": args.seed,
        "vendor_transport": args.vendor_transport, "python": platform.python_version(),
        "prices_usd_per_million": PRICES.get(llm.model),
        "source_sha256": source_fingerprint(),
        "git_commit": git_value(["rev-parse", "HEAD"]),
        "git_dirty": bool(git_value(["status", "--porcelain"])),
    }
    summary = summarise(rows, args.architectures)
    (out_dir / "summary.json").write_text(json.dumps({"meta": meta, "summary": summary}, indent=2, allow_nan=False), encoding="utf-8")
    write_markdown(summary, rows, args.architectures, meta, out_dir / "summary.md")
    print()
    for arch in args.architectures:
        s = summary[arch]
        print(f"{arch:6s}  fully correct {s['all_correct_pct']}%  next-action {s['next_action_correct_pct']}%  policy {s['policy_followed_pct']}%  "
              f"draft-correct {s['raw_all_correct_pct']}%  corrections/case {s['guardrail_corrections_per_case']}  "
              f"latency {s['avg_latency_ms']} ms  llm {s['avg_llm_calls']}  tools {s['avg_tool_calls']}")
    print(f"\nWritten to {out_dir}/ (trials.jsonl, runs.csv, decisions.jsonl, summary.json, summary.md)")
    if aborted:
        print("Experiment incomplete: stopped on a model error. Partial evidence preserved; do not use as a ship comparison.")
        raise SystemExit(2)
    if any(not r.get("end_to_end_success") for r in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
