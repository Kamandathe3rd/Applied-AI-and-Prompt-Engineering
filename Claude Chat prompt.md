# Claude Chat Prompt

I am completing a multi-stage AI workflow assessment. My problem is
cleaning a messy customer CSV dataset containing no more than 1,000
records. Create a structured data-cleaning plan for a Python project.
Cover missing values including empty strings, NULL, N/A, and None;
exact duplicate rows; leading and trailing whitespace; invalid,
missing, and repeated emails; potential duplicate customers;
inconsistent, ambiguous, and invalid dates; validation and testing;
output files and reporting. Do not invent customer information.
Preserve the original dataset, remove only exact duplicate rows
automatically, and flag uncertain records for review. Implementation
will use Python's built-in csv, re, pathlib, datetime, and collections
because NumPy is blocked by Windows Application Control. Return
practical Markdown that I can save as cleaning_rules.md. Include
explicit rules and acceptance criteria so another AI coding tool can
implement them without guessing.
