# HRIS Import Preview — Candidate Submission

> **Candidate note:** This file is my personal submission README. The original
> problem statement lives in `README.md`.

---

## Time Spent

| Phase | Time |
|---|---|
| Design thinking and dataset analysis (pen and paper) | ~20 min |
| Environment setup + scaffolding | ~10 min |
| Core implementation (parser → validator → hierarchy) | ~30 min |
| Template + view wiring | ~10 min |
| Tests | ~5 min |
| **Total** | **~75 min** |

I finished just inside the 90-minute timebox.

---

## Project Overview

### What This Application Does

This is a single-page Django web application that allows a Client Success team member
to upload an HRIS (Human Resource Information System) CSV export and immediately see
a structured import preview — without committing any data to a database. The preview
surfaces everything a reviewer needs to catch problems before data is written to the
Diversio platform:

- How many rows the file contains in total.
- Which employee records are clean and accepted for analysis.
- Which rows failed identity validation and exactly why (missing fields, duplicate IDs,
  duplicate emails), with the source row number for each error.
- Which manager references are broken — an ID that points to no one, two references
  that disagree, or an employee claiming to manage themselves — again with row numbers.
- Which employees have no manager at all (the roots of the org tree).
- Every manager in the dataset and how many people report directly to them.
- Any employees who are trapped inside a reporting cycle (A reports to B, B reports
  to A), which would make it impossible to walk the org chart without looping forever.

The application analyses the file entirely in memory. No employee records, no
relationships, and no file contents are persisted to a database. The result is
displayed once and discarded when the user navigates away.

---

### The Problem in Plain English

An HRIS export is a flat CSV — every row describes one employee. But the people
described are not independent; they are connected by reporting relationships. Each
employee optionally declares who their manager is, using either the manager's ID, the
manager's email address, or both.

Before Diversio can load this data and build an org chart, someone needs to answer
several questions:

1. Is the file even well-formed? Are there missing required fields? Duplicate IDs?
2. Does every manager reference actually resolve to a real employee in the file?
3. Are there employees who reference each other in a circle? A cycle would make the
   org chart impossible to display or traverse correctly.
4. Who sits at the top of the tree (the root) — i.e. who has no manager?

Answering these questions manually in a spreadsheet for a file with hundreds or
thousands of rows is tedious, error-prone, and slow. This tool automates all of it
in a single upload.

---

### Key Engineering Challenges

#### Challenge 1 — Two ways to reference a manager, both optional

The CSV has two manager columns: `manager_id` and `manager_email`. Either, both, or
neither can be filled in for any given row. When both are filled they must agree.
When only one is filled, that one is used. When neither is filled, the employee is a
root. This branching logic needed to be explicit and testable, not buried in a single
messy conditional.

#### Challenge 2 — Data quality issues in the raw file

The sample data itself contains real-world messiness that the application must survive:

- `manager_email` values are sometimes in ALLCAPS (e.g. `DEMO.SOFIA.CHEN@diversio.com`).
  These must resolve to the same person as the lowercase version.
- Row 24 has leading and trailing whitespace in `employee_id` and `email`, which would
  cause a lookup miss if not stripped.
- Some rows have a `manager_id` that does not match any `employee_id` in the file
  (e.g. `DIV-9999`). These are dangling references and must be reported, not silently
  ignored.
- A name containing a comma (`"Alvarez, Renée"`) must be handled correctly by a proper
  CSV parser, not a naive `str.split(",")`.

#### Challenge 3 — Detecting cycles without false positives

The spec says: "Do not classify an employee as cyclic merely because they report into
a cycle." This rules out naive approaches like "flag everyone reachable from a cycle
node." The algorithm must identify only the nodes that are themselves members of a
cycle — nodes that appear on a back-edge path in the directed graph.

#### Challenge 4 — Scalability to 100 000 employees

The spec explicitly asks about files approaching 100 000 rows. A naive O(n²) approach
(checking every pair of employees for conflicts) would be too slow. Every stage of the
pipeline — parsing, validation, manager resolution, cycle detection — runs in O(n)
time and O(n) space.

---

### Technology Choices

