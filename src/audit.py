"""Local review records tied to the exact recommendation the reviewer saw.

This is a demo audit file, not an authenticated approval or routing service.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


def request_fingerprint(request: dict[str, Any]) -> str:
    return sha256(json.dumps(request, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def record_review(path: Path, decision, *, reviewer: str, action: str, note: str) -> str:
    if not reviewer.strip():
        raise ValueError("A reviewer name is required")
    event = {
        "run_id": decision.run_id,
        "request_fingerprint": decision.request_fingerprint,
        "reviewer": reviewer.strip(), "human_action": action, "note": note.strip(),
        "decision": decision.model_dump(),
    }
    event_id = request_fingerprint(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if json.loads(line).get("event_id") == event_id:
                return event_id
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"event_id": event_id, "recorded_at": datetime.now(timezone.utc).isoformat(), **event}, default=str) + "\n")
    return event_id
