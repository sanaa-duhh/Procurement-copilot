from __future__ import annotations

import re
from typing import Any

from src.data_access import load_software_catalog

_STOP = {"pro", "plus", "enterprise", "team", "teams", "business", "advanced", "add", "on", "addon", "add-on",
         "expansion", "workspace", "assistant", "pack", "edition", "suite", "the", "for", "and", "of"}


def _tokens(text: Any) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", str(text or "").lower()) if t and t not in _STOP}


def search_software_catalog(product_name: str = "", vendor_name: str = "", category: str = "") -> dict[str, Any]:
    """Deterministic lookup. Ranks matches: same product > same vendor + category > same category > same vendor."""
    catalog = load_software_catalog()
    want_vendor = str(vendor_name or "").strip().lower()
    vendor_tokens = _tokens(vendor_name)
    want_product = _tokens(product_name) - vendor_tokens
    want_category = str(category or "").strip().lower()
    matches: list[dict[str, Any]] = []
    for _, row in catalog.iterrows():
        row_vendor = str(row["vendor_name"]).strip().lower()
        row_category = str(row["category"]).strip().lower()
        row_product = _tokens(row["product_name"]) - _tokens(row["vendor_name"])
        same_vendor = bool(want_vendor) and row_vendor == want_vendor
        same_category = bool(want_category) and row_category == want_category
        same_product = bool(want_product) and bool(want_product & row_product) and (same_vendor or want_product >= row_product)
        if same_product:
            kind, rank = "same_product", 0
        elif same_vendor and same_category:
            kind, rank = "same_vendor_same_category", 1
        elif same_category:
            kind, rank = "same_category", 2
        elif same_vendor:
            kind, rank = "same_vendor", 3
        else:
            continue
        matches.append({
            "match_type": kind,
            "_rank": rank,
            "software_id": row["software_id"],
            "product_name": row["product_name"],
            "vendor_name": row["vendor_name"],
            "category": row["category"],
            "status": row["status"],
            "annual_cost_usd": float(row["annual_cost_usd"]),
            "licensed_seats": int(row["licensed_seats"]),
            "scope": row["scope"],
            "notes": row["notes"],
        })
    matches.sort(key=lambda m: m["_rank"])
    for m in matches:
        m.pop("_rank")
    return {
        "query": {"product_name": product_name, "vendor_name": vendor_name, "category": category},
        "match_count": len(matches),
        "matches": matches,
        "reference": "software_catalog.csv",
    }