| Choice | Reason |
|---|---|
| **Django** | Matches Diversio's stated stack. Provides a test runner (`manage.py test`), request handling, and template rendering with no extra dependencies. |
| **`csv.DictReader`** | Handles quoted commas in names correctly; stdlib only, no extra install. |
| **`utf-8-sig` decoding** | Transparently strips the UTF-8 BOM that some Windows tools insert at the start of CSV files. |
| **Pure Python DFS (no `networkx`)** | Keeps the dependency list minimal (`django` only). The algorithm is straightforward to read and explain. |
| **Iterative DFS with explicit stack** | Python's default recursion limit (~1 000 frames) would cause a `RecursionError` on a deep org tree. An explicit stack has no such limit. |
| **No database** | The spec says persistence is not required. Skipping it keeps the application simple, fast, and free of migrations. |
| **No JavaScript framework** | The spec explicitly says plain HTML is fine and a JS framework is not needed. |

---

### Engineering Philosophy Behind This Submission

The application is intentionally small. Every piece of functionality maps directly to
a requirement in the spec. There is no speculative feature work, no elaborate styling,
no authentication scaffolding. The focus is on correctness, clarity, and testability.

Each of the three core modules (`parser.py`, `validator.py`, `hierarchy.py`) has zero
Django imports. They are plain Python functions that take lists and return lists or
dataclasses. This makes them trivially testable in isolation — no HTTP request, no
database, no Django setup required — and means the logic could be reused in a CLI
tool, a Celery task, or a different web framework without modification.

The test suite covers the behaviours I consider most important and most likely to break
under future changes: edge cases in manager resolution (not found, self-reference,
conflict), cycle detection (2-node, 3-node, reporter-into-cycle), and validation
(duplicates, missing fields). Each test is short, focused, and named after the
specific behaviour it verifies.

---

## How I Approached This (Design Thinking First)

Before writing a single line of code I opened the CSV in Excel and studied every
row with fresh eyes. I wrote my observations in a notebook. Here is what I found
and how each finding drove a concrete design decision.

### Dataset Observations

#### Observation A — manager_id is often blank

About half the rows leave `manager_id` empty while filling `manager_email`
instead. The reverse is also true. And some rows fill both. This told me the
two fields are alternative ways to express the same relationship, not
independent fields.

**Decision:** Resolve manager through two independent lookup channels
(`manager_id` lookup by employee ID, `manager_email` lookup by normalised
email) and cross-check for conflicts when both are supplied.

#### Observation B — manager_email has mixed case

Several `manager_email` values are in ALLCAPS
(DEMO.SOFIA.CHEN@diversio.com, DEMO.AVERY.MORGAN@diversio.com).
Email addresses are case-insensitive by convention, so an uppercase value and its
lowercase twin refer to the same person.

**Decision:** Normalise `email` and `manager_email` to lowercase at parse time
(in `parser.py`), before any lookup happens, so DEMO.SOFIA.CHEN@diversio.com
correctly resolves to Sofia Chen.

#### Observation C — manager_name can be derived from manager_email

The email format is `demo.<first>.<last>@diversio.com`. The "root name" portion
(everything between `demo.` and `@diversio.com`) is exactly the manager's name
with dots as separators.

| manager_email | Derived manager_name |
|---|---|
| demo.avery.morgan@diversio.com | avery_morgan |
| demo.sofia.chen@diversio.com | sofia_chen |
| demo.camille.laurent@diversio.com | camille_laurent |

**Decision:** Derive a `manager_name` slug by extracting the middle segment of
the email address and replacing dots with underscores. This gives a reliable,
normalised name even when `manager_id` is blank.

#### Observation D — manager_id maps directly to employee_id

Studying the data, `DIV-1001` (Avery Morgan) appears as both an `employee_id`
in one row and as a `manager_id` in several others. The pattern held for every
valid manager: the `manager_id` value always matches an `employee_id` in the
dataset.

**Decision:** Build a lookup dict keyed by `employee_id` and resolve
`manager_id` against it. If the value does not match any known `employee_id`,
the manager reference is broken and should be reported as an error.

#### Observation E — Employees sharing a manager_id form a branch

All rows with `manager_id = DIV-1001` (Avery Morgan) are in the Executive
branch. All rows with `manager_id = DIV-1100` (Priya Shah) are in Engineering.
The department of the manager propagates as the branch identity. This confirmed
that the data models a real org-chart tree, not a flat list.

#### Observation F — Roots: no manager_id AND no manager_email

Only one row, Avery Morgan (DIV-1001), has both manager fields blank. He is
the root of the whole tree.

**Decision:** Treat employees with both manager fields blank as root nodes. They
produce no edge in the graph and are listed separately in the UI.

#### Observation G — Invalid manager_id that matches no employee_id

Casey Bell (DIV-1600) has `manager_id = DIV-9999` which does not exist in the
dataset. This is a dangling reference — the person is neither a root nor has a
valid manager.

