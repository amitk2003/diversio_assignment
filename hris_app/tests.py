"""
tests.py — Focused automated tests for parser, validator, and hierarchy logic.

Run with:
    python manage.py test hris_app

Each test targets a specific, important behaviour and is independent of Django's
database or HTTP stack (except the upload integration test which uses the test
client).
"""

import io
from django.test import TestCase, Client
from django.urls import reverse

from .parser import parse_csv, ParseError
from .validator import validate_rows
from .hierarchy import build_hierarchy


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_csv(rows: list[str]) -> io.BytesIO:
    """Build a BytesIO CSV from a list of text lines (header included)."""
    header = "employee_id,employee_name,email,manager_id,manager_email,department\n"
    body = "\n".join(rows) + "\n"
    return io.BytesIO((header + body).encode("utf-8"))


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class ParserTest(TestCase):

    def test_basic_parsing_and_normalization(self):
        """Parser trims whitespace, lowercases emails, attaches _row_num."""
        csv_bytes = _make_csv([
            " EMP-1 , Alice ,  ALICE@EXAMPLE.COM ,,,HR",
        ])
        rows = parse_csv(csv_bytes)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["employee_id"], "EMP-1")          # strip only, case kept
        self.assertEqual(row["employee_name"], "Alice")
        self.assertEqual(row["email"], "alice@example.com")    # lowercased
        self.assertEqual(row["department"], "HR")
        self.assertEqual(row["_row_num"], 1)

    def test_bom_stripped(self):
        """UTF-8 BOM at the start of the file is silently removed."""
        bom = b"\xef\xbb\xbf"
        csv_content = b"employee_id,employee_name,email,manager_id,manager_email,department\nE1,Bob,bob@x.com,,,Eng\n"
        buf = io.BytesIO(bom + csv_content)
        rows = parse_csv(buf)
        self.assertEqual(rows[0]["employee_id"], "E1")

    def test_missing_required_header_raises_parse_error(self):
        """A CSV without 'email' raises ParseError with a helpful message."""
        bad_csv = io.BytesIO(b"employee_id,employee_name,manager_id,manager_email,department\nE1,Bob,,,Eng\n")
        with self.assertRaises(ParseError) as ctx:
            parse_csv(bad_csv)
        self.assertIn("email", str(ctx.exception))

    def test_quoted_value_with_comma(self):
        """Names containing commas (quoted in CSV) are parsed correctly."""
        csv_bytes = _make_csv([
            '"EMP-99","Smith, Jane",jane@example.com,,,Legal',
        ])
        rows = parse_csv(csv_bytes)
        self.assertEqual(rows[0]["employee_name"], "Smith, Jane")

    def test_manager_email_lowercased(self):
        """manager_email is lowercased during normalization."""
        csv_bytes = _make_csv([
            "EMP-1,Alice,alice@example.com,,BOSS@EXAMPLE.COM,HR",
        ])
        rows = parse_csv(csv_bytes)
        self.assertEqual(rows[0]["manager_email"], "boss@example.com")


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------

class ValidatorTest(TestCase):

    def test_duplicate_employee_id_rejected(self):
        """Both rows sharing a duplicate employee_id are rejected."""
        rows = [
            {"employee_id": "EMP-1", "email": "a@x.com", "_row_num": 1},
            {"employee_id": "EMP-1", "email": "b@x.com", "_row_num": 2},
            {"employee_id": "EMP-3", "email": "c@x.com", "_row_num": 3},
        ]
        accepted, errors = validate_rows(rows)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["employee_id"], "EMP-3")
        error_fields = {e.field for e in errors}
        self.assertIn("employee_id", error_fields)

    def test_duplicate_email_rejected(self):
        """Both rows sharing a duplicate email are rejected."""
        rows = [
            {"employee_id": "EMP-1", "email": "shared@x.com", "_row_num": 1},
            {"employee_id": "EMP-2", "email": "shared@x.com", "_row_num": 2},
        ]
        accepted, errors = validate_rows(rows)
        self.assertEqual(len(accepted), 0)
        self.assertTrue(any(e.field == "email" for e in errors))

    def test_missing_employee_id_rejected(self):
        """Rows without employee_id are rejected with a clear error."""
        rows = [
            {"employee_id": "", "email": "a@x.com", "_row_num": 1},
        ]
        accepted, errors = validate_rows(rows)
        self.assertEqual(len(accepted), 0)
        self.assertTrue(any(e.field == "employee_id" for e in errors))

    def test_missing_email_rejected(self):
        """Rows without email are rejected."""
        rows = [
            {"employee_id": "EMP-1", "email": "", "_row_num": 1},
        ]
        accepted, errors = validate_rows(rows)
        self.assertEqual(len(accepted), 0)

    def test_valid_rows_all_accepted(self):
        """Clean rows with unique IDs and emails are all accepted."""
        rows = [
            {"employee_id": "EMP-1", "email": "a@x.com", "_row_num": 1},
            {"employee_id": "EMP-2", "email": "b@x.com", "_row_num": 2},
        ]
        accepted, errors = validate_rows(rows)
        self.assertEqual(len(accepted), 2)
        self.assertEqual(len(errors), 0)


# ---------------------------------------------------------------------------
# Hierarchy tests
# ---------------------------------------------------------------------------

