"""Resolve typed names to directory evidence, never to a guessed budget owner."""


def _normalise(value: str) -> str:
    return " ".join(value.split()).casefold()


def resolve_requester(name: str, employee_id: str, employees: dict) -> tuple[str, str]:
    name = _normalise(name)
    identifier = employee_id.strip().upper()
    if not name:
        return "", "Enter the requester's name."
    if identifier:
        record = employees.get(identifier)
        if record and _normalise(record["name"]) == name:
            return identifier, f"Directory match: {record['name']} · {record['department']} · {identifier}"
        return "", "The name and employee ID do not match a directory record. Identity and budget ownership need verification."
    matches = [(key, value) for key, value in employees.items() if _normalise(value["name"]) == name]
    if len(matches) == 1:
        key, record = matches[0]
        return key, f"Directory match: {record['name']} · {record['department']} · {key}"
    if len(matches) > 1:
        return "", "Several employees share this name. Add an employee ID to identify the requester."
    return "", "New requester: the name is accepted. Procurement must verify the employee record and budget owner before approval."
