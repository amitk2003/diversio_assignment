"""
validator.py — Employee identity validation.

Rules (from the spec):
- `employee_id` and `email` are required (non-empty after normalization).
- Each must be unique across all rows.
- Every row that shares a duplicated employee_id OR email is invalid.
- Invalid rows do not participate in manager lookup or hierarchy analysis.

Returns:
    accepted  — list of row dicts that passed identity validation
    errors    — list of ValidationError dicts with _row_num, field, message

This module has NO Django imports so it can be tested in isolation.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import NamedTuple


class ValidationError(NamedTuple):
    row_num: int
    field: str
    message: str


def validate_rows(rows: list[dict]) -> tuple[list[dict], list[ValidationError]]:
    """
    Check identity rules and return (accepted_rows, validation_errors).

    A row is *accepted* only when:
      - employee_id is non-empty, AND
      - email is non-empty, AND
      - neither employee_id nor email appears in any other row.

    All other rows are *rejected* and produce one or more ValidationError entries.

    Time complexity: O(n) — two passes over the row list.
    Space complexity: O(n) — index dicts proportional to number of rows.
    """
    errors: list[ValidationError] = []

    # --- Pass 1: index every employee_id and email to find duplicates ---
    id_index: dict[str, list[int]] = defaultdict(list)   # value -> [row_nums]
    email_index: dict[str, list[int]] = defaultdict(list)

    for row in rows:
        rn = row["_row_num"]
        eid = row.get("employee_id", "")
        em = row.get("email", "")

        if eid:
            id_index[eid].append(rn)
        if em:
            email_index[em].append(rn)

    # Build sets of row numbers that are invalid due to duplication.
    invalid_row_nums: set[int] = set()

    for eid, rns in id_index.items():
        if len(rns) > 1:
            for rn in rns:
                invalid_row_nums.add(rn)
                errors.append(
                    ValidationError(
                        row_num=rn,
                        field="employee_id",
                        message=f"Duplicate employee_id '{eid}' (also on row(s) "
                                f"{', '.join(str(r) for r in rns if r != rn)}).",
                    )
                )

    for em, rns in email_index.items():
        if len(rns) > 1:
            for rn in rns:
                invalid_row_nums.add(rn)
                errors.append(
                    ValidationError(
                        row_num=rn,
                        field="email",
                        message=f"Duplicate email '{em}' (also on row(s) "
                                f"{', '.join(str(r) for r in rns if r != rn)}).",
                    )
                )

    # --- Pass 2: check required fields and collect accepted rows ---
    accepted: list[dict] = []

    for row in rows:
        rn = row["_row_num"]
        eid = row.get("employee_id", "")
        em = row.get("email", "")

        if not eid:
            invalid_row_nums.add(rn)
            errors.append(
                ValidationError(row_num=rn, field="employee_id", message="employee_id is required.")
            )
        if not em:
            invalid_row_nums.add(rn)
            errors.append(
                ValidationError(row_num=rn, field="email", message="email is required.")
            )

        if rn not in invalid_row_nums:
            accepted.append(row)

    # Sort errors by row number for readable output.
    errors.sort(key=lambda e: (e.row_num, e.field))
    return accepted, errors
