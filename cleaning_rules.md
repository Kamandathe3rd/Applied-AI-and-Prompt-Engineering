# Customer CSV Cleaning Rules

**Purpose:** A rules spec for cleaning a messy customer CSV (≤ 1,000 records) in Python. It is detailed enough for another AI coding tool to build without guessing.

**Hard constraints**

| ID | Constraint |
|----|-----------|
| C-01 | **Never modify the raw input file.** Read only. Write all outputs to a separate folder. |
| C-02 | **Never invent data.** Do not impute, guess, autocorrect, or fill any value. A value is either kept, trimmed, standardised to empty, or copied into a *derived* column. |
| C-03 | **Only exact duplicate rows are removed automatically.** Every other problem is *flagged* and the row is kept. |
| C-04 | **Flag uncertain records for review.** Do not resolve them. |
| C-05 | Implementation imports **only** `csv`, `re`, `pathlib`, `datetime`, `collections`. No NumPy or pandas, and no third-party packages. Tests may also use `unittest` (standard library). |
| C-06 | Behaviour is deterministic. The same input and config always give byte-identical outputs. Row order follows the input order. |

---

## 0. Project layout and configuration

```
customer_cleaning/
├── data/raw/customers.csv          # original file, read only
├── src/clean_customers.py          # single script, CONFIG at top
├── tests/test_cleaning.py
├── tests/fixtures/sample_messy.csv # fixture in §7.3
└── output/                         # all generated files (§8)
```

Run with: `python src/clean_customers.py` (all settings come from `CONFIG`, so the script needs no CLI parsing).

```python
CONFIG = {
    "input_path": "data/raw/customers.csv",
    "output_dir": "output",
    "run_date": None,            # "YYYY-MM-DD" or None (= today). Tests must set it.
    "date_order": None,          # None | "DMY" | "MDY". Only set after reviewing the date evidence in the report.
    "required_columns": ["customer_id", "email"],   # logical names (see aliases)
    "column_aliases": {          # header matching, after header normalisation (§0.1)
        "customer_id": ["customer_id", "id", "cust_id", "customerid", "customer_no"],
        "first_name":  ["first_name", "firstname", "given_name", "fname"],
        "last_name":   ["last_name", "lastname", "surname", "family_name", "lname"],
        "full_name":   ["full_name", "name", "customer_name"],
        "email":       ["email", "e_mail", "email_address", "emailaddress"],
        "phone":       ["phone", "phone_number", "mobile", "telephone", "tel", "cell"],
    },
    "date_columns": None,        # None = auto-detect (§6.1), or an explicit list of original header names
    "min_date": "1900-01-01",
    "max_age_years": 120,        # used for date-of-birth columns only
}
```

### 0.1 Header handling

- **H-01** Read the first row as the header. Strip whitespace and a leading BOM (`﻿`) from each header. Log any header that changed.
- **H-02** To match aliases, normalise the header: lowercase, then replace runs of spaces, hyphens, and dots with `_`, then strip `_` from both ends. The **original (trimmed) header text is still used in the output**.
- **H-03** If two headers normalise to the same value, **stop with an error** naming both. Do not guess which one to use.
- **H-04** If an empty header is found, name it `column_<n>` (1-based position) and log it as a structural label, not data.
- **H-05** If a logical column (for example `email`) is not found, skip the rules that depend on it. Write `"<column> not present – rules skipped"` in the report. Do not fail.
- **H-06** If a required column is absent from the header, stop with an error.

### 0.2 File reading

