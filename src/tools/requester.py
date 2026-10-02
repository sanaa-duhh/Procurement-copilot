from __future__ import annotations

import math
from typing import Any

from src.data_access import load_employees


def _clean(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def get_requester_profile(employee_id: str) -> dict[str, Any]:
    employees = load_employees()
    row = employees[employees["employee_id"] == employee_id]
    if row.empty:
        return {"found": False, "employee_id": employee_id, "error": "no employee with this ID"}
    record = {k: _clean(v) for k, v in row.iloc[0].to_dict().items()}
    manager = None
    if record.get("manager_id"):
        mrow = employees[employees["employee_id"] == record["manager_id"]]
        if not mrow.empty:
            manager = {k: _clean(v) for k, v in mrow.iloc[0].to_dict().items() if k in {"employee_id", "name", "level", "department"}}
    return {"found": True, **record, "manager": manager, "reference": employee_id}
