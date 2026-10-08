"""Durable application history. Experiments remain immutable, separate artifacts."""
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3

from src.audit import request_fingerprint
from src.contracts import CopilotDecision


def configuration(root: Path, provider: str, model: str) -> dict:
    """Identity of analysis inputs, excluding UI styling and credentials."""
    digest = sha256()
    files = [p for directory in ("src", "data", "mock_api") for p in (root/directory).rglob("*")
             if p.is_file() and p.suffix in {".py", ".json", ".csv", ".md"}]
    files += [root/name for name in ("pyproject.toml", "uv.lock") if (root/name).exists()]
    for path in sorted(files):
        digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes() + b"\0")
    return {"provider": provider, "model": model, "effort": os.getenv("LLM_EFFORT", "medium"),
            "analysis_sha256": digest.hexdigest(), "vendor_endpoint": os.getenv("VENDOR_RISK_BASE_URL", "")}


@dataclass
class SavedRun:
    request: dict
    config: dict
    decision: CopilotDecision
    created_at: str
    origin: str = "local"

    @property
    def run_id(self):
        return self.decision.run_id

    @property
    def architecture(self):
        return self.decision.telemetry.architecture

    def payload(self) -> dict:
        # trace is intentionally excluded by the public contract, but required
        # here to reopen tool activity, errors and the analyst handoff faithfully.
        return {"request": self.request, "config": self.config, "created_at": self.created_at,
                "origin": self.origin, "decision": self.decision.model_dump(mode="json"),
                "trace": self.decision.trace}

    @classmethod
    def from_payload(cls, value: dict):
        decision = CopilotDecision.model_validate({**value["decision"], "trace": value.get("trace", {})})
        if (not decision.run_id or decision.request_fingerprint != request_fingerprint(value["request"])
                or decision.request_id != value["request"].get("request_id")):
            raise ValueError("Saved analysis does not match its request")
        if not decision.telemetry or decision.telemetry.architecture not in {"single", "staged"}:
            raise ValueError("Saved analysis has no valid architecture")
        return cls(value["request"], value["config"], decision, value["created_at"], value.get("origin", "local"))


class RunStore:
    def __init__(self, path: Path):
        self.path = path

    def save(self, run: SavedRun) -> None:
        payload = run.payload()
        SavedRun.from_payload(payload)
        encoded = json.dumps(payload, sort_keys=True, default=str)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""CREATE TABLE IF NOT EXISTS analyses (
                run_id TEXT PRIMARY KEY, request_fingerprint TEXT NOT NULL,
                architecture TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)""")
            connection.execute("CREATE INDEX IF NOT EXISTS request_runs ON analyses(request_fingerprint, architecture, created_at)")
            previous = connection.execute("SELECT payload FROM analyses WHERE run_id = ?", (run.run_id,)).fetchone()
            if previous:
                if previous[0] != encoded:
                    raise ValueError("A stored run cannot be overwritten with different content")
                return
            connection.execute("INSERT INTO analyses VALUES (?, ?, ?, ?, ?)",
                               (run.run_id, request_fingerprint(run.request), run.architecture, run.created_at, encoded))

    def list_runs(self, request: dict | None = None, architecture: str | None = None, *, limit: int = 100) -> list[SavedRun]:
        if not self.path.exists():
            return []
        conditions, values = [], []
        if request is not None:
            conditions.append("request_fingerprint = ?")
            values.append(request_fingerprint(request))
        if architecture:
            conditions.append("architecture = ?")
            values.append(architecture)
        query = "SELECT payload FROM analyses" + (" WHERE " + " AND ".join(conditions) if conditions else "")
        query += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            rows = connection.execute(query, (*values, limit)).fetchall()
        return [SavedRun.from_payload(json.loads(row[0])) for row in rows]


def new_run(request: dict, config: dict, decision: CopilotDecision) -> SavedRun:
    return SavedRun(json.loads(json.dumps(request)), dict(config), decision, datetime.now(timezone.utc).isoformat())


def benchmark_runs(root: Path, request: dict, architecture: str) -> list[SavedRun]:
    """Expose existing sample results only when their full input hash matches.

    These are historical evidence, never current-policy approvals or cache hits.
    Nothing is imported into the local database or changed in the experiment.
    """
    directory = root/"evals/results/openai-comparison-20261008"
    meta = json.loads((directory/"summary.json").read_text())["meta"]
    matching = []
    for line in (directory/"decisions.jsonl").read_text().splitlines():
        item = json.loads(line)
        if item["architecture"] != architecture or not item.get("decision"):
            continue
        if item["decision"].get("request_fingerprint") != request_fingerprint(request):
            continue
        matching.append(SavedRun.from_payload({"request": request, "decision": item["decision"], "trace": item.get("trace", {}),
                        "created_at": meta["generated_at"], "origin": "benchmark",
                        "config": {"provider": "openai", "model": meta["model"], "effort": meta["effort"],
                                   "experiment": directory.name}}))
    return matching
