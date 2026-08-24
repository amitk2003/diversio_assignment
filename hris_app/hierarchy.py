"""
hierarchy.py — Manager resolution and reporting-cycle detection.

Given a list of *accepted* employee rows (identity already validated), this
module:

1. Builds a lookup dict by employee_id and by email.
2. For each employee resolves their manager according to the spec rules:
   - Both fields blank → root employee.
   - Only manager_id → look up by ID.
   - Only manager_email → look up by email.
   - Both supplied → both must resolve to the SAME employee.
   - Self-management, not-found, and conflict are reported as manager errors.
   An employee with a manager error is accepted but produces no edge and is
   NOT classified as a root.
3. Detects reporting cycles using DFS with three-colour marking
   (WHITE → GRAY → BLACK).  Only employees inside a cycle are reported as
   cyclic; employees who merely *report into* a cycle are not.
4. Counts direct reports per manager.
5. Identifies employees that participate in any reporting cycle.

All operations are O(V + E) where V = employees, E = reporting edges.

This module has NO Django imports so it can be tested in isolation.
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Employee:
    employee_id: str
    employee_name: str
    email: str
    department: str
    row_num: int
    # Resolved after build_hierarchy():
    manager: Optional["Employee"] = field(default=None, repr=False)
    manager_error: Optional[str] = None   # human-readable error message


@dataclass
class HierarchyResult:
    employees: list[Employee]                 # all accepted employees
    manager_errors: list[tuple[int, str]]     # (row_num, message)
    roots: list[Employee]                     # employees with no manager
    direct_report_counts: dict[str, int]      # employee_id → count
    cycle_members: list[Employee]             # employees that ARE in a cycle
    reporting_cycle_employees: list[Employee] # same set, sorted for display


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_hierarchy(accepted_rows: list[dict]) -> HierarchyResult:
    """
    Resolve the manager graph and detect cycles from accepted employee rows.

    Args:
        accepted_rows: Output of validator.validate_rows()[0].

    Returns:
        A HierarchyResult populated with roots, manager errors, direct-report
        counts, and cycle members.
    """
    # --- Step 1: build Employee objects and lookup dicts ---
    employees: list[Employee] = []
    by_id: dict[str, Employee] = {}
    by_email: dict[str, Employee] = {}

    for row in accepted_rows:
        emp = Employee(
            employee_id=row["employee_id"],
            employee_name=row.get("employee_name", ""),
            email=row["email"],
            department=row.get("department", ""),
            row_num=row["_row_num"],
        )
        employees.append(emp)
        by_id[emp.employee_id] = emp
        by_email[emp.email] = emp

    # --- Step 2: resolve managers, record edges and errors ---
    manager_errors: list[tuple[int, str]] = []

    # adjacency: parent_id -> list of child Employee objects (for DFS later)
    children: dict[str, list[Employee]] = {e.employee_id: [] for e in employees}

    for row, emp in zip(accepted_rows, employees):
        mid = row.get("manager_id", "")
        memail = row.get("manager_email", "")

        if not mid and not memail:
            # Root employee — no manager.
            continue

        resolved_by_id: Optional[Employee] = None
        resolved_by_email: Optional[Employee] = None
        error_msg: Optional[str] = None

        if mid:
            resolved_by_id = by_id.get(mid)
            if resolved_by_id is None:
                error_msg = f"manager_id '{mid}' not found in accepted employees."

        if memail:
            resolved_by_email = by_email.get(memail)
            if resolved_by_email is None:
                error_msg = (
                    (error_msg + " " if error_msg else "")
                    + f"manager_email '{memail}' not found in accepted employees."
                )

        # Check for conflict when both are supplied and both resolved.
        if resolved_by_id and resolved_by_email:
            if resolved_by_id.employee_id != resolved_by_email.employee_id:
                error_msg = (
                    f"manager_id '{mid}' resolves to "
                    f"'{resolved_by_id.employee_id}' but manager_email "
                    f"'{memail}' resolves to '{resolved_by_email.employee_id}'. "
                    "They must identify the same employee."
                )
                resolved_by_id = None  # cancel both on conflict

        # Pick whichever resolved (id takes precedence if both supplied without conflict).
        resolved: Optional[Employee] = resolved_by_id or resolved_by_email

        if resolved is None and error_msg is None:
            # Both were blank — shouldn't happen here but guard anyway.
            continue

        if resolved is not None and resolved.employee_id == emp.employee_id:
            error_msg = f"Employee '{emp.employee_id}' cannot manage themselves."
            resolved = None

        if error_msg:
            emp.manager_error = error_msg
            manager_errors.append((emp.row_num, error_msg))
        elif resolved:
            emp.manager = resolved
            children[resolved.employee_id].append(emp)

    # --- Step 3: compute roots and direct-report counts ---
    roots: list[Employee] = [
        e for e in employees if e.manager is None and e.manager_error is None
    ]
    direct_report_counts: dict[str, int] = {
        e.employee_id: len(children[e.employee_id]) for e in employees
    }

    # --- Step 4: detect cycle members using DFS 3-colour marking ---
    # WHITE = 0 (unvisited), GRAY = 1 (in current DFS stack), BLACK = 2 (done)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {e.employee_id: WHITE for e in employees}
    # in_cycle: tracks employees confirmed to be IN a cycle.
    in_cycle: set[str] = set()

    def dfs(emp: Employee) -> None:
        color[emp.employee_id] = GRAY
        for child in children[emp.employee_id]:
            cid = child.employee_id
            if color[cid] == GRAY:
                # Found a back-edge → both endpoints are in a cycle.
                # Walk up the stack to mark all nodes in this SCC.
                in_cycle.add(cid)
                in_cycle.add(emp.employee_id)
                # Mark all GRAY nodes that are part of this cycle path.
                # We re-traverse the GRAY stack to capture the full cycle.
                _mark_cycle_path(emp, child, color, children, in_cycle)
            elif color[cid] == WHITE:
                dfs(child)
        color[emp.employee_id] = BLACK

    # We need an iterative DFS to avoid stack overflow on large inputs.
    # Replace the recursive version above with an explicit stack.
    color = {e.employee_id: WHITE for e in employees}
    in_cycle = set()

    for start in employees:
        if color[start.employee_id] != WHITE:
            continue

        # Iterative DFS using explicit stack of (employee, child_iterator).
        stack: list[tuple[Employee, iter]] = []
        color[start.employee_id] = GRAY
        stack.append((start, iter(children[start.employee_id])))

        while stack:
            cur, child_iter = stack[-1]
            try:
                child = next(child_iter)
                cid = child.employee_id
                if color[cid] == GRAY:
                    # Back-edge → cycle detected.
                    # Collect all GRAY nodes currently on the path.
                    on_stack_ids = {e.employee_id for e, _ in stack}
                    # The cycle consists of nodes from `child` up to `cur`.
                    in_cycle_path: set[str] = set()
                    found = False
                    for e, _ in stack:
                        if e.employee_id == cid:
                            found = True
                        if found:
                            in_cycle_path.add(e.employee_id)
                    in_cycle_path.add(cid)
                    in_cycle.update(in_cycle_path)
                elif color[cid] == WHITE:
                    color[cid] = GRAY
                    stack.append((child, iter(children[cid])))
            except StopIteration:
                color[cur.employee_id] = BLACK
                stack.pop()

    by_emp_id: dict[str, Employee] = {e.employee_id: e for e in employees}
    cycle_members: list[Employee] = sorted(
        [by_emp_id[eid] for eid in in_cycle],
        key=lambda e: e.row_num,
    )

    return HierarchyResult(
        employees=employees,
        manager_errors=manager_errors,
        roots=sorted(roots, key=lambda e: e.employee_id),
        direct_report_counts=direct_report_counts,
        cycle_members=cycle_members,
        reporting_cycle_employees=cycle_members,
    )


def _mark_cycle_path(
    cur: Employee,
    cycle_start: Employee,
    color: dict[str, int],
    children: dict[str, list[Employee]],
    in_cycle: set[str],
) -> None:
    """Helper — not used in the iterative version, kept for clarity."""
    pass
