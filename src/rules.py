"""Deterministic policy engine.

Everything in this module is plain code with no model involvement. It owns:
thresholds, budget arithmetic, date-based staleness, registry/API conflict
detection, required-field checks, and the prompt-injection scan.

The LLM layer may *add* context on top of these findings but can never lower
them; see `src/guardrails.py` for how the two are reconciled.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from src.contracts import EvidenceItem
from src.data_access import load_policy_text

# --------------------------------------------------------------------------
# Reference date and constants
# --------------------------------------------------------------------------

_FALLBACK_REFERENCE_DATE = date(2026, 9, 30)
SECURITY_ASSESSMENT_VALIDITY_DAYS = 365
LEGAL_NEW_VENDOR_SPEND_THRESHOLD = Decimal("10000")

APPROVAL_ORDER = ["Manager", "Department Head", "Procurement", "Finance", "CFO", "Security", "Privacy", "Legal"]

# (upper bound inclusive, approvals). Amounts are Decimal to avoid float edge cases at the boundaries.
APPROVAL_TIERS: list[tuple[Decimal | None, list[str]]] = [
    (Decimal("1000"), ["Manager"]),
    (Decimal("10000"), ["Department Head", "Procurement"]),
    (Decimal("25000"), ["Department Head", "Finance", "Procurement"]),
    (None, ["Department Head", "Finance", "CFO", "Procurement"]),
]

BLOCKING_FLAGS = {
    "missing_information",
    "budget_insufficient",
    "budget_unverified",
    "vendor_risk_unavailable",
    "conflicting_vendor_evidence",
    "evidence_unavailable",
}

FLAG_TAXONOMY = {
    "existing_tool_overlap",
    "budget_insufficient",
    "budget_unverified",
    "security_review_required",
    "privacy_review_required",
    "legal_review_required",
    "vendor_review_expired",
    "conflicting_vendor_evidence",
    "vendor_risk_unavailable",
    "prompt_injection_detected",
    "missing_information",
    "evidence_unavailable",
}


def reference_date() -> date:
    """Read the snapshot date from the policy document; fall back to the documented constant."""
    try:
        text = load_policy_text()
    except OSError:
        return _FALLBACK_REFERENCE_DATE
    match = re.search(r"reference date:\*{0,2}\s*(\d{4}-\d{2}-\d{2})", text, flags=re.IGNORECASE)
    if match:
        return date.fromisoformat(match.group(1))
    return _FALLBACK_REFERENCE_DATE


# --------------------------------------------------------------------------
# Untrusted text scan (policy section 9)
# --------------------------------------------------------------------------

_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ignore_rules", re.compile(r"\b(ignore|disregard|bypass|skip|forget)\b[^.]{0,60}\b(rules?|polic(y|ies)|instructions?|controls?|checks?|review|approval)", re.I)),
    ("fabricated_approval", re.compile(r"\b(treat|consider|mark|regard|assume)\b[^.]{0,60}\b(as|is)\b[^.]{0,30}\b(approved|authori[sz]ed|signed[- ]off|cleared)", re.I)),
    ("fabricated_approval", re.compile(r"\b(already|pre)[- ]?(approved|authori[sz]ed)\b", re.I)),
    ("command_to_approve", re.compile(r"\bapprove\b[^.]{0,40}\b(immediately|now|automatically|without)\b", re.I)),
    ("role_override", re.compile(r"\b(you are now|act as|new instructions?|system prompt|developer message|ignore (the )?(above|previous|prior))\b", re.I)),
    ("secret_exfil", re.compile(r"\b(reveal|print|show|expose)\b[^.]{0,40}\b(api key|secret|password|credential|token|system prompt)", re.I)),
    ("override_review", re.compile(r"\b(no|without|skip)\b[^.]{0,20}\b(security|privacy|legal)\b[^.]{0,20}\breview\b", re.I)),
]


@dataclass
class InjectionScan:
    detected: bool
    matches: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    cleaned_text: str = ""


def scan_untrusted_text(texts: dict[str, Any]) -> InjectionScan:
    """Scan free-text fields for instruction-like content. Returns the matches and the
    text with matching sentences removed so completeness checks look at real content only."""
    matches: list[str] = []
    fields_hit: list[str] = []
    cleaned_parts: list[str] = []
    for field_name, raw in texts.items():
        if raw is None:
            continue
        text = str(raw)
        sentences = re.split(r"(?<=[.!?])\s+", text)
        kept: list[str] = []
        for sentence in sentences:
            hit = [label for label, pattern in _INJECTION_PATTERNS if pattern.search(sentence)]
            if hit:
                matches.extend(f"{field_name}: {label}" for label in dict.fromkeys(hit))
                if field_name not in fields_hit:
                    fields_hit.append(field_name)
            else:
                kept.append(sentence)
        cleaned_parts.append(" ".join(kept).strip())
    return InjectionScan(
        detected=bool(matches),
        matches=matches,
        fields=fields_hit,
        cleaned_text=" ".join(p for p in cleaned_parts if p),
    )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite():
        return None
    return amount


def approval_tier(annual_cost: Decimal) -> tuple[int, list[str]]:
    """Policy section 4. Returns (tier_index, approvals)."""
    for index, (upper, approvals) in enumerate(APPROVAL_TIERS, start=1):
        if upper is None or annual_cost <= upper:
            return index, list(approvals)
    raise AssertionError("unreachable")


def sort_approvals(approvals: set[str] | list[str]) -> list[str]:
    known = [a for a in APPROVAL_ORDER if a in approvals]
    unknown = sorted(a for a in approvals if a not in APPROVAL_ORDER)
    return known + unknown


def _norm(value: Any) -> str:
    return re.sub(r"[\s_\-]+", " ", str(value or "")).strip().lower()


_SECURITY_DATA_KEYWORDS = ("source code", "code", "repo", "production", "confidential", "pii", "personal", "credential", "secret", "cloud", "prod")
_SECURITY_INTEGRATION_KEYWORDS = ("production", "cloud account", "git", "repositor", "credential", "secret", "database", "api key", "source")
_PRIVACY_DATA_KEYWORDS = ("pii", "personal data", "employee data", "customer data")
_UNKNOWN_DATA_VALUES = {"", "unknown", "unclear", "tbd", "n/a", "na", "?"}
_NO_DATA_VALUES = {"none", "no data", "no access"}


def data_access_profile(level: Any) -> dict[str, bool]:
    text = _norm(level)
    return {
        "unknown": text in _UNKNOWN_DATA_VALUES,
        "none": text in _NO_DATA_VALUES,
        "security_sensitive": any(k in text for k in _SECURITY_DATA_KEYWORDS),
        "pii": any(k in text for k in _PRIVACY_DATA_KEYWORDS),
        "confidential": "confidential" in text,
        "source_code": "source" in text or "code" in text,
        "production": "prod" in text,
    }


def integration_is_sensitive(integrations: list[Any] | None) -> list[str]:
    hits: list[str] = []
    if not isinstance(integrations, list):
        integrations = [integrations] if integrations else []
    for item in integrations or []:
        text = _norm(item)
        if any(k in text for k in _SECURITY_INTEGRATION_KEYWORDS):
            hits.append(str(item))
    return hits


def normalize_security_status(value: Any) -> str:
    """Map registry and API vocabularies onto one scale."""
    text = _norm(value)
    if text in {"approved", "current", "passed", "complete", "completed"}:
        return "approved"
    if text in {"expired", "stale", "lapsed"}:
        return "expired"
    if text in {"pending", "not completed", "in progress", "incomplete", "not started", "draft"}:
        return "not_completed"
    if text in {"unknown", "", "none", "n/a"}:
        return "unknown"
    return text.replace(" ", "_")


# --------------------------------------------------------------------------
# Evidence pack: the raw tool results the rules operate on
# --------------------------------------------------------------------------

@dataclass
class EvidencePack:
    """Raw tool outputs for one request. Any entry may be None if the tool failed."""

    request: dict[str, Any]
    requester: dict[str, Any] | None = None
    budget: dict[str, Any] | None = None
    catalog: dict[str, Any] | None = None
    vendor_registry: dict[str, Any] | None = None
    vendor_risk: dict[str, Any] | None = None
    purchase_history: dict[str, Any] | None = None


@dataclass
class RuleFindings:
    required_approvals: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    reviews: list[str] = field(default_factory=list)           # Security / Privacy / Legal
    approval_tier: int | None = None
    annual_cost: Decimal | None = None
    budget_ok: bool | None = None
    overlap_kind: str | None = None                            # same_product / same_category / expansion
    overlap_covers_department: bool = False
    vendor_status: str = "unknown"
    vendor_conflict: bool = False
    vendor_unavailable: bool = False
    injection: InjectionScan | None = None
    blocking_flags: list[str] = field(default_factory=list)
    allowed_next_actions: list[str] = field(default_factory=list)
    preferred_next_action: str = "route_for_reviews"
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "required_approvals": self.required_approvals,
            "risk_flags": self.risk_flags,
            "missing_information": self.missing_information,
            "reviews": self.reviews,
            "approval_tier": self.approval_tier,
            "annual_cost_usd": float(self.annual_cost) if self.annual_cost is not None else None,
            "budget_ok": self.budget_ok,
            "overlap_kind": self.overlap_kind,
            "overlap_covers_department": self.overlap_covers_department,
            "vendor_status": self.vendor_status,
            "vendor_conflict": self.vendor_conflict,
            "vendor_unavailable": self.vendor_unavailable,
            "prompt_injection": {
                "detected": bool(self.injection and self.injection.detected),
                "matches": self.injection.matches if self.injection else [],
            },
            "blocking_flags": self.blocking_flags,
            "allowed_next_actions": self.allowed_next_actions,
            "preferred_next_action": self.preferred_next_action,
            "evidence": [e.model_dump() for e in self.evidence],
            "notes": self.notes,
        }


# --------------------------------------------------------------------------
# Section-by-section checks
# --------------------------------------------------------------------------

def check_required_fields(request: dict[str, Any], requester: dict[str, Any] | None, injection: InjectionScan) -> list[str]:
    """Policy section 1. Returns human-readable missing items."""
    missing: list[str] = []
    if not requester or not requester.get("employee_id"):
        missing.append("requester could not be resolved to an employee record")
    elif not requester.get("department"):
        missing.append("requester department")
    if not str(request.get("product_name") or "").strip():
        missing.append("product name")
    if not str(request.get("vendor_name") or "").strip():
        missing.append("vendor name")
    cost = to_decimal(request.get("annual_cost_usd"))
    if cost is None or cost < 0:
        missing.append("annual cost (USD) or a reasonable annual estimate")
    users = request.get("user_count")
    try:
        count = to_decimal(users)
        users_ok = not isinstance(users, bool) and count is not None and count > 0 and count == count.to_integral_value()
    except (TypeError, ValueError, OverflowError):
        users_ok = False
    if not users_ok:
        missing.append("number of users / licenses")
    justification_scan = scan_untrusted_text({"business_justification": request.get("business_justification")})
    justification = justification_scan.cleaned_text
    if len(justification.split()) < 4:
        missing.append("business purpose (a usable justification)")
    if data_access_profile(request.get("data_access_level"))["unknown"]:
        missing.append("intended data-access level")
    if not isinstance(request.get("requested_integrations"), list) or any(not isinstance(x, str) or not x.strip() for x in request.get("requested_integrations", [])):
        missing.append("required integrations (state 'none' if not applicable)")
    return missing


def evaluate(pack: EvidencePack) -> RuleFindings:
    """Apply the whole policy to one evidence pack. Pure function of its input."""
    request = pack.request
    findings = RuleFindings()
    approvals: set[str] = set()
    flags: list[str] = []
    ref_date = reference_date()

    def flag(name: str) -> None:
        if name not in flags:
            flags.append(name)

    def evidence(source: str, finding: str, reference: str | None = None) -> None:
        findings.evidence.append(EvidenceItem(source=source, finding=finding, reference=reference))

    # -- Section 9: untrusted text -------------------------------------------------
    injection = scan_untrusted_text({
        "business_justification": request.get("business_justification"),
        "product_name": request.get("product_name"),
        "vendor_name": request.get("vendor_name"),
        "notes": request.get("notes"),
        "vendor_registry_notes": (pack.vendor_registry or {}).get("notes"),
        "vendor_risk_notes": (pack.vendor_risk or {}).get("notes"),
    })
    findings.injection = injection
    if injection.detected:
        flag("prompt_injection_detected")
        evidence(
            "policy_checks",
            f"Instruction-like text found in {', '.join(injection.fields)} ({', '.join(dict.fromkeys(injection.matches))}); treated as data and ignored.",
            "Policy §9",
        )

    # -- Section 1: completeness ---------------------------------------------------
    missing = check_required_fields(request, pack.requester, injection)
    findings.missing_information = missing
    if missing:
        flag("missing_information")
        evidence("policy_checks", f"Request is not ready for approval; missing: {'; '.join(missing)}.", "Policy §1")

    # -- Section 4: thresholds -----------------------------------------------------
    cost = to_decimal(request.get("annual_cost_usd"))
    if cost is not None and cost >= 0:
        findings.annual_cost = cost
        tier, tier_approvals = approval_tier(cost)
        findings.approval_tier = tier
        approvals.update(tier_approvals)
        if tier == 1 and pack.requester and not pack.requester.get("manager_id"):
            approvals.discard("Manager")
            approvals.add("Department Head")
            findings.notes.append("Requester has no manager on record; Department Head substitutes for Manager approval.")
        evidence("policy_checks", f"Annual amount ${cost:,.2f} falls in approval tier {tier}: {' + '.join(tier_approvals)}.", "Policy §4")
    else:
        findings.notes.append("Approval tier cannot be computed without an annual cost.")

    # -- Section 2: budget ---------------------------------------------------------
    budget = pack.budget or {}
    available = to_decimal(budget.get("available_usd"))
    if cost is not None and cost >= 0 and budget.get("found") and available is not None and budget.get("snapshot_arithmetic_consistent", True):
        available = to_decimal(budget.get("available_usd")) or Decimal(0)
        findings.budget_ok = cost <= available
        if findings.budget_ok:
            evidence("check_budget", f"${cost:,.0f} is within {budget['department']}'s available software budget of ${available:,.0f}.", budget.get("reference"))
        else:
            flag("budget_insufficient")
            approvals.add("Finance")
            evidence("check_budget", f"${cost:,.0f} exceeds {budget['department']}'s available software budget of ${available:,.0f} by ${cost - available:,.0f}.", budget.get("reference"))
    elif cost is not None and cost >= 0:
        flag("budget_unverified")
        approvals.add("Finance")
        evidence("check_budget", f"No software budget line found for department '{budget.get('department') or 'unknown'}'; budget could not be verified.", "Policy §2 / §10")

    # -- Section 3: overlap --------------------------------------------------------
    catalog = pack.catalog or {}
    matches = catalog.get("matches") or []
    if matches:
        kinds = {m.get("match_type") for m in matches}
        if "same_product" in kinds:
            findings.overlap_kind = "same_product"
        elif "same_vendor_same_category" in kinds:
            findings.overlap_kind = "expansion"
        elif "same_category" in kinds:
            findings.overlap_kind = "same_category"
        if findings.overlap_kind:
            flag("existing_tool_overlap")
            top = matches[0]
            dept = _norm((pack.requester or {}).get("department"))
            findings.overlap_covers_department = _norm(top.get("scope")) in {"company wide", "companywide", "all", dept} if dept else False
            evidence(
                "search_software_catalog",
                f"Catalog already lists {top['product_name']} ({top['vendor_name']}, {top['category']}, {top['status']}, {top['licensed_seats']} seats, scope {top['scope']}); overlap kind: {findings.overlap_kind}.",
                top.get("software_id"),
            )

    # -- Sections 5-7: vendor status, security, privacy, legal ---------------------
    registry = pack.vendor_registry or {}
    risk = pack.vendor_risk or {}
    registry_found = bool(registry.get("found"))
    risk_available = bool(risk.get("available"))
    # "No record for this vendor" is an answer (the assessment is missing); an outage or timeout is not.
    risk_missing = (not risk_available) and risk.get("error_kind") == "not_found"
    findings.vendor_unavailable = (not risk_available) and not risk_missing

    registry_status = normalize_security_status(registry.get("security_status")) if registry_found else "unknown"
    api_status = normalize_security_status(risk.get("security_review_status")) if risk_available else "unknown"
    registry_date = _parse_date(registry.get("security_review_date")) if registry_found else None
    api_date = _parse_date(risk.get("last_review_date")) if risk_available else None

    def is_current(review_date: date | None) -> bool | None:
        if review_date is None:
            return None
        return review_date <= ref_date < review_date + timedelta(days=SECURITY_ASSESSMENT_VALIDITY_DAYS)

    registry_current = is_current(registry_date)
    api_current = is_current(api_date)

    # A registry row saying "approved" with a review older than 365 days is itself expired.
    effective_registry_status = registry_status
    if registry_status == "approved" and registry_current is not True:
        effective_registry_status = "expired" if registry_date and registry_date <= ref_date else "unknown"
    effective_api_status = api_status
    if api_status == "approved" and api_current is not True:
        effective_api_status = "expired" if api_date and api_date <= ref_date else "unknown"

    if risk_missing:
        findings.vendor_status = "not_completed"
        evidence("get_vendor_risk_assessment", f"Vendor-risk service has no assessment on record for {request.get('vendor_name')}; treated as not completed.", risk.get("reference"))
    elif not risk_available:
        flag("vendor_risk_unavailable")
        evidence("get_vendor_risk_assessment", f"Vendor-risk service could not verify {request.get('vendor_name')}: {risk.get('error') or 'no response'}. No favourable status is assumed.", "Policy §10")
        findings.vendor_status = effective_registry_status
    else:
        findings.vendor_status = effective_api_status
        evidence(
            "get_vendor_risk_assessment",
            f"Vendor-risk service reports {request.get('vendor_name')}: status {api_status}, risk level {risk.get('risk_level')}, last review {risk.get('last_review_date') or 'none'}"
            + (f" ({(ref_date - api_date).days} days before the {ref_date} snapshot)" if api_date else "")
            + ".",
            risk.get("reference"),
        )
        conflict_reasons = []
        if registry_found and registry_status != "unknown" and api_status != "unknown" and registry_status != api_status:
            conflict_reasons.append(f"registry says '{registry.get('security_status')}' ({registry.get('security_review_date') or 'no date'}), service says '{risk.get('security_review_status')}' ({risk.get('last_review_date') or 'no date'})")
        if registry_date and api_date and registry_date != api_date:
            conflict_reasons.append(f"review dates differ ({registry_date} vs {api_date})")
        if conflict_reasons:
            findings.vendor_conflict = True
            flag("conflicting_vendor_evidence")
            evidence("get_vendor_registry_record", "Internal registry and vendor-risk service disagree: " + "; ".join(conflict_reasons) + ". Neither source is chosen silently.", "Policy §5")

    if registry_found:
        evidence(
            "get_vendor_registry_record",
            f"Registry lists {registry.get('vendor_name')} as procurement status '{registry.get('procurement_status')}', security '{registry.get('security_status')}' (reviewed {registry.get('security_review_date') or 'never'}), legal terms '{registry.get('legal_terms_status')}'.",
            registry.get("vendor_id"),
        )
    else:
        evidence("get_vendor_registry_record", f"{request.get('vendor_name')} is not in the internal vendor registry; treated as a new vendor.", "Policy §7")

    # Security (section 5)
    profile = data_access_profile(request.get("data_access_level"))
    sensitive_integrations = integration_is_sensitive(request.get("requested_integrations"))
    security_reasons: list[str] = []
    if profile["security_sensitive"]:
        security_reasons.append(f"data access level '{request.get('data_access_level')}'")
    if sensitive_integrations:
        security_reasons.append(f"integration with {', '.join(sensitive_integrations)}")
    if findings.vendor_status in {"expired"} or effective_registry_status == "expired":
        security_reasons.append("vendor security assessment has expired (older than 365 days)")
        flag("vendor_review_expired")
    elif findings.vendor_unavailable:
        security_reasons.append("current vendor security assessment could not be verified (vendor-risk service unavailable)")
    elif findings.vendor_status != "approved":
        security_reasons.append(f"vendor security assessment is {findings.vendor_status.replace('_', ' ')}")
    elif effective_registry_status == "unknown":
        security_reasons.append("registry assessment status/date cannot be confirmed as current")
    if findings.vendor_conflict:
        security_reasons.append("conflicting vendor evidence")
    if security_reasons:
        flag("security_review_required")
        approvals.add("Security")
        findings.reviews.append("Security")
        evidence("policy_checks", "Security review required: " + "; ".join(security_reasons) + ".", "Policy §5")

    # Privacy (section 6)
    outside_region = bool(risk.get("stores_data_outside_region")) if risk_available else False
    processes_personal = bool(risk.get("processes_personal_data")) if risk_available else False
    privacy_reasons: list[str] = []
    if profile["pii"]:
        privacy_reasons.append(f"tool will process {request.get('data_access_level')}")
    if outside_region and (profile["pii"] or profile["confidential"] or profile["security_sensitive"]):
        privacy_reasons.append("vendor stores data outside the operating region")
    if privacy_reasons:
        flag("privacy_review_required")
        approvals.add("Privacy")
        findings.reviews.append("Privacy")
        evidence("policy_checks", "Privacy review required: " + "; ".join(privacy_reasons) + ".", "Policy §6")
    elif processes_personal and outside_region and profile["unknown"]:
        findings.notes.append("Vendor processes personal data outside the region; privacy need cannot be judged until the data-access level is known.")

    # Legal (section 7)
    legal_reasons: list[str] = []
    vendor_is_new = (not registry_found) or _norm(registry.get("procurement_status")) != "approved"
    if vendor_is_new and cost is not None and cost >= LEGAL_NEW_VENDOR_SPEND_THRESHOLD:
        legal_reasons.append(f"new vendor with annual spend ${cost:,.0f} (>= $10,000)")
    if registry_found and _norm(registry.get("legal_terms_status")) not in {"approved", "standard"}:
        legal_reasons.append(f"legal terms status is '{registry.get('legal_terms_status')}'")
    elif not registry_found:
        legal_reasons.append("no approved legal terms on file")
    if outside_region and (profile["pii"] or profile["confidential"]):
        legal_reasons.append("cross-region data processing of sensitive data")
    if legal_reasons:
        flag("legal_review_required")
        approvals.add("Legal")
        findings.reviews.append("Legal")
        evidence("policy_checks", "Legal review required: " + "; ".join(legal_reasons) + ".", "Policy §7")

    # Section 8: AI tools get no shortcut from prior purchases
    if "ai" in _norm(request.get("category")).split() or "ai" in _norm(request.get("product_name")).split():
        if findings.overlap_kind and (profile["security_sensitive"] or profile["pii"] or profile["confidential"]):
            findings.notes.append("AI tool already in the catalog; the prior purchase does not authorise this data class (policy §8).")

    # A failed catalog/history/registry lookup is not an empty successful lookup.
    for source, result in (("search_software_catalog", pack.catalog),
                           ("get_vendor_registry_record", pack.vendor_registry),
                           ("get_purchase_history", pack.purchase_history)):
        if result is None or "error" in result:
            flag("evidence_unavailable")
            evidence(source, "Required evidence could not be verified; Procurement must complete this check manually.", "Policy §10")

    # -- Assemble ----------------------------------------------------------------
    if missing:
        # Thresholds and reviews cannot be settled on an incomplete request; keep whatever is already
        # determinable (e.g. Security for a known-sensitive integration) but do not invent the rest.
        findings.notes.append("Approvals listed are partial until the missing information is supplied.")
    findings.required_approvals = sort_approvals(approvals)
    findings.risk_flags = flags
    findings.blocking_flags = [f for f in flags if f in BLOCKING_FLAGS]
    findings.allowed_next_actions, findings.preferred_next_action = _next_actions(findings)
    return findings


def _next_actions(f: RuleFindings) -> tuple[list[str], str]:
    """Which next actions are consistent with the deterministic findings. The LLM picks within this set."""
    if f.missing_information:
        return ["request_clarification"], "request_clarification"
    if f.vendor_unavailable or f.vendor_conflict:
        return ["escalate_manual_review", "route_for_reviews"], "escalate_manual_review"
    if "evidence_unavailable" in f.risk_flags:
        return ["escalate_manual_review"], "escalate_manual_review"
    if "budget_insufficient" in f.risk_flags or "budget_unverified" in f.risk_flags:
        allowed = ["budget_exception_required", "route_for_reviews", "evaluate_existing_tool_first"]
        return allowed, "budget_exception_required"
    if f.reviews:
        allowed = ["route_for_reviews"]
        if f.overlap_kind:
            allowed.append("evaluate_existing_tool_first")
        return allowed, "route_for_reviews"
    if f.overlap_kind in {"same_product", "same_category"}:
        return ["evaluate_existing_tool_first", "proceed_to_approval"], "evaluate_existing_tool_first"
    if f.overlap_kind == "expansion":
        # Same vendor and category already under contract. Whether this is a legitimate seat/add-on
        # expansion or a duplicate purchase is a judgement on the justification, so both actions are
        # allowed; the conservative default is to check existing capacity first when the existing
        # agreement already covers the requesting department (policy section 3).
        preferred = "evaluate_existing_tool_first" if f.overlap_covers_department else "proceed_to_approval"
        return ["proceed_to_approval", "evaluate_existing_tool_first"], preferred
    return ["proceed_to_approval"], "proceed_to_approval"


def _parse_date(value: Any) -> date | None:
    if not value or str(value).strip().lower() in {"nan", "none", "null"}:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None