**Decision:** Report such employees as manager errors. They are still accepted
employees (their identity is valid) but produce no reporting edge and are not
classified as roots.

#### Observation H — Whitespace and encoding quirks

Row 24 (DIV-1113, Hana Patel) has leading and trailing spaces in the
`employee_id` and `email` cells. If I simply compared strings directly, she
would never match as a valid employee. The spec also mentioned possible UTF-8
BOM.

**Decision:** Strip surrounding whitespace from every field at parse time and
use `utf-8-sig` decoding to handle the BOM silently.

---

## Algorithm Choice: Iterative Three-Colour DFS

After mapping the org-chart on paper I realised the reporting structure is a
directed graph (not guaranteed to be a tree), so reporting cycles are possible.

I needed an algorithm that:

1. Detects cycles.
2. Reports only nodes that are members of a cycle, not nodes that merely report
   into one.

Three-colour DFS (WHITE → GRAY → BLACK) is the right tool:

- **WHITE** = not yet visited.
- **GRAY** = currently on the DFS stack (processing its subtree).
- **BLACK** = fully processed; no unresolved cycle leads through this node.

A back-edge (an edge to a GRAY node) means a cycle was found. The cycle members
are exactly the nodes on the DFS stack between the GRAY target and the current
node.

I consulted Claude to choose between Tarjan's SCC algorithm and the three-colour
DFS approach. Claude confirmed that for the requirement "report only cycle
members, not their reporters", a simple three-colour DFS with an explicit stack
(to avoid Python recursion limits on large files) was the clearest and most
appropriate choice. I verified the algorithm against my hand-drawn test cases
before coding.

**Complexity (important for 100 000-employee files):**

| Stage | Complexity |
|---|---|
| Parse | O(n) |
| Validate | O(n) |
| Build lookup dicts | O(n) |
| Resolve managers | O(n) |
| DFS cycle detection | O(V + E) = O(n) since E <= V |
| **Total** | **O(n)** |

Space is also O(n) — the lookup dicts and colour map each hold at most n entries.

---

## How I Verified My Design Before Coding

I manually traced the sample CSV in Excel, building the expected output row by row:

- Mapped each `manager_id` to an employee name and confirmed it existed.
- Colour-coded cells to show which employees were valid or invalid.
- Identified Avery Morgan as the only root.
- Spotted the Casey Bell dangling reference (DIV-9999).
- Confirmed no cycles exist in the sample data.

My manual trace produced output that matched `expected_output_hiris.csv` exactly.
Only then did I start coding — the algorithm was already proven on paper.

---

## Architecture

```
diversio_assignment/
├── hris_app/
│   ├── parser.py       # CSV reading, BOM stripping, whitespace trim, email lowercase
│   ├── validator.py    # Identity rules: required fields, uniqueness
│   ├── hierarchy.py    # Graph build, manager resolution, DFS cycle detection
│   ├── views.py        # Django view: upload form (GET) + result page (POST)
│   ├── urls.py         # URL routing
│   ├── tests.py        # Automated tests
│   └── templates/hris_app/
│       ├── upload.html
│       └── result.html
├── sample_hris.csv
├── expected_output_hiris.csv
├── manage.py
└── requirements.txt
```

### Data Flow

```
POST / (CSV upload)
  |
  v
parser.parse_csv()
  - decode utf-8-sig (BOM handled)
  - csv.DictReader (quoted commas work)
  - strip whitespace from every field
  - lowercase email + manager_email
  - derive manager_name from manager_email root
  - attach _row_num (1-based)
  |
  v
validator.validate_rows()
  - Pass 1: index employee_id and email to detect duplicates
  - Pass 2: check required fields, collect accepted rows
  - returns (accepted_rows, validation_errors)
  |
  v
hierarchy.build_hierarchy()
  - Step 1: build Employee objects, by_id dict, by_email dict
  - Step 2: resolve each employee's manager (id → email → conflict → self-check)
  - Step 3: compute roots and direct-report counts
  - Step 4: iterative DFS 3-colour cycle detection
  - returns HierarchyResult
  |
  v
views.upload_view() → render result.html
  - total rows, accepted, rejected
  - validation errors (with row numbers)
  - manager errors (with row numbers)
  - root employees
  - managers and direct-report counts
  - cycle members
```

---

## Setup and Run

### Prerequisites

- Python 3.11+
- pip

### Install

```bash
pip install -r requirements.txt
```

### Run

```bash
python manage.py runserver
```