- **F-01** Open with `newline=""`. Try `encoding="utf-8-sig"` first. On `UnicodeDecodeError`, retry with `cp1252` and record which encoding was used in the report. If both fail, stop with an error.
- **F-02** The delimiter is a comma. If the header parses to a single column that contains `;` or a tab, **stop with an error** that says "delimiter appears to be X". Do not auto-switch.
- **F-03** Each data row gets `source_row` = its physical CSV record number, with the header = 1 and the first data row = 2. Every output file carries `source_row`.
- **F-04** Blank lines (the csv reader returns `[]`) are not records. Skip them and report the count as `blank_lines_skipped`.
- **F-05** If a row has fewer fields than the header, pad it with `""` and flag `ROW_TOO_SHORT`. If it has more, put the extra values, joined with ` | `, into a derived column `_extra_fields` and flag `ROW_TOO_LONG`.
- **F-06** If a data row's trimmed values equal the header's, flag `HEADER_ROW_REPEATED`. This often happens when files were concatenated. Do not remove the row automatically unless it is also an exact duplicate.
- **F-07** Read the raw file's bytes before processing and again at the end. They must be equal (AC-01).

### 0.3 Processing order (mandatory)

| Step | Action | Section |
|------|--------|---------|
| P1 | Load, assign `source_row`, structural checks | §0 |
| P2 | Remove exact duplicate rows (on **raw** values) | §2 |
| P3 | Trim whitespace | §3 |
| P4 | Standardise missing values | §1 |
| P5 | Validate and normalise emails, detect repeats | §4 |
| P6 | Parse and validate dates | §6 |
| P7 | Detect potential duplicate customers | §5 |
| P8 | Aggregate flags, set `needs_review` | §8.2 |
| P9 | Write outputs and report | §8 |
| P10 | Run reconciliation checks, write results to report | §7 |

> Note: the section numbers follow the order of your requirements. The processing order above takes precedence.

---

## 1. Missing values

**Rules**

- **M-01** After trimming (P3), a cell counts as missing if its value, **compared case-insensitively**, is in:
  `MISSING_TOKENS = {"", "null", "none", "n/a"}`
  This list covers empty strings, `NULL`, `N/A`, `None`, and whitespace-only cells (whitespace-only cells are `""` after trimming).
- **M-02** Replace missing cells with `""` in the clean output. Track replacements internally for reconciliation, but do not create a change-log file.
- **M-03** Do **not** treat `NA`, `nan`, `-`, `0`, `unknown`, or `?` as missing. `NA` is a real surname, and the others may carry meaning. Count them in the report under "possible placeholder values (not changed)" so the user can decide.
- **M-04** Never fill a missing value from another row, column, or default.
- **M-05** A missing value in a `required_columns` field → flag `MISSING_REQUIRED:<column>` (review).
- **M-06** A missing value in any other column → no flag. Count it only.
- **M-07** If every original column of a row is missing → flag `ALL_FIELDS_MISSING` (review). Keep the row.

**Acceptance criteria**

- AC-M1: No cell in the original columns of `clean_customers.csv` equals a missing token, case-insensitively (except `""`).
- AC-M2: A cell that was missing in the raw file is `""` in the clean file. No missing cell gains a value.
- AC-M3: The report has a per-column table with missing counts **before** (raw tokens and blanks) and **after**.

---

## 2. Exact duplicate rows

**Rules**

- **X-01** Two rows are exact duplicates when their **raw field lists**, exactly as returned by `csv.reader`, are identical. This comparison is case-sensitive, whitespace-sensitive, and includes the field count.
- **X-02** Keep the **first** occurrence and remove later occurrences from the clean output. Report the removed count and each removed `source_row` → `kept_source_row` pair in `cleaning_report.txt`; do not create a separate duplicate-rows file.
- **X-03** Rows that become identical only **after** trimming or missing-value standardisation are **not** removed. Flag them as potential duplicates with rule `D6` (§5).
- **X-04** Exact duplicate removal is the **only** step that drops a row.

**Acceptance criteria**

- AC-X1: `rows_read == clean_rows + exact_duplicates_removed`.
- AC-X2: Each input `source_row` appears exactly once internally as either a clean row or an exact duplicate removed.
- AC-X3: Each removed row's raw values equal the raw values of its kept row.

---

## 3. Leading and trailing whitespace

**Rules**

