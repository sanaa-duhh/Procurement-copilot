from __future__ import annotations

from typing import Any

from src.data_access import load_purchase_history


def get_purchase_history(vendor_name: str = "", department: str = "") -> dict[str, Any]:
    history = load_purchase_history()
    if vendor_name:
        history = history[history["vendor_name"].str.strip().str.lower() == vendor_name.strip().lower()]
    if department:
        history = history[history["department"].str.strip().str.lower() == department.strip().lower()]
    records = history.to_dict(orient="records")
    for r in records:
        r["annual_amount_usd"] = float(r["annual_amount_usd"])
    return {
        "query": {"vendor_name": vendor_name, "department": department},
        "match_count": len(records),
        "purchases": records,
        "reference": "purchase_history.csv",
    }
