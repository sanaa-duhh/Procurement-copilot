"""Load the procurement policy configuration and check it against the written policy.

`config/policy.toml` holds the values the policy engine enforces. The written policy
in `data/procurement_policy.md` remains the human source of truth, so
`check_against_document` compares the two and reports any drift.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "policy.toml"


@dataclass(frozen=True)
class DataClass:
    name: str
    labels: tuple[tuple[str, ...], ...]       # each label as a tuple of words
    security: bool
    privacy: bool
    confidential: bool = False


@dataclass(frozen=True)
class PolicyConfig:
    version: str
    document: Path
    approval_tiers: tuple[tuple[Decimal | None, tuple[str, ...]], ...]
    assessment_validity_days: int
    legal_new_vendor_threshold: Decimal
    reviews_before_overlap_check: bool
    data_classes: tuple[DataClass, ...]
    sensitive_integrations: tuple[tuple[str, ...], ...] = field(default_factory=tuple)


def words(text: object) -> tuple[str, ...]:
    """Lower-case word tokens; underscores, hyphens and punctuation separate words."""
    return tuple(t for t in re.split(r"[^a-z0-9]+", str(text or "").lower()) if t)


def contains_phrase(haystack: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    n = len(phrase)
    return n > 0 and any(haystack[i:i + n] == phrase for i in range(len(haystack) - n + 1))


def load(path: Path = CONFIG_PATH) -> PolicyConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    tiers = []
    for tier in raw["approval_tiers"]:
        bound = tier.get("up_to_usd")
        tiers.append((Decimal(str(bound)) if bound is not None else None, tuple(tier["approvals"])))
    bounds = [b for b, _ in tiers if b is not None]
    if bounds != sorted(bounds) or tiers[-1][0] is not None or len(bounds) != len(tiers) - 1:
        raise ValueError("approval_tiers must be ascending and end with one unbounded tier")
    classes = tuple(
        DataClass(name=name, labels=tuple(words(label) for label in spec["labels"]),
                  security=bool(spec["security"]), privacy=bool(spec["privacy"]),
                  confidential=bool(spec.get("confidential", False)))
        for name, spec in raw["data_classes"].items()
    )
    return PolicyConfig(
        version=str(raw["policy"]["version"]),
        document=ROOT / raw["policy"]["document"],
        approval_tiers=tuple(tiers),
        assessment_validity_days=int(raw["security"]["assessment_validity_days"]),
        legal_new_vendor_threshold=Decimal(str(raw["legal"]["new_vendor_spend_threshold_usd"])),
        reviews_before_overlap_check=bool(raw["sequencing"]["specialist_reviews_before_overlap_check"]),
        data_classes=classes,
        sensitive_integrations=tuple(words(p) for p in raw["integrations"]["security_sensitive"]),
    )


@lru_cache(maxsize=1)
def current() -> PolicyConfig:
    return load()


_MONEY = r"\$([\d,]+(?:\.\d+)?)"


def check_against_document(config: PolicyConfig, text: str) -> list[str]:
    """Return human-readable differences between the config and the written policy."""
    problems: list[str] = []

    version = re.search(r"Policy version:\*{0,2}\s*([\w.\-]+)", text)
    if not version or version.group(1) != config.version:
        problems.append(f"policy version: document says {version.group(1) if version else 'nothing'}, config says {config.version}")

    # §4 table rows look like: | Up to $1,000 | Manager |  /  | $1,000.01 - $10,000 | ... |  /  | Above $25,000 | ... |
    rows = re.findall(r"^\|\s*([^|]*\$[^|]*)\|\s*([^|]+)\|", text, flags=re.M)
    doc_tiers: list[tuple[Decimal | None, tuple[str, ...]]] = []
    for amount, approvals in rows:
        names = tuple(a.strip() for a in approvals.split("+"))
        amounts = [Decimal(m.replace(",", "")) for m in re.findall(_MONEY, amount)]
        if not amounts:
            continue
        doc_tiers.append((None if amount.strip().lower().startswith("above") else amounts[-1], names))
    if [(b, set(a)) for b, a in doc_tiers] != [(b, set(a)) for b, a in config.approval_tiers]:
        problems.append(f"approval tiers differ: document {doc_tiers}, config {list(config.approval_tiers)}")

    days = re.search(r"current for \*{0,2}(\d+) days", text)
    if not days or int(days.group(1)) != config.assessment_validity_days:
        problems.append(f"assessment validity: document says {days.group(1) if days else 'nothing'} days, config says {config.assessment_validity_days}")

    legal = re.search(r"annual spend is \*{0,2}" + _MONEY + r" or more", text)
    if not legal or Decimal(legal.group(1).replace(",", "")) != config.legal_new_vendor_threshold:
        problems.append(f"legal new-vendor threshold: document says {legal.group(1) if legal else 'nothing'}, config says {config.legal_new_vendor_threshold}")
    return problems
