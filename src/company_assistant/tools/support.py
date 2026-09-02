"""Narrow support-case lookup by case id - the only structured-data tool."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from company_assistant.database import DATABASE_PATH, get_support_case as _read_support_case
from company_assistant.models import EmployeeContext, EmployeeRole
from company_assistant.tools.schemas import SupportCase, SupportCaseResult

#: Roles cleared for business records (projects / support cases), from the access
#: matrix. People Operations is denied: its remit is personal-data records, and
#: no People Ops priority question needs a customer's case status.
#:
#: This gate lives here because `database.py` has no permission concept at all -
#: it is the one place in the tool set that *authors* access policy rather than
#: enforcing policy already carried on a record. Written as an allow-list so a
#: role added to the system later is denied until someone decides otherwise
#: (default deny).
CASE_READER_ROLES: frozenset[EmployeeRole] = frozenset(
    {"customer_success", "engineering", "finance"}
)

#: Case ids are opaque identifiers, not a query language. Anything that is not
#: shaped like one is refused before it reaches the database - not because the
#: query is unparameterized (it is parameterized), but because a tool that
#: accepts arbitrary text invites being used as one.
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")


def get_support_case(
    case_id: str,
    employee: EmployeeContext,
    *,
    database_path: Path = DATABASE_PATH,
) -> SupportCaseResult:
    """Look up exactly one support case by id.

    Three outcomes are kept strictly apart:

    * `denied` - this role may not read business records at all.
    * `empty`  - the lookup ran and no such case exists. This is absence, and it
      is never zero and never a permission problem.
    * `error`  - the database could not be read. Reported as unknown, because
      presenting an infrastructure failure as "no such case" would be a failure
      reported as fact (T-07, EVAL-008).
    """
    normalized = (case_id or "").strip()

    if employee.role not in CASE_READER_ROLES:
        # Refused before the read, and the message reveals nothing about whether
        # the case exists: existence itself is information this role has not been
        # cleared for.
        return SupportCaseResult(
            status="denied",
            case_id=normalized,
            reason=f"Role {employee.role} is not cleared to read business records.",
        )

    if not CASE_ID_PATTERN.match(normalized):
        return SupportCaseResult(
            status="error",
            case_id=normalized,
            reason="A case id is required, shaped like 'CASE-4471'. This tool accepts no other input.",
        )

    try:
        row = _read_support_case(normalized, database_path)
    except sqlite3.Error as exc:
        return SupportCaseResult(
            status="error",
            case_id=normalized,
            reason=f"The business database could not be read ({type(exc).__name__}). "
            "Treat this case as unknown, not as non-existent.",
        )

    if row is None:
        return SupportCaseResult(
            status="empty",
            case_id=normalized,
            reason=f"No support case with id {normalized} exists.",
        )

    return SupportCaseResult(status="ok", case_id=normalized, case=SupportCase(**row))
