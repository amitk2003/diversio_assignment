# Diversio Engineer I Exercise: HRIS Import Preview

## Context

A client has sent Diversio an HRIS export. Before any employee or reporting data is written to the platform, Client Success needs a simple way to inspect the file, understand its hierarchy, and find data problems.

Build a small web application that accepts the supplied CSV and presents a useful import preview.

## Timebox

Spend no more than **90 minutes** building and testing the application. Record the walkthrough after the coding timebox.

If you do not finish everything, submit the best working version and describe what you would do next. A small, reliable application is better than a large unfinished one.

## AI tools and technical ownership

You may use documentation, internet search, an LLM, or a coding agent. Using AI will not count against you; using it well is part of modern engineering. You remain responsible for reading, understanding, testing, and validating everything you submit.

You should be able to explain all non-trivial code in your own words, justify the main decisions, and describe how you would debug or change the implementation. We are looking for engineers who use AI as a tool—not people who simply pass its output along without understanding it. This article captures the distinction: [Don't be a meat proxy](https://gruhn.me/blog/2026-08-03/).

**A code-only submission is not enough.** For evaluation purposes, code submitted without the required narrated walkthrough will be treated as AI-generated work for which no technical understanding or ownership has been demonstrated. The submission will be considered incomplete.

## What to build

Your application must let a user upload an HRIS CSV from a browser and then show:

- the total number of source rows;
- the employees accepted for analysis;
- row-level validation errors with source row numbers;
- root employees who have no manager;
- managers and their direct-report counts;
- employees that participate in a reporting cycle.

Analyze the upload before writing employee or relationship data to a database. Database persistence is not required.

The interface can be plain HTML. We evaluate whether it is clear and usable, not its visual polish.

## CSV contract

The file contains these headers, in any order:

```text
employee_id,employee_name,email,manager_id,manager_email,department
```

Use normal CSV parsing so quoted values such as names containing commas work correctly. Support UTF-8 files with or without a byte-order mark.

Normalize values as follows:

- Trim surrounding whitespace from every value.
- Lowercase `email` and `manager_email`.
- Keep employee IDs case-sensitive.

### Employee identity rules

- `employee_id` and `email` are required.
- Each must be unique after normalization.
- Every row sharing a duplicated employee ID or email is invalid.
- Invalid identity rows must not participate in manager lookup or hierarchy analysis.

### Manager rules

Manager rows may appear before or after their reports.

- Both manager fields blank: the employee is a root.
- Only `manager_id` supplied: look up the manager by employee ID.
- Only `manager_email` supplied: look up the manager by normalized email.
- Both supplied: both must identify the same employee.
- Report a useful error when a manager cannot be found, the two references conflict, or an employee manages themselves.
- An employee with a manager error remains an accepted employee but does not produce a reporting relationship and is not a root.

### Reporting cycles

Identify employees that are members of a reporting cycle. Do not classify an employee as cyclic merely because they report into a cycle.

## Technical expectations

- Use Python.
- Django is preferred because it matches Diversio's stack, but another Python web framework is acceptable if you explain the choice.
- Keep parsing and hierarchy logic separate enough to test without driving a browser.
- Add at least two focused automated tests for behavior you consider important.
- Handle a malformed upload with a clear error instead of an unhandled exception.
- Be ready to explain the time and space complexity of your approach for files approaching 100,000 employees.

Include a README in your submission with:

- setup and run instructions;
- test instructions;
- assumptions and known limitations;
- the approximate time you spent;
- the AI tools you used, if any.

## Do not spend time on

You do not need to add:

- authentication or user accounts;
- production deployment;
- database persistence;
- a JavaScript frontend framework;
- elaborate styling;
- features unrelated to the import preview.

## Video walkthrough and code explanation

Submit a **screen recording of no more than 10 minutes** with narration. Your camera is optional, and editing or high production quality is not expected.

The recording is a required code explanation, not only a product demonstration. We strongly evaluate whether you understand and can clearly explain the code you submitted. A working application without a clear code explanation is not a complete submission.

Please use the recording to:

1. Demonstrate the working application with the supplied sample.
2. Open the key source files and trace the code from file upload through parsing, validation, hierarchy analysis, and the displayed result.
3. Explain what the main functions or classes do, why you structured them that way, and how data changes between steps.
4. Explain the important algorithms and data structures, including how you detect reporting cycles.
5. Show your tests and connect each test to the behavior it verifies.
6. Discuss an important edge case and one trade-off or improvement you would make with more time.
7. Explain how you used AI tools, including at least one suggestion you accepted, changed, or rejected and why.

You do not need to explain every line, but you should be able to explain all non-trivial code in your own words. As a guide, spend about two minutes on the demonstration, five minutes on the code, two minutes on tests and trade-offs, and one minute on AI-tool usage.

We evaluate technical ownership, understanding, and clarity—not video production quality.

## Questions

Questions are welcome. Email [ashwini@diversio.com](mailto:ashwini@diversio.com) with this subject line so your message can be filtered correctly:

```text
[Diversio Engineer I Exercise] Question - Your Full Name
```

Ask specific questions about the requirements or submission process. We can clarify the exercise, but we cannot debug your implementation or choose an approach for you.

## Submission

Email [ashwini@diversio.com](mailto:ashwini@diversio.com) with this exact subject format:

```text
[Diversio Engineer I Exercise] Submission - Your Full Name
```

Include:

1. A link to the source repository, or a ZIP archive containing the source.
2. A viewable link to the narrated video walkthrough.
3. The approximate time you spent on the implementation, excluding the recording.

Both the source and video are required. Make sure all links are accessible and do not include credentials, secrets, or client data.

## What happens after submission

- We will respond to every candidate who sends a complete submission, whether or not they are selected to continue.
- Candidates selected after the exercise review will be invited to a second-round interview with the Diversio Engineering team to discuss their implementation and approach.
- A third-round interview may be scheduled for deeper technical and behavioural questions.

## What we evaluate

- A working end-to-end import preview.
- Demonstrated ownership and understanding of the submitted code.
- Programming and problem-solving fundamentals.
- Correct handling of data and reporting relationships.
- Code clarity, testing, and error handling.
- Practical scoping and decision-making.
- Your understanding and explanation of the submitted work.