- **W-01** Strip leading and trailing whitespace from **every** cell. This includes spaces, tabs, `\r`, `\n`, non-breaking space ` `, and BOM `﻿`. Use `re.sub(r"^[\s ﻿]+|[\s ﻿]+$", "", value)`.
- **W-02** In **name columns only** (`first_name`, `last_name`, `full_name`), collapse internal runs of whitespace to one space. Do not change internal whitespace in any other column.
- **W-03** Do not change letter case in the original columns. Case normalisation only happens in derived columns (emails, match keys).
- **W-04** Track every changed cell internally for reconciliation (rule `W-01` or `W-02`); do not create a change-log file.

**Acceptance criteria**

- AC-W1: No original-column cell in the clean output starts or ends with a character matched by `[\s ﻿]`.
- AC-W2: The number of internally tracked `W-01`/`W-02` changes equals the "cells trimmed" count in the report.

---

## 4. Email addresses

The original `email` column keeps its trimmed and missing-standardised value. Derived columns: `email_normalized`, `email_status`.

**Normalisation**

- **E-01** `email_normalized` = the trimmed email lowercased in full. If the email is missing, `email_normalized` is `""`.
- **E-02** Do **not** autocorrect anything. For example, `gmial.com` stays as it is, and so does a missing `@`, a trailing dot, or a stray character.

**Validation** (check `email_normalized` in this order. The first failure sets the status.)

| Rule | Check | Result |
|------|-------|--------|
| E-03 | value is `""` | `MISSING` |
| E-04 | contains `,` `;` or whitespace (multiple addresses or a broken value) | `INVALID` + flag `EMAIL_MULTIPLE_OR_SPACES` |
| E-05 | does not have exactly one `@` | `INVALID` |
| E-06 | total length > 254 or local part > 64 | `INVALID` |
| E-07 | local part starts or ends with `.`, or contains `..` | `INVALID` |
| E-08 | does not fully match `EMAIL_RE` below | `INVALID` |
| — | otherwise | `VALID` |

```python
EMAIL_RE = re.compile(
    r"^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
```

- **E-09** Status `INVALID` → flag `EMAIL_INVALID` (review). Status `MISSING` → handled by M-05 if `email` is required.
- **E-10 Repeated emails:** among clean rows, if a non-empty `email_normalized` with status `VALID` appears in more than one row, flag **every** occurrence `EMAIL_DUPLICATE` (review). Fill a derived column `email_group` with `EMAIL-0001`, `EMAIL-0002`, … numbered in order of first appearance.
- **E-11** Missing or invalid emails never count as repeats of each other.

**Acceptance criteria**

- AC-E1: Every clean row has `email_status` ∈ {`VALID`, `INVALID`, `MISSING`}.
- AC-E2: Every `VALID` value fully matches `EMAIL_RE` and passes E-04 to E-07.
- AC-E3: Apart from trimming and missing-standardisation, the original `email` column is unchanged.
- AC-E4: The number of rows with `EMAIL_DUPLICATE` equals the sum of the sizes of groups with ≥ 2 members.

---

## 5. Potential duplicate customers

These are **flagged only, never merged or removed.**

**Match keys** (derived, used only for comparison)

- **K-01 `name_key`:** use `full_name` if present, otherwise `first_name + " " + last_name`. Lowercase it. Remove characters that are not letters, digits, or spaces (`re.sub(r"[^\w\s]|_", "", s)`). Collapse spaces, then **sort the tokens** so `Smith John` = `John Smith`. If no name is present, `name_key` is `""`.
- **K-02 `phone_key`:** keep the digits of the phone only. Keep a leading `+` if the original began with one. If there are fewer than 7 digits → `""`. Do not add or remove country codes or leading zeros.
- **K-03** `dob_key` = the ISO date of a date-of-birth column (§6) when its status is `VALID`. Otherwise `""`.
- **K-04 Empty keys never match.** Two rows that both lack an email do not match on email.

**Pair rules** (compare every pair of clean rows. n ≤ 1,000, so O(n²) is acceptable.)

