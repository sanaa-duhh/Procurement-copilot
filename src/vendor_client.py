from __future__ import annotations

import os
from urllib.parse import quote

import requests
from datetime import date

from pydantic import BaseModel, ConfigDict, ValidationError
from typing import Literal


class VendorAssessment(BaseModel):
    model_config = ConfigDict(strict=True)
    vendor_name: str
    security_review_status: Literal["approved", "expired", "not_completed", "unknown"]
    last_review_date: str | None
    risk_level: Literal["low", "medium", "high", "unknown"]
    processes_personal_data: bool
    stores_data_outside_region: bool
    notes: str = ""


class VendorRiskUnavailable(RuntimeError):
    """Raised when the vendor-risk service cannot give an answer (outage, timeout, bad payload)."""


class VendorRiskNotFound(LookupError):
    """Raised when the service has no record for the vendor."""


def get_vendor_risk(vendor_name: str, timeout_seconds: float = 3.0) -> dict:
    """Call the vendor-risk service.

    Starter version raised raw `requests` exceptions and let a 503 propagate as an HTTPError;
    here each failure mode becomes a typed exception so the tool layer can degrade on purpose.
    """
    base_url = os.getenv("VENDOR_RISK_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    url = f"{base_url}/vendor-risk/{quote(vendor_name, safe='')}"
    try:
        response = requests.get(url, timeout=timeout_seconds)
    except requests.RequestException as exc:
        raise VendorRiskUnavailable(f"{type(exc).__name__} calling {url}") from exc
    if response.status_code == 404:
        raise VendorRiskNotFound(f"No vendor-risk record for '{vendor_name}'")
    if response.status_code >= 500:
        detail = _detail(response)
        raise VendorRiskUnavailable(f"HTTP {response.status_code}: {detail}")
    if not response.ok:
        raise VendorRiskUnavailable(f"HTTP {response.status_code}: {_detail(response)}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise VendorRiskUnavailable("non-JSON response from vendor-risk service") from exc
    if not isinstance(payload, dict):
        raise VendorRiskUnavailable("unexpected payload shape from vendor-risk service")
    try:
        record = VendorAssessment.model_validate(payload)
        if record.vendor_name.casefold() != vendor_name.casefold():
            raise ValueError("vendor identity mismatch")
        if record.last_review_date is not None:
            date.fromisoformat(record.last_review_date)
    except (ValidationError, ValueError) as exc:
        raise VendorRiskUnavailable("invalid vendor-risk response schema, date, or vendor identity") from exc
    return record.model_dump()


def _detail(response: requests.Response) -> str:
    try:
        body = response.json()
        return str(body.get("detail", body) if isinstance(body, dict) else body)[:200]
    except ValueError:
        return response.text[:200]
