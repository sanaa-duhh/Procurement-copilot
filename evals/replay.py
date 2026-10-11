"""Replay saved trials through the current deterministic layer, without calling a model.

Every saved trial keeps the model's draft and the complete tool log. This script rebuilds
each run from those records, reruns the current policy engine and guardrail over the
*original* draft, and rescores it with the same labels. It answers one question: how would
the final decisions change if the policy layer changed, holding model behaviour fixed?

    uv run python evals/replay.py evals/results/openai-repeats-20261011

No tool is executed: the tool cache is pre-filled from the saved log, and the replay fails
if any lookup misses it. Raw-draft scores cannot change, because the drafts are reused as-is.
Output: replay.json and replay.md in the experiment directory.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "evals")]

from run_evals import score  # noqa: E402

from src import rules  # noqa: E402
from src.data_access import get_request  # noqa: E402
from src.guardrails import reconcile  # noqa: E402
from src.telemetry import RunTelemetryCounter  # noqa: E402
from src.tools import ToolRegistry  # noqa: E402
from src.tools.policy import gather_evidence  # noqa: E402


class ReplayMiss(RuntimeError):
    """A replayed run tried to execute a tool whose result was not in the saved log."""


def replay_record(record: dict, case: dict) -> dict:
    request = case.get("request") or get_request(case["request_id"])
    trace = record.get("trace") or {}
    telemetry = RunTelemetryCounter()
    registry = ToolRegistry(request=request, telemetry=telemetry)
    for entry in trace.get("tool_log", []):
        if not entry.get("cached"):
            registry.cache[entry["tool"] + ":" + json.dumps(entry["args"], sort_keys=True, default=str)] = entry["result"]
    findings = rules.evaluate(gather_evidence(registry, actor="guardrail"))
    if telemetry.tool_calls:
        raise ReplayMiss(f"{record['case_id']} {record['architecture']} r{record['repeat']}: {telemetry.tool_names}")
    draft = record.get("draft") or trace.get("draft")
    decision = reconcile(draft, findings, registry, request, telemetry, architecture=record["architecture"], model="replay", trace={})
    final = score(case["expectations"], next_action=decision.next_action, approvals=decision.required_approvals,
                  flags=decision.risk_flags, missing=decision.missing_information, human_review=decision.human_review_required)
    return {"case_id": record["case_id"], "architecture": record["architecture"], "repeat": record["repeat"],
            "next_action": decision.next_action, "all_correct": final["all_correct"], "failures": final["failures"],
            "corrections": decision.telemetry.guardrail_corrections}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("experiment", type=Path, help="experiment directory containing decisions.jsonl and runs.csv")
    args = parser.parse_args()
    directory = args.experiment if args.experiment.is_absolute() else ROOT / args.experiment

    cases = {c["case_id"]: c for c in json.loads((ROOT / "evals" / "cases.json").read_text())}
    with (directory / "runs.csv").open(newline="") as f:
        original = {(r["case_id"], r["architecture"], int(r["repeat"])): r for r in csv.DictReader(f)}
    records = [json.loads(line) for line in (directory / "decisions.jsonl").read_text().splitlines() if line.strip()]

    rows = [replay_record(r, cases[r["case_id"]]) for r in records]
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"trials": 0, "original_final": 0, "replayed_final": 0, "raw": 0})
    changed = []
    for row in rows:
        key = (row["case_id"], row["architecture"], int(row["repeat"]))
        before = original[key]["end_to_end_success"] == "True"
        t = totals[row["architecture"]]
        t["trials"] += 1
        t["original_final"] += before
        t["replayed_final"] += row["all_correct"]
        t["raw"] += original[key]["raw_all_correct"] == "True"
        if before != row["all_correct"]:
            changed.append({**row, "original_final": before})

    result = {"experiment": directory.name, "policy_version": rules.POLICY_VERSION, "totals": totals, "changed": changed, "rows": rows}
    (directory / "replay.json").write_text(json.dumps(result, indent=2, default=str))

    lines = [f"# Replay under the current policy layer", "",
             f"Experiment `{directory.name}` · policy v{rules.POLICY_VERSION} · {len(rows)} saved trials · no model or tool calls.", "",
             "The model drafts are the originals, so raw-draft scores are unchanged. Only the policy engine and guardrail were rerun.", "",
             "| Architecture | Raw draft passed | Final passed, as run | Final passed, replayed |", "|---|---:|---:|---:|"]
    for arch, t in sorted(totals.items()):
        lines.append(f"| {arch} | {t['raw']}/{t['trials']} | {t['original_final']}/{t['trials']} | {t['replayed_final']}/{t['trials']} |")
    lines += ["", "## Trials whose final result changed", ""]
    lines += [f"- **{c['case_id']}** {c['architecture']} r{c['repeat']}: {'fail → pass' if c['all_correct'] else 'pass → fail'} "
              f"(final action `{c['next_action']}`){'; still failing: ' + ' | '.join(c['failures']) if c['failures'] else ''}" for c in changed] or ["None."]
    remaining = [r for r in rows if not r["all_correct"]]
    lines += ["", "## Trials still failing after replay", ""]
    lines += [f"- **{r['case_id']}** {r['architecture']} r{r['repeat']}: {' | '.join(r['failures'])}" for r in remaining] or ["None."]
    (directory / "replay.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