| Rule | Condition | Confidence |
|------|-----------|------------|
| D1 | same `email_normalized` (VALID) **and** same `name_key` | HIGH |
| D2 | same `email_normalized` (VALID), different or empty `name_key` | MEDIUM |
| D3 | same `phone_key` **and** same `name_key` | HIGH |
| D4 | same `name_key` **and** same `dob_key` | HIGH |
| D5 | same non-empty `customer_id` | HIGH + flag `CUSTOMER_ID_CONFLICT` |
| D6 | all original columns identical after P3 and P4 | HIGH |
| D7 | same `phone_key` only | LOW |
| D8 | same `name_key` only | LOW |

- **D-09** A pair can match more than one rule. Record all of them (for example `D1;D3`). The pair confidence is the highest one.
- **D-10** Build groups with union-find over all matched pairs. Assign `duplicate_group_id` = `DUP-0001`, … in order of each group's smallest `source_row`. The group confidence is the highest pair confidence in the group.
- **D-11** For each row in a group, flag `POSSIBLE_DUPLICATE_<CONFIDENCE>`. HIGH and MEDIUM flags are review flags. LOW is an info flag. Report detected groups, pairs, and rules in `cleaning_report.txt`; do not create a separate potential-duplicates file.
- **D-12** Do not use fuzzy or edit-distance matching. It needs extra modules and would be guessing. Record this as a known limitation in the report.

**Acceptance criteria**

- AC-D1: Every reported potential-duplicate pair has `row_a < row_b`, at least one rule ID, and a confidence.
- AC-D2: No pair is matched on an empty key.
- AC-D3: The row count of `clean_customers.csv` is unchanged by this step.
- AC-D4: Every row with a `duplicate_group_id` appears in at least one pair.

---

## 6. Dates

### 6.1 Which columns

- **DT-01** If `CONFIG["date_columns"]` is `None`, treat a column as a date column when its normalised header contains `date`, `dob`, or `birth`, or ends with `_at` or `_on`.
- **DT-02** A date column is a **date-of-birth column** when its normalised header contains `dob` or `birth`.

### 6.2 Derived columns

For each date column `<col>`, add `<col>_iso` (`YYYY-MM-DD` or `""`) and `<col>_status`. The original column keeps only trimmed and missing-standardised text.

Status values: `VALID`, `MISSING`, `AMBIGUOUS`, `INVALID`, `OUT_OF_RANGE`.

### 6.3 Parsing rules (apply in order, and match each regex against the full string)

| Rule | Input pattern | Handling |
|------|--------------|----------|
| DT-03 | `""` | `MISSING` |
| DT-04 | Integer of 1–5 digits (e.g. `45366`) | `AMBIGUOUS`, flag `DATE_EXCEL_SERIAL_SUSPECTED`. **Do not convert.** |
| DT-05 | `YYYY-MM-DD`, `YYYY/MM/DD`, `YYYY.MM.DD` | Parse with `strptime` |
| DT-06 | Same as DT-05 followed by `T` or a space and `HH:MM` or `HH:MM:SS` | Parse the date part, info flag `DATE_TIME_DROPPED` |
| DT-07 | 8 digits `YYYYMMDD` | Parse if valid with year 1900–2100. Otherwise `AMBIGUOUS` |
| DT-08 | Month name, English, full or 3-letter, case-insensitive: `15 Mar 2024`, `15-Mar-2024`, `15 March 2024`, `Mar 15 2024`, `March 15, 2024` | Parse with `%d %b %Y`, `%d-%b-%Y`, `%d %B %Y`, `%b %d %Y`, `%B %d %Y` (remove commas first) |
| DT-09 | Any pattern above or below with a **2-digit year** (e.g. `05-Mar-24`, `03/04/24`) | `AMBIGUOUS`, flag `DATE_TWO_DIGIT_YEAR`. **Do not parse.** |
| DT-10 | Numeric `A/B/YYYY`, `A-B-YYYY`, `A.B.YYYY` (A, B are 1–2 digits) | See DT-11 |
| DT-11 | • A > 12 and B ≤ 12 → day-month-year<br>• B > 12 and A ≤ 12 → month-day-year<br>• A == B → same date either way, parse it<br>• both ≤ 12 and A ≠ B → if `date_order` is set, use it and add info flag `DATE_ORDER_ASSUMED`. Otherwise `AMBIGUOUS` with flag `DATE_AMBIGUOUS_DAY_MONTH`<br>• both > 12 → `INVALID` | — |
| DT-12 | Parse fails because the calendar date does not exist (e.g. `2024-02-30`, `31/04/2024`) | `INVALID`, flag `DATE_INVALID` |
| DT-13 | Nothing matches | `INVALID`, flag `DATE_UNRECOGNISED_FORMAT` |

