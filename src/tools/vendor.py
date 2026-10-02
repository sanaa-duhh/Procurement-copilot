from __future__ import annotations

import math
from typing import Any

from src.data_access import load_vendors
from src.vendor_client import VendorRiskNotFound, VendorRiskUnavailable, get_vendor_risk


def _clean(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def get_vendor_registry_record(vendor_name: str) -> dict[str, Any]:
    vendors = load_vendors()
    row = vendors[vendors["vendor_name"].str.strip().str.lower() == str(vendor_name).strip().lower()]
    if row.empty:
        return {"found": False, "vendor_name": vendor_name, "note": "vendor not in internal registry (new vendor)", "reference": "vendors.csv"}
    record = {k: _clean(v) for k, v in row.iloc[0].to_dict().items()}
    return {"found": True, **record, "reference": record.get("vendor_id")}


def get_vendor_risk_assessment(vendor_name: str) -> dict[str, Any]:
    """External tool. Never raises: an outage is returned as `available: False` so the policy engine
    can refuse to infer a favourable status (policy section 10)."""
    endpoint = f"/vendor-risk/{vendor_name}"
    try:
        payload = get_vendor_risk(vendor_name)
    except VendorRiskNotFound as exc:
        return {"available": False, "vendor_name": vendor_name, "error": str(exc), "error_kind": "not_found", "reference": endpoint}
    except VendorRiskUnavailable as exc:
        return {"available": False, "vendor_name": vendor_name, "error": str(exc), "error_kind": "unavailable", "reference": endpoint}
    return {"available": True, **payload, "reference": endpoint}
