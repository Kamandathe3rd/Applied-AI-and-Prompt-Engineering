# Multi-Stage AI Workflow Across UX Types

## 1. Project Overview

**Project name:** Customer CSV Cleaning Workflow\
**Problem:** Clean and validate a messy customer CSV file containing no
more than 1,000 records while preserving the original data and flagging
uncertain records for review.

This project demonstrates how outputs from one AI user-experience type
can be passed to another AI tool. Claude Chat is used to plan the
cleaning rules, and GitHub Copilot in PyCharm is used to help implement
and test those rules in Python.

## 2. Tools and Technologies

-   **Claude Chat --- Chat UX:** Creates the structured data-cleaning
    plan.
-   **GitHub Copilot in PyCharm --- IDE-based AI UX:** Helps implement,
    review, and troubleshoot the Python script inside the development
    environment.
-   **Python standard library:** `csv`, `re`, `pathlib`, `datetime`, and
    `collections`.
-   **PyCharm terminal:** Runs the script and displays its output.
-   **Git (if used):** Tracks changes to project files.

Pandas and NumPy are intentionally not required for this implementation
because NumPy encountered a Windows Application Control policy error in
the development environment.

## 3. Problem Statement

Customer CSV files can contain inconsistent or incomplete information,
such as:

-   Missing values represented by empty cells or markers such as `NULL`,
    `N/A`, or `None`.
-   Leading or trailing spaces in fields.
-   Exact duplicate rows.
-   Missing, invalid, or repeated email addresses.
-   Customers who may be duplicates because their names or other fields
    are similar.
-   Dates that are invalid or ambiguous.

The goal is to apply consistent, documented cleaning rules without
inventing missing customer information or automatically deleting records
when a match is uncertain.

## 4. Workflow Diagram

``` mermaid
flowchart TD
    A[Dirty customer CSV] --> B[Claude Chat: create cleaning plan]
    B --> C[Save plan as cleaning_rules.md]
    C --> D[GitHub Copilot in PyCharm]
    D --> E[Implement clean_data.py]
    A --> E
    E --> F[Run script in PyCharm terminal]
    F --> G{Execution and checks successful?}
    G -- No --> H[Review error and update code with Copilot]
    H --> F
    G -- Yes --> I[output/clean_customers.csv]
    G -- Yes --> J[output/cleaning_report.txt]
    I --> K[Inspect outputs and document evidence]
    J --> K
```

## 5. Stage 1 --- Claude Chat (Planning)

Claude Chat is the first AI tool. Its task is to turn the problem
statement into explicit rules that can be implemented by a second AI
tool.

### Prompt used

> I am completing a multi-stage AI workflow assessment. My problem is
> cleaning a messy customer CSV dataset containing no more than 1,000
> records. Create a structured data-cleaning plan for a Python project.
> Cover missing values including empty strings, NULL, N/A, and None;
> exact duplicate rows; leading and trailing whitespace; invalid,
> missing, and repeated emails; potential duplicate customers;
> inconsistent, ambiguous, and invalid dates; validation and testing;
> output files and reporting. Do not invent customer information.
> Preserve the original dataset, remove only exact duplicate rows
> automatically, and flag uncertain records for review. Implementation
> will use Python's built-in csv, re, pathlib, datetime, and collections
> because NumPy is blocked by Windows Application Control. Return
> practical Markdown that I can save as cleaning_rules.md. Include
> explicit rules and acceptance criteria so another AI coding tool can
> implement them without guessing.

### Output passed to Stage 2

The response from Claude Chat is saved in the project as:

`cleaning_rules.md`

This file is the handoff artifact between the two AI tools. It records
the proposed cleaning rules and acceptance criteria so that the
implementation is based on a documented plan rather than an unrelated
prompt.

**Evidence to capture:** A screenshot of Claude Chat's generated plan
and the `cleaning_rules.md` file open in PyCharm.

## 6. Stage 2 --- GitHub Copilot in PyCharm (Implementation)

GitHub Copilot is the second AI tool. It is used inside PyCharm to help
implement the cleaning plan as a Python program.

### Implementation prompt

> Read `cleaning_rules.md` and implement the specified CSV-cleaning
> workflow in `clean_data.py`.
>
> Use only Python's built-in libraries: csv, re, pathlib, datetime, and
> collections. Do not use Pandas or NumPy.
>
> Input file: `dirty_customers.csv` in the project root.
>
> Requirements: - Inspect the actual CSV headers and row count. -
> Normalize missing-value markers and trim whitespace. - Remove exact
> duplicate rows and report the count. - Identify email columns,
> normalize valid emails to lowercase, and flag missing or invalid
> emails. - Report repeated email addresses. - Flag potential duplicate
> customers without automatically deleting uncertain matches. -
> Standardize dates only when unambiguous; flag ambiguous or invalid
> dates. - Preserve the original file. - Create
> `output/clean_customers.csv` and `output/cleaning_report.txt`. -
> Report accurate counts and handle errors. - Follow `cleaning_rules.md`
> rather than inventing new rules.
>
> First explain the planned changes, then generate the complete code.
> Help me run and verify it, and distinguish tests actually run from
> tests not yet run.

### Expected implementation artifact

`clean_data.py`

Copilot should be asked to follow the rules in `cleaning_rules.md`.
Review the suggested code before running it. In particular, check how
the script identifies email and date columns, defines exact duplicates,
treats missing-value markers, and flags uncertain customer matches.

**Evidence to capture:** A screenshot of Copilot's implementation
assistance and `clean_data.py` open in PyCharm.

## 7. Project Structure

The project should have a structure similar to the following. The
`.venv` folder may also exist and is not shown here.