### 6.4 Range rules (only for successfully parsed dates)

- **DT-14** A date before `min_date` → `OUT_OF_RANGE`, flag `DATE_TOO_EARLY`.
- **DT-15** A date after `run_date` → `OUT_OF_RANGE`, flag `DATE_IN_FUTURE`.
- **DT-16** Date-of-birth columns: an age above `max_age_years` on `run_date` → `OUT_OF_RANGE`, flag `DOB_IMPLAUSIBLE_AGE`.
- **DT-17** For `OUT_OF_RANGE`, still fill `<col>_iso` so the reviewer can see the parsed value.
- **DT-18** `AMBIGUOUS`, `INVALID`, and `OUT_OF_RANGE` are review flags. `MISSING` is a review flag only if the column is required (M-05).

### 6.5 Date-order evidence (report only)

- **DT-19** For each date column, count the values that matched DT-11 as day-month-year evidence (A > 12) and as month-day-year evidence (B > 12). Print both counts in the report with this note: *"Set CONFIG['date_order'] only if the evidence and the data source confirm it."* **Never apply the order automatically.**

**Acceptance criteria**

- AC-DT1: Every non-empty `<col>_iso` matches `^\d{4}-\d{2}-\d{2}$` and parses with `datetime.date.fromisoformat`.
- AC-DT2: Every value with a 2-digit year, or with an ambiguous day and month (when `date_order` is `None`), has an empty `<col>_iso`.
- AC-DT3: Every row has `<col>_status` set for every date column.
- AC-DT4: All date checks use the configured `run_date`, never the system clock directly.

---

## 7. Validation and testing

### 7.1 Reconciliation checks (run inside the script at P10, written to the report as PASS or FAIL)

| ID | Check |
|----|-------|
| AC-01 | The raw file's bytes are identical before and after the run |
| AC-02 | `rows_read == clean_rows + exact_duplicates_removed` |
| AC-03 | Each `source_row` appears exactly once across clean + removed |
| AC-04 | **Traceability (no invented data):** for every original-column cell, `clean_value == raw_value` **or** an internally tracked change maps `raw_value → clean_value` with a rule ID from {W-01, W-02, M-01} |
| AC-05 | Each changed cell is either a whitespace-trimmed version of its raw value or `""` that replaced a missing token |
| AC-06 | The reported review-queue row count equals the number of clean rows where `needs_review == "Y"` |
| AC-07 | Every flag in `review_flags` is in the flag catalogue (§8.2) |
| AC-08 | All of §1–§6's acceptance criteria hold |

If any check fails, the script finishes writing its outputs, writes `RESULT: FAIL` at the top of the report, and exits with code 1.

### 7.2 Unit tests (`tests/test_cleaning.py`, `unittest`)