Open `http://127.0.0.1:8000/` in a browser, upload `sample_hris.csv`, and
inspect the import preview.

---

## Running Tests

```bash
python manage.py test hris_app
```

| Test class | What it covers |
|---|---|
| ParserTest | Whitespace trimming, BOM stripping, missing headers, quoted commas, email lowercasing |
| ValidatorTest | Duplicate ID/email rejection, missing required fields, clean rows accepted |
| HierarchyTest | Root detection, not-found manager, self-management, 2-node cycle, 3-node cycle, reporter-into-cycle not marked, conflict detection, direct-report counts, manager-error employee not a root |
| UploadViewTest | GET form, POST without file, POST non-CSV, POST valid sample, POST bad headers |

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Parse → Validate → Hierarchy pipeline | Each stage is independently testable without Django |
| Lowercase emails at parse time | Prevents duplicated lookup logic throughout the codebase |
| manager_name derived from email | manager_id is often blank; email root is a reliable identifier |
| Iterative DFS (explicit stack) | Python's default recursion limit would fail on deep 100k-employee trees |
| No database persistence | The spec says persistence is not required; in-memory keeps it simple and fast |
| Django over Flask | Matches Diversio's stack; manage.py test gives a ready test runner |

---

## Assumptions and Known Limitations

- Single CSV per upload; multiple files not supported.
- manager_name derivation relies on the `demo.<first>.<last>@diversio.com` pattern.
  A different domain or format would need a different extraction strategy.
- No authentication (intentionally excluded per the spec).
- No database persistence (intentionally excluded per the spec).
- In-memory approach works well up to a few hundred MB; a streaming parser would
  be needed beyond that.
- Cycle detection reports only cycle members. Employees that report into a cycle
  but are not part of it are not flagged — this matches the spec.

---

## AI Tools Used

I used Claude as my primary coding assistant throughout this exercise.

### What AI wrote

Most of the implementation code was generated by Claude, including:

- `parser.py` — CSV decoding, DictReader wiring, whitespace trimming, email lowercasing.
- `validator.py` — Two-pass duplicate detection and required-field checks.
- `hierarchy.py` — Employee dataclasses, manager resolution logic, iterative three-colour DFS cycle detection.
- `views.py` — Django view, file-type guard, context assembly.
- `tests.py` — Full test suite (parser, validator, hierarchy, integration).
- HTML templates — Upload form and result page.

### What I did (design thinking and direction)

I drove every decision about **what to build and why**. Before prompting Claude I:

- Opened `sample_hris.csv` in Excel and manually studied every row.
- Wrote observations in a notebook: blank `manager_id`, mixed-case `manager_email`,
  the `demo.<first>.<last>@diversio.com` email pattern, the `manager_id` ↔ `employee_id`
  mapping, the dangling `DIV-9999` reference, whitespace padding on row 24.
- Manually traced the full expected output before touching any code — my trace
  matched `expected_output_hiris.csv` exactly.
- Chose the three-stage pipeline (parse → validate → hierarchy) as the architecture.
- Specified to Claude exactly which edge cases to handle and why (e.g. "an employee
  with a manager error must still be accepted but must not appear as a root").
- Rejected Claude's suggestion to use the `networkx` library and asked for a
  pure-stdlib DFS instead, because I wanted no heavy dependencies.

### One suggestion I accepted

Claude recommended an explicit iterative stack for the DFS (instead of Python
recursion) to avoid hitting the default recursion limit on large files. I accepted
this because it is correct for files approaching 100 000 rows.

### One suggestion I changed

Claude initially suggested Tarjan's SCC algorithm. I redirected to the simpler
three-colour DFS because Tarjan's SCC would mark all nodes whose strongly-connected
component contains a cycle — including nodes that merely *report into* a cycle —
which the spec explicitly forbids.

### My responsibility

I have read and understood every file I submitted. I can explain what each function
does, why the data structures were chosen, how the DFS detects back-edges, and how
the validation pipeline works. The design thinking that shaped this solution is
entirely my own.

---

## What I Would Do Next (With More Time)

1. **Stream large files** — Replace full in-memory read with a chunked CSV reader
   for files over 100 MB.
2. **Paginate the result table** — For 100 000 employees the single-page result
   would be unwieldy.
3. **Export corrected CSV** — Let the user download a cleaned file with emails
   normalised and whitespace stripped.
4. **Async processing** — For very large uploads, offload parsing and analysis to
   a Celery task and poll for results.
5. **Better cycle reporting** — Show the actual cycle path (A → B → C → A) rather
   than just listing members.
