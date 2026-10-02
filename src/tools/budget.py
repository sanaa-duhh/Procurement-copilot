from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.data_access import load_budgets
from src.rules import to_decimal


def check_budget(department: str, annual_cost_usd: float | int | str | None) -> dict[str, Any]:
    """Deterministic. Compares cost with the department's available software budget."""
    budgets = load_budgets()
    row = budgets[budgets["department"].str.strip().str.lower() == str(department).strip().lower()]
    cost = to_decimal(annual_cost_usd)
    if row.empty:
        return {
            "found": False,
            "department": department,
            "annual_cost_usd": float(cost) if cost is not None else None,
            "error": f"no software budget line for department '{department}'",
        }
    rec = row.iloc[0]
    annual = Decimal(str(rec["annual_software_budget_usd"]))
    committed = Decimal(str(rec["committed_usd"]))
    available = Decimal(str(rec["available_usd"]))
    arithmetic_ok = annual - committed == available
    result: dict[str, Any] = {
        "found": True,
        "department": rec["department"],
        "annual_software_budget_usd": float(annual),
        "committed_usd": float(committed),
        "available_usd": float(available),
        "snapshot_arithmetic_consistent": arithmetic_ok,
        "annual_cost_usd": float(cost) if cost is not None else None,
        "reference": f"department_budgets.csv:{rec['department']}",
    }
    if cost is None:
        result.update({"within_budget": None, "shortfall_usd": None, "note": "no annual cost supplied"})
    else:
        shortfall = max(Decimal(0), cost - available)
        result.update({"within_budget": cost <= available, "shortfall_usd": float(shortfall)})
    return result