| Test | Input | Expected |
|------|-------|----------|
| T01 | `"  NULL "`, `"n/a"`, `"None"`, `""`, `"   "` | all → `""`, missing |
| T02 | `"NA"`, `"nan"`, `"0"` | unchanged, not missing |
| T03 | `" Ann\t"` | `"Ann"` |
| T04 | name `"Mary   Ann"` | `"Mary Ann"`. A non-name column with internal spaces is unchanged |
| T05 | `"A@B.COM "` | normalized `a@b.com`, `VALID` |
| T06 | `a@b`, `a@@b.com`, `.a@b.com`, `a..b@c.com`, `a@b.com;c@d.com` | `INVALID` |
| T07 | the same email in 2 rows | both rows flagged `EMAIL_DUPLICATE`, same `email_group` |
| T08 | `2024-02-30` | `INVALID` |
| T09 | `15/03/2024` | `2024-03-15`, `VALID` |
| T10 | `03/15/2024` | `2024-03-15`, `VALID` |
| T11 | `03/04/2024`, `date_order=None` | `AMBIGUOUS`, iso `""` |
| T12 | `03/04/2024`, `date_order="DMY"` | `2024-04-03`, `DATE_ORDER_ASSUMED` |
| T13 | `05-Mar-24` | `AMBIGUOUS`, `DATE_TWO_DIGIT_YEAR` |
| T14 | `45366` | `AMBIGUOUS`, `DATE_EXCEL_SERIAL_SUSPECTED` |
| T15 | a date after `run_date` | `OUT_OF_RANGE`, iso filled |
| T16 | `March 5, 2024` | `2024-03-05` |
| T17 | two identical raw rows | one removed, `kept_source_row` correct |
| T18 | two rows that differ only by whitespace | none removed, D6 pair HIGH |
| T19 | `John Smith` / `Smith John` + the same email | D1 HIGH |
| T20 | two rows with empty email and empty phone | no pair |
| T21 | short row and long row | `ROW_TOO_SHORT` / `ROW_TOO_LONG`, extras kept |
| T22 | the script's source | imports ⊆ {csv, re, pathlib, datetime, collections} |
| T23 | run twice on the fixture | all output files byte-identical |
| T24 | the fixture in §7.3 | expected counts in §7.3 |

### 7.3 End-to-end fixture (`tests/fixtures/sample_messy.csv`, synthetic data only)

Run with `run_date = "2026-10-14"` and `date_order = None`.

```csv
customer_id,first_name,last_name,email,phone,signup_date
1,Ana,Mensah,ana.mensah@example.com,0241234567,2024-03-15
1,Ana,Mensah,ana.mensah@example.com,0241234567,2024-03-15
2, Kofi ,Boateng,KOFI.B@EXAMPLE.COM ,N/A,15/03/2024
3,Efua,Owusu,efua.owusu@example,NULL,03/04/2024
4,Kwame,Asante,,0201112222,2024-02-30
5,Kofi,Boateng,kofi.b@example.com,0559998888,2024-03-16
6,Yaw,Darko,None,,2027-01-01
7,Akua,Frimpong,akua@@example.com,,"March 5, 2024"
8,Ama,Serwaa,ama.serwaa@example.com,0241234500,05-Mar-24
9,Ana , Mensah,ana.mensah@example.com,0241234567,2024-03-15
10,Esi,Nyarko,esi.nyarko@example.com,,
```

**Expected results**

| Metric | Expected |
|--------|----------|
| rows_read | 11 |
| exact_duplicates_removed | 1 (source_row 3, kept 2) |
| clean_rows | 10 |
| missing tokens replaced | 3 (rows 4 phone, 5 phone, 8 email) |
| cells trimmed | 4 (row 4 first_name and email, row 11 first_name and last_name) |
| email VALID / INVALID / MISSING | 6 / 2 (rows 5, 9) / 2 (rows 6, 8) |
| email groups | 2: rows {2, 11}, {4, 7} |
| signup_date VALID / OUT_OF_RANGE / AMBIGUOUS / INVALID / MISSING | 5 (2, 4, 7, 9, 11) / 1 (8) / 2 (5, 10) / 1 (6) / 1 (12) |
| duplicate groups | 2, both HIGH via D1: {2, 11}, {4, 7} |
| review_queue rows | 9 (all except source_row 12) |
| reconciliation | all PASS |