``` text
csv-cleaning-project/
├── dirty_customers.csv
├── cleaning_rules.md
├── clean_data.py
├── workflow_documentation.md
└── output/
    ├── clean_customers.csv
    └── cleaning_report.txt
```

The input file must be present at the path expected by the script. The
`output` folder and its files should be created by the program if that
is how the implementation is designed.

## 8. Running the Program

Open the project in PyCharm and use its terminal. Confirm that the
terminal is in the project root and that the intended Python environment
is active.

Run:

``` powershell
python clean_data.py
```

If an error appears, read the complete traceback. Use Copilot to help
diagnose the error, make the correction, and run the program again.
Record the actual error and fix if it is relevant to the assessment.

## 9. Validation and Acceptance Criteria

Use this checklist after implementing the script. Mark each item only
after verifying it.

-   [ ] The script reads `dirty_customers.csv` successfully.
-   [ ] The script reports the number of input records accurately.
-   [ ] Missing-value markers and whitespace are handled according to
    `cleaning_rules.md`.
-   [ ] Only exact duplicate rows are automatically removed.
-   [ ] Missing and invalid emails are flagged, and repeated emails are
    reported.
-   [ ] Potential duplicate customers are flagged for review rather than
    automatically deleted.
-   [ ] Only unambiguous dates are standardized; ambiguous or invalid
    dates are flagged.
-   [ ] The original input file remains unchanged.
-   [ ] `output/clean_customers.csv` is created and can be opened.
-   [ ] `output/cleaning_report.txt` is created and its counts agree
    with the processed data.
-   [ ] The script handles a missing input file or malformed input with
    a clear error message.
-   [ ] The results have been inspected, not merely assumed correct
    because the program ran.

If a criterion has not been checked, leave it unchecked and explain why
in the results section.

## 10. Test Results

Complete this section only after running the program and inspecting its
output. Do not report a test as passed unless you actually performed it.

  -----------------------------------------------------------------------
  Check                   Actual result           Status
  ----------------------- ----------------------- -----------------------
  Script execution        \[Record terminal       \[Pass/Fail/Not run\]
                          output\]                

  Input record count      \[Record observed       \[Pass/Fail/Not run\]
                          count\]                 

  Exact duplicate         \[Record observed count \[Pass/Fail/Not run\]
  handling                and inspection\]        

  Email validation and    \[Record observed       \[Pass/Fail/Not run\]
  repeated emails         findings\]              

  Date handling           \[Record observed       \[Pass/Fail/Not run\]
                          findings\]              

  Clean CSV output        \[Confirm file exists   \[Pass/Fail/Not run\]
                          and inspect it\]        

  Cleaning report         \[Confirm file exists   \[Pass/Fail/Not run\]
                          and compare counts\]    

  Original input          \[Explain how you       \[Pass/Fail/Not run\]
  preserved               checked\]               

  Error handling          \[Describe test or mark \[Pass/Fail/Not run\]
                          not tested\]            
  -----------------------------------------------------------------------

### Summary of actual results

-   **Input rows:** \[Fill in after running\]
-   **Output rows:** \[Fill in after running\]
-   **Exact duplicate rows removed:** \[Fill in after running\]
-   **Missing or invalid email findings:** \[Fill in after running\]
-   **Repeated email findings:** \[Fill in after running\]
-   **Potential duplicate customers flagged:** \[Fill in after running\]
-   **Date issues flagged:** \[Fill in after running\]
-   **Known limitations or unresolved issues:** \[Fill in after
    inspection\]

## 11. How the Two AI UX Types Were Chained

The workflow passes a concrete artifact between tools:

1.  Claude Chat receives the problem description and produces the
    cleaning plan.
2.  The plan is saved as `cleaning_rules.md`.
3.  GitHub Copilot in PyCharm is instructed to read that exact file.
4.  Copilot helps produce `clean_data.py` from the written rules.
5.  The program is run in the PyCharm terminal and its output files are
    inspected.
6.  Any issues discovered during testing are fed back into the
    implementation step for correction.

This is a multi-stage workflow because the first tool produces an
artifact that directly guides the second tool. The workflow is not
complete until the generated code has been executed and its outputs
checked.

## 12. Limitations and Responsible Data Handling

-   The quality of the output depends on the input file and the accuracy
    of the cleaning rules.
-   Email validation checks format; it does not prove that an email
    address exists or belongs to a particular customer.
-   Similar names or shared contact details may indicate a possible
    duplicate but are not sufficient proof to delete a record.
-   Ambiguous dates should be flagged rather than silently interpreted.
-   Missing information should not be invented.
-   Keep the original CSV unchanged and avoid sharing real customer data
    with AI tools unless permitted by the relevant data-handling policy.
-   AI-generated code must be reviewed and tested. A successful run
    alone does not prove every cleaning rule is correct.

## 13. Evidence to Submit


Evidence required by the assessment
instructions:

1.  Claude Chat prompt and generated cleaning plan.
2.  `cleaning_rules.md` open in PyCharm.
3.  GitHub Copilot in PyCharm assisting with the implementation.
4.  `clean_data.py` in the editor.
5.  PyCharm terminal showing the actual script execution.
6.  `output/clean_customers.csv` open for inspection.
7.  `output/cleaning_report.txt` open for inspection.
8.  This documentation with the workflow diagram and completed test
    results.



## 14. Conclusion

This project demonstrates a workflow across two different AI UX types:
Claude Chat for planning and GitHub Copilot in PyCharm for
implementation. The cleaning plan is passed between the tools through
`cleaning_rules.md`, and the resulting Python script produces a cleaned
CSV and a report for review.

The assessment is complete when the code has been run, the outputs have
been inspected, the test-results table has been completed truthfully,
and the required evidence has been collected.