class HierarchyTest(TestCase):

    def _row(self, eid, email, mid="", memail="", name="", dept="", rn=1):
        return {
            "employee_id": eid, "email": email,
            "manager_id": mid, "manager_email": memail,
            "employee_name": name, "department": dept,
            "_row_num": rn,
        }

    def test_root_detection(self):
        """An employee with no manager fields is detected as a root."""
        rows = [self._row("EMP-1", "a@x.com", rn=1)]
        result = build_hierarchy(rows)
        root_ids = {e.employee_id for e in result.roots}
        self.assertIn("EMP-1", root_ids)

    def test_manager_not_found_error(self):
        """A manager_id that does not exist in accepted rows produces an error."""
        rows = [self._row("EMP-1", "a@x.com", mid="NONEXISTENT", rn=1)]
        result = build_hierarchy(rows)
        self.assertEqual(len(result.manager_errors), 1)
        self.assertIn("NONEXISTENT", result.manager_errors[0][1])

    def test_self_management_error(self):
        """An employee referencing themselves as manager produces an error."""
        rows = [self._row("EMP-1", "a@x.com", mid="EMP-1", rn=1)]
        result = build_hierarchy(rows)
        self.assertEqual(len(result.manager_errors), 1)
        self.assertIn("cannot manage themselves", result.manager_errors[0][1])

    def test_cycle_detection_simple(self):
        """A simple two-node cycle (A→B, B→A) is detected and both are marked."""
        rows = [
            self._row("EMP-A", "a@x.com", mid="EMP-B", rn=1),
            self._row("EMP-B", "b@x.com", mid="EMP-A", rn=2),
        ]
        result = build_hierarchy(rows)
        cycle_ids = {e.employee_id for e in result.cycle_members}
        self.assertIn("EMP-A", cycle_ids)
        self.assertIn("EMP-B", cycle_ids)

    def test_cycle_detection_longer(self):
        """A three-node cycle (A→B→C→A) marks all three members."""
        rows = [
            self._row("A", "a@x.com", mid="B", rn=1),
            self._row("B", "b@x.com", mid="C", rn=2),
            self._row("C", "c@x.com", mid="A", rn=3),
        ]
        result = build_hierarchy(rows)
        cycle_ids = {e.employee_id for e in result.cycle_members}
        self.assertEqual(cycle_ids, {"A", "B", "C"})

    def test_non_cycle_reporter_not_marked(self):
        """An employee reporting INTO a cycle is not itself marked as cyclic."""
        # A→B→A is a cycle; D→A means D reports into the cycle but isn't in it.
        rows = [
            self._row("A", "a@x.com", mid="B", rn=1),
            self._row("B", "b@x.com", mid="A", rn=2),
            self._row("D", "d@x.com", mid="A", rn=3),  # reports into cycle
        ]
        result = build_hierarchy(rows)
        cycle_ids = {e.employee_id for e in result.cycle_members}
        self.assertNotIn("D", cycle_ids)
        self.assertIn("A", cycle_ids)
        self.assertIn("B", cycle_ids)

    def test_conflicting_manager_refs(self):
        """manager_id and manager_email pointing to different people is an error."""
        rows = [
            self._row("MGR-1", "mgr1@x.com", rn=1),
            self._row("MGR-2", "mgr2@x.com", rn=2),
            self._row("EMP-1", "emp@x.com", mid="MGR-1", memail="mgr2@x.com", rn=3),
        ]
        result = build_hierarchy(rows)
        self.assertEqual(len(result.manager_errors), 1)
        self.assertIn("conflict" in result.manager_errors[0][1].lower()
                      or "same" in result.manager_errors[0][1].lower(), [True])

    def test_direct_report_counts(self):
        """Manager's direct report count equals number of immediate reports."""
        rows = [
            self._row("MGR", "mgr@x.com", rn=1),
            self._row("E1", "e1@x.com", mid="MGR", rn=2),
            self._row("E2", "e2@x.com", mid="MGR", rn=3),
            self._row("E3", "e3@x.com", mid="MGR", rn=4),
        ]
        result = build_hierarchy(rows)
        self.assertEqual(result.direct_report_counts["MGR"], 3)
        self.assertEqual(result.direct_report_counts["E1"], 0)

    def test_manager_error_employee_not_a_root(self):
        """An employee with a manager error is accepted but not classified as root."""
        rows = [self._row("EMP-1", "a@x.com", mid="GHOST", rn=1)]
        result = build_hierarchy(rows)
        root_ids = {e.employee_id for e in result.roots}
        self.assertNotIn("EMP-1", root_ids)
        self.assertEqual(len(result.employees), 1)


# ---------------------------------------------------------------------------
# Integration test — upload view
# ---------------------------------------------------------------------------

class UploadViewTest(TestCase):

    def setUp(self):
        self.client = Client()

    def test_get_returns_upload_form(self):
        """GET / renders the upload form page."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HRIS Import Preview")

    def test_post_without_file_shows_error(self):
        """POST without a file returns the upload form with an error message."""
        response = self.client.post("/", {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please select a CSV file")

    def test_post_non_csv_shows_error(self):
        """POST with a non-.csv file is rejected with a clear error."""
        buf = io.BytesIO(b"not,a,csv")
        buf.name = "data.txt"
        response = self.client.post("/", {"csv_file": buf})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not appear to be a CSV file")

    def test_post_valid_sample_csv_returns_result(self):
        """POST with the sample HRIS CSV renders the result page."""
        import os
        sample_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "sample_hris.csv"
        )
        with open(sample_path, "rb") as f:
            response = self.client.post("/", {"csv_file": f})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Import Preview")
        self.assertContains(response, "Source rows")

    def test_post_bad_csv_header_shows_error(self):
        """POST with CSV missing required headers shows a parse error."""
        bad = io.BytesIO(b"name,age\nAlice,30\n")
        bad.name = "bad.csv"
        response = self.client.post("/", {"csv_file": bad})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "missing required column")