---

## 8. Output files and reporting

### 8.1 Files (in `output/`, written as `utf-8-sig` so Excel shows accented characters, `newline=""`)

| File | Contents |
|------|----------|
| `clean_customers.csv` | All rows except exact duplicates. Original columns (trimmed headers, original order), then derived columns in this order: `source_row`, `email_normalized`, `email_status`, `email_group`, `<col>_iso` and `<col>_status` per date column, `_extra_fields` (only if any row is too long), `duplicate_group_id`, `review_flags`, `needs_review` |
| `cleaning_report.txt` | Human-readable summary with counts, detected issues, duplicate pairs, review flags, and reconciliation results |

### 8.2 Flags

- `review_flags`: flags joined with `|`, sorted alphabetically, with column-specific flags written as `FLAG:column` (for example `DATE_AMBIGUOUS_DAY_MONTH:signup_date`).
- `needs_review` = `Y` if the row has at least one **review** flag, otherwise `N`.

| Flag | Severity |
|------|----------|
| ROW_TOO_SHORT, ROW_TOO_LONG, HEADER_ROW_REPEATED, ALL_FIELDS_MISSING | review |
| MISSING_REQUIRED:&lt;col&gt; | review |
| EMAIL_INVALID, EMAIL_MULTIPLE_OR_SPACES, EMAIL_DUPLICATE | review |
| POSSIBLE_DUPLICATE_HIGH, POSSIBLE_DUPLICATE_MEDIUM, CUSTOMER_ID_CONFLICT | review |
| DATE_AMBIGUOUS_DAY_MONTH, DATE_TWO_DIGIT_YEAR, DATE_EXCEL_SERIAL_SUSPECTED, DATE_INVALID, DATE_UNRECOGNISED_FORMAT, DATE_TOO_EARLY, DATE_IN_FUTURE, DOB_IMPLAUSIBLE_AGE | review |
| POSSIBLE_DUPLICATE_LOW, DATE_TIME_DROPPED, DATE_ORDER_ASSUMED | info |

### 8.3 `cleaning_report.txt` sections

1. **Result:** `PASS` or `FAIL`, run timestamp, `run_date`, config values used.
2. **Input:** path, encoding used, header (original and normalised), rows read, blank lines skipped, structural issues.
3. **Exact duplicates:** count and `source_row → kept_source_row` list.
4. **Whitespace and missing values:** cells trimmed per column, and a per-column table of missing counts before and after. Also possible placeholders that were not changed (M-03).
5. **Emails:** status counts, number of repeated-email groups, and rows affected.
6. **Dates:** status counts per column, and the date-order evidence (DT-19).
7. **Potential duplicates:** groups and pairs by confidence, and the rules that fired.
8. **Review queue:** total rows needing review, and counts per flag. This is a report summary, not a separate CSV.
9. **Reconciliation checks:** AC-01 to AC-08 with PASS or FAIL.
10. **Assumptions and limitations:** no fuzzy name matching. Phone numbers are compared by digits only, so `+27…` vs `0…` will not match. Only English month names are supported. Ambiguous dates are not resolved.

**Acceptance criteria**

- AC-O1: Exactly `clean_customers.csv` and `cleaning_report.txt` are generated in `output/`.
- AC-O2: Each count in the report agrees with the rows processed and the flags in `clean_customers.csv`.
- AC-O3: Nothing is written outside `output_dir`, and the raw file is untouched.

---

## 9. Definition of done

- [ ] All unit tests T01–T24 pass with `python -m unittest discover tests`.
- [ ] The fixture run matches every expected value in §7.3.
- [ ] The real dataset run reports `RESULT: PASS` and finishes in under 5 seconds.
- [ ] The script imports only `csv`, `re`, `pathlib`, `datetime`, `collections`.
- [ ] A person has reviewed the rows marked `needs_review` in `clean_customers.csv` and the date-order evidence before any manual fixes or `date_order` setting.
