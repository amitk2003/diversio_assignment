"""
parser.py — CSV parsing and field normalization.

Responsibilities:
- Read a UTF-8 file object (with or without BOM).
- Use stdlib csv.DictReader so quoted commas in values work correctly.
- Trim surrounding whitespace from every field value.
- Lowercase `email` and `manager_email`.
- Keep `employee_id` case-sensitive.
- Attach a 1-based `_row_num` (header = row 0, first data row = 1).

This module has NO Django imports so it can be tested in isolation.
"""

import csv
import io
from typing import IO


# Required columns the CSV must contain.
REQUIRED_HEADERS = {"employee_id", "employee_name", "email", "manager_id", "manager_email", "department"}


class ParseError(Exception):
    """Raised when the uploaded file cannot be parsed at all."""


def parse_csv(file_obj: IO[bytes]) -> list[dict]:
    """
    Parse a CSV file-like object and return a list of normalized row dicts.

    Each dict has the original column keys plus ``_row_num`` (int, 1-based,
    counting data rows only — the header row is not counted).

    Args:
        file_obj: A binary file-like object (Django's InMemoryUploadedFile or
                  similar).  May start with a UTF-8 BOM.

    Returns:
        List of row dicts, one per data row.

    Raises:
        ParseError: If the file cannot be decoded or is missing required headers.
    """
    try:
        raw_bytes = file_obj.read()
    except Exception as exc:
        raise ParseError(f"Could not read uploaded file: {exc}") from exc

    # Decode UTF-8, stripping the byte-order mark if present.
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ParseError(f"File is not valid UTF-8: {exc}") from exc

    reader = csv.DictReader(io.StringIO(text))

    # Validate that all required headers are present.
    if reader.fieldnames is None:
        raise ParseError("The file appears to be empty.")

    actual_headers = {h.strip() for h in reader.fieldnames}
    missing = REQUIRED_HEADERS - actual_headers
    if missing:
        raise ParseError(
            f"CSV is missing required column(s): {', '.join(sorted(missing))}"
        )

    rows: list[dict] = []
    for row_num, raw_row in enumerate(reader, start=1):
        normalized: dict = {}
        for key, value in raw_row.items():
            if key is None:
                continue  # extra columns beyond the header are ignored
            clean_key = key.strip()
            clean_val = (value or "").strip()

            # Lowercase email fields; keep everything else as-is.
            if clean_key in ("email", "manager_email"):
                clean_val = clean_val.lower()

            normalized[clean_key] = clean_val

        normalized["_row_num"] = row_num
        rows.append(normalized)

    return rows
