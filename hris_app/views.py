"""
views.py — Django view handling file upload and result rendering.

GET  /  → render upload form
POST /  → parse CSV, validate, build hierarchy, render result page
"""

from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .parser import parse_csv, ParseError
from .validator import validate_rows
from .hierarchy import build_hierarchy


@require_http_methods(["GET", "POST"])
def upload_view(request):
    """Single view: upload form on GET, result preview on POST."""
    if request.method == "GET":
        return render(request, "hris_app/upload.html")

    # --- POST: process the uploaded file ---
    uploaded_file = request.FILES.get("csv_file")
    if not uploaded_file:
        return render(
            request,
            "hris_app/upload.html",
            {"error": "Please select a CSV file before uploading."},
        )

    # Guard against non-CSV uploads.
    filename = uploaded_file.name or ""
    if not filename.lower().endswith(".csv"):
        return render(
            request,
            "hris_app/upload.html",
            {"error": f"'{filename}' does not appear to be a CSV file. Please upload a .csv file."},
        )

    # --- Parse ---
    try:
        rows = parse_csv(uploaded_file)
    except ParseError as exc:
        return render(
            request,
            "hris_app/upload.html",
            {"error": f"Could not parse the file: {exc}"},
        )
    except Exception as exc:
        return render(
            request,
            "hris_app/upload.html",
            {"error": f"Unexpected error while reading the file: {exc}"},
        )

    total_rows = len(rows)

    # --- Validate identity ---
    accepted, validation_errors = validate_rows(rows)

    # --- Build hierarchy ---
    result = build_hierarchy(accepted)

    # --- Build manager table (only managers with ≥1 direct report) ---
    managers_with_reports = [
        {
            "employee": emp,
            "direct_reports": result.direct_report_counts[emp.employee_id],
        }
        for emp in result.employees
        if result.direct_report_counts[emp.employee_id] > 0
    ]
    managers_with_reports.sort(
        key=lambda m: -m["direct_reports"]  # descending by report count
    )

    context = {
        "filename": filename,
        "total_rows": total_rows,
        "accepted_count": len(accepted),
        "rejected_count": total_rows - len(accepted),
        "validation_errors": validation_errors,
        "manager_errors": result.manager_errors,
        "roots": result.roots,
        "managers_with_reports": managers_with_reports,
        "cycle_members": result.cycle_members,
        "has_cycles": bool(result.cycle_members),
    }

    return render(request, "hris_app/result.html", context)
