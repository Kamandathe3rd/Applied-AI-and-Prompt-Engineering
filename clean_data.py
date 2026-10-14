import csv
import re
from pathlib import Path
import datetime
from collections import Counter, defaultdict


CONFIG = {
    "input_path": "dirty_customers.csv",
    "input_fallback_path": "dirty-customers.csv",
    "output_dir": "output",
    "run_date": None,
    "date_order": None,
    "required_columns": ["customer_id", "email"],
    "column_aliases": {
        "customer_id": ["customer_id", "id", "cust_id", "customerid", "customer_no"],
        "first_name": ["first_name", "firstname", "given_name", "fname"],
        "last_name": ["last_name", "lastname", "surname", "family_name", "lname"],
        "full_name": ["full_name", "name", "customer_name"],
        "email": ["email", "e_mail", "email_address", "emailaddress"],
        "phone": ["phone", "phone_number", "mobile", "telephone", "tel", "cell"],
    },
    "date_columns": None,
    "min_date": "1900-01-01",
    "max_age_years": 120,
}

MISSING_TOKENS = {"", "null", "none", "n/a"}
POSSIBLE_PLACEHOLDERS = {"na", "nan", "-", "0", "unknown", "?"}
EMAIL_RE = re.compile(
    r"^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
EDGE_WHITESPACE_RE = re.compile(r"^[\s ﻿]+|[\s ﻿]+$")
INTERNAL_WHITESPACE_RE = re.compile(r"[\s ﻿]+")
HEADER_SEPARATOR_RE = re.compile(r"[ .-]+")
TWO_DIGIT_YEAR_RE = re.compile(
    r"^(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2}|"
    r"\d{1,2}[\s-][A-Za-z]{3,9}[\s-]\d{2}|"
    r"[A-Za-z]{3,9}[\s-]\d{1,2},?[\s-]\d{2})$"
)
ISO_DATE_RE = re.compile(r"^\d{4}[-/.]\d{2}[-/.]\d{2}$")
ISO_DATETIME_RE = re.compile(
    r"^(\d{4}[-/.]\d{2}[-/.]\d{2})[ T]\d{2}:\d{2}(?::\d{2})?$"
)
NUMERIC_DATE_RE = re.compile(r"^(\d{1,2})([/.-])(\d{1,2})\2(\d{4})$")
EIGHT_DIGIT_DATE_RE = re.compile(r"^\d{8}$")
EXCEL_SERIAL_RE = re.compile(r"^\d{1,5}$")
DATE_TIME_FORMATS = (
    "%d %b %Y",
    "%d-%b-%Y",
    "%d %B %Y",
    "%b %d %Y",
    "%B %d %Y",
)
MONTH_NAME_DATE_RE = re.compile(
    r"^(?:\d{1,2}[\s-][A-Za-z]{3,9}[\s-]\d{4}|"
    r"[A-Za-z]{3,9}[\s-]\d{1,2},?[\s-]\d{4})$"
)

REVIEW_FLAGS = {
    "ROW_TOO_SHORT",
    "ROW_TOO_LONG",
    "HEADER_ROW_REPEATED",
    "ALL_FIELDS_MISSING",
    "MISSING_REQUIRED",
    "EMAIL_INVALID",
    "EMAIL_MULTIPLE_OR_SPACES",
    "EMAIL_DUPLICATE",
    "POSSIBLE_DUPLICATE_HIGH",
    "POSSIBLE_DUPLICATE_MEDIUM",
    "CUSTOMER_ID_CONFLICT",
    "DATE_AMBIGUOUS_DAY_MONTH",
    "DATE_TWO_DIGIT_YEAR",
    "DATE_EXCEL_SERIAL_SUSPECTED",
    "DATE_INVALID",
    "DATE_UNRECOGNISED_FORMAT",
    "DATE_TOO_EARLY",
    "DATE_IN_FUTURE",
    "DOB_IMPLAUSIBLE_AGE",
}
INFO_FLAGS = {
    "POSSIBLE_DUPLICATE_LOW",
    "DATE_TIME_DROPPED",
    "DATE_ORDER_ASSUMED",
}


def normalize_header(value):
    return HEADER_SEPARATOR_RE.sub("_", value.lower()).strip("_")


def clean_cell(value, is_name):
    trimmed = EDGE_WHITESPACE_RE.sub("", value)
    if is_name:
        trimmed = INTERNAL_WHITESPACE_RE.sub(" ", trimmed)
    return trimmed


def missing_value(value):
    return value.lower() in MISSING_TOKENS


def add_change(changes, source_row, column, original, new_value, rule_id):
    changes.append(
        {
            "source_row": source_row,
            "column": column,
            "original_value": original,
            "new_value": new_value,
            "rule_id": rule_id,
        }
    )


def map_logical_columns(headers, normalized_headers, aliases):
    result = {}
    for logical_name, alias_names in aliases.items():
        normalized_aliases = {normalize_header(alias) for alias in alias_names}
        for index, normalized in enumerate(normalized_headers):
            if normalized in normalized_aliases:
                result[logical_name] = index
                break
    return result


def get_date_columns(headers, normalized_headers, config):
    configured = config.get("date_columns")
    if configured is not None:
        missing = [name for name in configured if name not in headers]
        if missing:
            raise ValueError("Configured date column(s) not found: " + ", ".join(missing))
        return [(headers.index(name), name, normalized_headers[headers.index(name)]) for name in configured]
    return [
        (index, header, normalized_headers[index])
        for index, (header, normalized) in enumerate(zip(headers, normalized_headers))
        if any(token in normalized for token in ("date", "dob", "birth"))
        or normalized.endswith("_at")
        or normalized.endswith("_on")
    ]


def resolve_input_path(config, root):
    configured = Path(config["input_path"])
    path = configured if configured.is_absolute() else root / configured
    if path.exists():
        return path
    fallback_value = config.get("input_fallback_path")
    if fallback_value:
        fallback = Path(fallback_value)
        fallback = fallback if fallback.is_absolute() else root / fallback
        if fallback.exists():
            return fallback
    return path


def read_input(path):
    raw_bytes = path.read_bytes()
    rows = []
    blank_lines = 0
    encoding = "utf-8-sig"
    try:
        with path.open("r", encoding=encoding, newline="") as source:
            reader = csv.reader(source, strict=True)
            for row in reader:
                if row == []:
                    blank_lines += 1
                else:
                    rows.append(row)
    except UnicodeDecodeError:
        rows = []
        blank_lines = 0
        encoding = "cp1252"
        try:
            with path.open("r", encoding=encoding, newline="") as source:
                reader = csv.reader(source, strict=True)
                for row in reader:
                    if row == []:
                        blank_lines += 1
                    else:
                        rows.append(row)
        except UnicodeDecodeError as error:
            raise ValueError("Input is not valid UTF-8 or cp1252 text.") from error
    if not rows:
        raise ValueError("Input CSV is empty; a header row is required.")
    if len(rows[0]) == 1:
        if ";" in rows[0][0]:
            raise ValueError("Delimiter appears to be semicolon, not comma.")
        if "\t" in rows[0][0]:
            raise ValueError("Delimiter appears to be tab, not comma.")
    return raw_bytes, rows, blank_lines, encoding


def email_result(value):
    normalized = value.lower()
    if normalized == "":
        return normalized, "MISSING", []
    if "," in normalized or ";" in normalized or any(char.isspace() for char in normalized):
        return normalized, "INVALID", ["EMAIL_MULTIPLE_OR_SPACES"]
    if normalized.count("@") != 1:
        return normalized, "INVALID", []
    local, _domain = normalized.split("@")
    if len(normalized) > 254 or len(local) > 64:
        return normalized, "INVALID", []
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return normalized, "INVALID", []
    if EMAIL_RE.fullmatch(normalized) is None:
        return normalized, "INVALID", []
    return normalized, "VALID", []


def date_parse(value, date_order):
    if value == "":
        return "", "MISSING", []
    if TWO_DIGIT_YEAR_RE.fullmatch(value):
        return "", "AMBIGUOUS", ["DATE_TWO_DIGIT_YEAR"]
    if EXCEL_SERIAL_RE.fullmatch(value):
        return "", "AMBIGUOUS", ["DATE_EXCEL_SERIAL_SUSPECTED"]

    datetime_match = ISO_DATETIME_RE.fullmatch(value)
    if datetime_match:
        iso_part = datetime_match.group(1).replace("/", "-").replace(".", "-")
        try:
            parsed = datetime.datetime.strptime(iso_part, "%Y-%m-%d").date()
        except ValueError:
            return "", "INVALID", ["DATE_INVALID"]
        return parsed.isoformat(), "VALID", ["DATE_TIME_DROPPED"]

    if ISO_DATE_RE.fullmatch(value):
        iso_part = value.replace("/", "-").replace(".", "-")
        try:
            parsed = datetime.datetime.strptime(iso_part, "%Y-%m-%d").date()
        except ValueError:
            return "", "INVALID", ["DATE_INVALID"]
        return parsed.isoformat(), "VALID", []

    if EIGHT_DIGIT_DATE_RE.fullmatch(value):
        year = int(value[:4])
        if not 1900 <= year <= 2100:
            return "", "AMBIGUOUS", []
        try:
            parsed = datetime.datetime.strptime(value, "%Y%m%d").date()
        except ValueError:
            return "", "AMBIGUOUS", []
        return parsed.isoformat(), "VALID", []

    month_value = value.replace(",", "")
    month_pattern_matched = MONTH_NAME_DATE_RE.fullmatch(value) is not None
    for date_format in DATE_TIME_FORMATS:
        try:
            parsed = datetime.datetime.strptime(month_value, date_format).date()
            return parsed.isoformat(), "VALID", []
        except ValueError:
            pass
    if month_pattern_matched:
        return "", "INVALID", ["DATE_INVALID"]

    numeric_match = NUMERIC_DATE_RE.fullmatch(value)
    if numeric_match:
        first = int(numeric_match.group(1))
        second = int(numeric_match.group(3))
        year = int(numeric_match.group(4))
        flags = []
        if first > 12 and second <= 12:
            day, month = first, second
        elif second > 12 and first <= 12:
            month, day = first, second
        elif first == second:
            day, month = first, second
        elif first <= 12 and second <= 12:
            if date_order is None:
                return "", "AMBIGUOUS", ["DATE_AMBIGUOUS_DAY_MONTH"]
            if date_order == "DMY":
                day, month = first, second
            else:
                month, day = first, second
            flags.append("DATE_ORDER_ASSUMED")
        else:
            return "", "INVALID", ["DATE_INVALID"]
        try:
            parsed = datetime.date(year, month, day)
        except ValueError:
            return "", "INVALID", ["DATE_INVALID"]
        return parsed.isoformat(), "VALID", flags

    return "", "INVALID", ["DATE_UNRECOGNISED_FORMAT"]


def date_evidence(value):
    if TWO_DIGIT_YEAR_RE.fullmatch(value):
        return 0, 0
    match = NUMERIC_DATE_RE.fullmatch(value)
    if match is None:
        return 0, 0
    first = int(match.group(1))
    second = int(match.group(3))
    if first > 12 and second <= 12:
        return 1, 0
    if second > 12 and first <= 12:
        return 0, 1
    return 0, 0


def is_dob_column(normalized_header):
    return "dob" in normalized_header or "birth" in normalized_header


def age_on(birth_date, reference_date):
    years = reference_date.year - birth_date.year
    if (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def make_name_key(row, mapping):
    if "full_name" in mapping:
        name = row[mapping["full_name"]]
    elif "first_name" in mapping or "last_name" in mapping:
        first = row[mapping["first_name"]] if "first_name" in mapping else ""
        last = row[mapping["last_name"]] if "last_name" in mapping else ""
        name = (first + " " + last).strip()
    else:
        return ""
    name = re.sub(r"[^\w\s]|_", "", name.lower())
    return " ".join(sorted(name.split()))


def make_phone_key(row, mapping):
    if "phone" not in mapping:
        return ""
    value = row[mapping["phone"]]
    digits = re.sub(r"\D", "", value)
    if len(digits) < 7:
        return ""
    return ("+" if value.startswith("+") else "") + digits


def confidence_rank(confidence):
    return {"LOW": 1, "MEDIUM": 2, "HIGH": 3}[confidence]


def find_potential_duplicates(rows, headers, mapping, date_columns, date_results):
    pairs = []
    parent = list(range(len(rows)))
    group_confidences = {}

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right):
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    names = [make_name_key(row["values"], mapping) for row in rows]
    phones = [make_phone_key(row["values"], mapping) for row in rows]
    email_values = [row.get("email_normalized", "") for row in rows]
    email_statuses = [row.get("email_status", "") for row in rows]
    customer_ids = [
        row["values"][mapping["customer_id"]] if "customer_id" in mapping else ""
        for row in rows
    ]
    dob_index = next(
        (
            column_index
            for column_index, _header, normalized in date_columns
            if is_dob_column(normalized)
        ),
        None,
    )
    dob_values = []
    for row_index in range(len(rows)):
        if dob_index is None:
            dob_values.append("")
        else:
            iso_value, status = date_results[row_index][dob_index]
            dob_values.append(iso_value if status == "VALID" else "")
    original_values = [tuple(row["values"]) for row in rows]

    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            rules = []
            confidences = []
            same_valid_email = (
                email_statuses[left] == "VALID"
                and email_statuses[right] == "VALID"
                and email_values[left] != ""
                and email_values[left] == email_values[right]
            )
            same_name = bool(names[left]) and names[left] == names[right]
            same_phone = bool(phones[left]) and phones[left] == phones[right]
            same_dob = bool(dob_values[left]) and dob_values[left] == dob_values[right]
            same_id = bool(customer_ids[left]) and customer_ids[left] == customer_ids[right]
            same_clean_row = original_values[left] == original_values[right]

            if same_valid_email and same_name:
                rules.append("D1")
                confidences.append("HIGH")
            if same_valid_email and not same_name:
                rules.append("D2")
                confidences.append("MEDIUM")
            if same_phone and same_name:
                rules.append("D3")
                confidences.append("HIGH")
            if same_name and same_dob:
                rules.append("D4")
                confidences.append("HIGH")
            if same_id:
                rules.append("D5")
                confidences.append("HIGH")
            if same_clean_row:
                rules.append("D6")
                confidences.append("HIGH")
            if same_phone:
                rules.append("D7")
                confidences.append("LOW")
            if same_name:
                rules.append("D8")
                confidences.append("LOW")

            if not rules:
                continue
            confidence = max(confidences, key=confidence_rank)
            left_row = rows[left]
            right_row = rows[right]
            pair = {
                "duplicate_group_id": "",
                "row_a": left_row["source_row"],
                "row_b": right_row["source_row"],
                "rules": ";".join(rules),
                "confidence": confidence,
                "name_key": names[left],
                "email_normalized_a": email_values[left],
                "email_normalized_b": email_values[right],
                "_left_index": left,
                "_right_index": right,
            }
            pairs.append(pair)
            union(left, right)

    components = defaultdict(list)
    paired_indexes = set()
    pair_confidence_by_root = {}
    for pair in pairs:
        left = pair["_left_index"]
        right = pair["_right_index"]
        paired_indexes.add(left)
        paired_indexes.add(right)
    if paired_indexes:
        components.clear()
        for index in paired_indexes:
            components[find(index)].append(index)
        for pair in pairs:
            root = find(pair["_left_index"])
            current = pair_confidence_by_root.get(root)
            if current is None or confidence_rank(pair["confidence"]) > confidence_rank(current):
                pair_confidence_by_root[root] = pair["confidence"]
    ordered_groups = sorted(
        components.values(),
        key=lambda indexes: min(rows[index]["source_row"] for index in indexes),
    )
    root_to_group_id = {}
    for group_number, indexes in enumerate(ordered_groups, 1):
        group_id = "DUP-{0:04d}".format(group_number)
        root = find(indexes[0])
        confidence = pair_confidence_by_root[root]
        group_confidences[group_id] = confidence
        root_to_group_id[root] = group_id
        for index in indexes:
            rows[index]["duplicate_group_id"] = group_id
            rows[index]["flags"].add("POSSIBLE_DUPLICATE_" + confidence)
    for pair in pairs:
        pair["duplicate_group_id"] = root_to_group_id[find(pair["_left_index"])]

    for pair in pairs:
        left = pair["_left_index"]
        right = pair["_right_index"]
        if "D5" in pair["rules"].split(";"):
            rows[left]["flags"].add("CUSTOMER_ID_CONFLICT")
            rows[right]["flags"].add("CUSTOMER_ID_CONFLICT")
        pair.pop("_left_index")
        pair.pop("_right_index")

    return pairs, group_confidences


def flag_base(flag):
    if ":" in flag:
        return flag.split(":", 1)[0]
    return flag


def write_csv(path, fieldnames, data_rows):
    with path.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data_rows)


def build_report(state, checks):
    headers = state["headers"]
    missing = state["missing_counts"]
    lines = [
        "RESULT: " + ("PASS" if all(checks.values()) else "FAIL"),
        "",
        "# Customer CSV Cleaning Report",
        "",
        "Run timestamp (deterministic): {0}T00:00:00 (derived from run_date).".format(
            state["run_date"].isoformat()
        ),
        "Run date: `{0}`".format(state["run_date"].isoformat()),
        "Configuration: input_path=`{0}`, output_dir=`{1}`, date_order=`{2}`, "
        "required_columns=`{3}`, min_date=`{4}`, max_age_years=`{5}`.".format(
            state["input_path"],
            state["output_dir"],
            state["config"].get("date_order"),
            ", ".join(state["config"]["required_columns"]),
            state["config"]["min_date"],
            state["config"]["max_age_years"],
        ),
        "",
        "## Input",
        "",
        "- Input path used: `{0}`".format(state["input_path"]),
        "- Encoding used: `{0}`".format(state["encoding"]),
        "- Header changes: {0}".format(
            "; ".join(state["header_changes"]) if state["header_changes"] else "none"
        ),
        "- Normalised headers: {0}".format(
            "; ".join(
                "`{0}` -> `{1}`".format(header, normalized)
                for header, normalized in zip(headers, state["normalized_headers"])
            )
        ),
        "- Data rows read: {0}".format(state["rows_read"]),
        "- Blank lines skipped: {0}".format(state["blank_lines"]),
        "- Structural issues: ROW_TOO_SHORT={0}, ROW_TOO_LONG={1}, "
        "HEADER_ROW_REPEATED={2}".format(
            state["structural_counts"]["ROW_TOO_SHORT"],
            state["structural_counts"]["ROW_TOO_LONG"],
            state["structural_counts"]["HEADER_ROW_REPEATED"],
        ),
        "- Extra field column added: {0}".format("yes" if state["has_extra_fields"] else "no"),
        "",
        "## Skipped rules",
        "",
    ]
    lines.extend("- " + item for item in state["skipped_rules"])
    if not state["skipped_rules"]:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Exact duplicates",
            "",
            "- Removed: {0}".format(len(state["removed_rows"])),
            "- Kept/removed source rows: {0}".format(
                "; ".join(
                    "{0} -> {1}".format(item["source_row"], item["kept_source_row"])
                    for item in state["removed_rows"]
                )
                if state["removed_rows"]
                else "none"
            ),
            "",
            "## Whitespace and missing values",
            "",
            "- Cells changed by whitespace rules: {0}".format(state["cells_trimmed"]),
            "- Cells with a missing marker replaced by empty: {0}".format(
                state["missing_replacements"]
            ),
            "- Extra fields: {0} whitespace-changed value(s), {1} missing before, "
            "{2} missing after.".format(
                state["extra_cells_trimmed"],
                state["extra_missing_before"],
                state["extra_missing_after"],
            ),
            "",
            "| Column | Missing before | Missing after | Cells whitespace-changed |",
            "|---|---:|---:|---:|",
        ]
    )
    for index, header in enumerate(headers):
        lines.append(
            "| `{0}` | {1} | {2} | {3} |".format(
                header,
                missing["before"][index],
                missing["after"][index],
                state["trimmed_by_column"][index],
            )
        )
    lines.extend(
        [
            "",
            "Possible placeholder values not changed (M-03):",
            "",
        ]
    )
    if state["placeholder_counts"]:
        for column, value in sorted(state["placeholder_counts"]):
            lines.append(
                "- `{0}` = `{1}`: {2}".format(
                    column, value, state["placeholder_counts"][(column, value)]
                )
            )
    else:
        lines.append("- none found")

    lines.extend(["", "## Emails", ""])
    if state["email_index"] is None:
        lines.append("- Email column not present; email rules skipped.")
    else:
        lines.extend(
            [
                "- Email column: `{0}`".format(headers[state["email_index"]]),
                "- Status counts: VALID={0}, INVALID={1}, MISSING={2}".format(
                    state["email_status_counts"]["VALID"],
                    state["email_status_counts"]["INVALID"],
                    state["email_status_counts"]["MISSING"],
                ),
                "- Repeated email groups: {0}".format(len(state["repeated_emails"])),
                "- Rows affected by repeated emails: {0}".format(
                    sum(len(group["source_rows"]) for group in state["repeated_emails"])
                ),
            ]
        )
        if state["repeated_emails"]:
            lines.extend(["", "Repeated valid addresses (lowercased) and source rows:"])
            for group in state["repeated_emails"]:
                lines.append(
                    "- `{0}`: {1}".format(
                        group["email"],
                        ", ".join(str(row) for row in group["source_rows"]),
                    )
                )

    lines.extend(["", "## Dates", ""])
    if not state["date_columns"]:
        lines.append("- No date columns detected; date rules skipped.")
    for date_column in state["date_columns"]:
        index, header, _normalized = date_column
        counts = state["date_status_counts"][index]
        evidence = state["date_evidence"][index]
        lines.extend(
            [
                "- `{0}` status counts: VALID={1}, MISSING={2}, AMBIGUOUS={3}, "
                "INVALID={4}, OUT_OF_RANGE={5}".format(
                    header,
                    counts["VALID"],
                    counts["MISSING"],
                    counts["AMBIGUOUS"],
                    counts["INVALID"],
                    counts["OUT_OF_RANGE"],
                ),
                "  - Day-month-year evidence (first number > 12): {0}; "
                "month-day-year evidence (second number > 12): {1}.".format(
                    evidence[0], evidence[1]
                ),
            ]
        )
    lines.append(
        "- Set CONFIG['date_order'] only if the evidence and the data source confirm it."
    )

    lines.extend(
        [
            "",
            "## Potential duplicates",
            "",
            "- Groups: {0}; pairs: {1}".format(
                len(state["group_confidences"]), len(state["potential_pairs"])
            ),
            "- Pairs by confidence: HIGH={0}, MEDIUM={1}, LOW={2}".format(
                state["pair_confidence_counts"]["HIGH"],
                state["pair_confidence_counts"]["MEDIUM"],
                state["pair_confidence_counts"]["LOW"],
            ),
        ]
    )
    for pair in state["potential_pairs"]:
        lines.append(
            "- `{0}` rows {1} and {2}: {3} ({4})".format(
                pair["duplicate_group_id"],
                pair["row_a"],
                pair["row_b"],
                pair["rules"],
                pair["confidence"],
            )
        )

    lines.extend(["", "## Review queue", ""])
    lines.append("- Rows needing review: {0}".format(len(state["review_rows"])))
    if state["flag_counts"]:
        lines.extend(
            "- `{0}`: {1}".format(flag, count)
            for flag, count in sorted(state["flag_counts"].items())
        )
    else:
        lines.append("- No review flags.")

    lines.extend(["", "## Reconciliation checks", "", "| Check | Result |", "|---|---|"])
    lines.extend(
        "| {0} | {1} |".format(check, "PASS" if passed else "FAIL")
        for check, passed in checks.items()
    )
    lines.extend(
        [
            "",
            "## Assumptions and limitations",
            "",
            "- Potential matches are flagged only; no uncertain customer row is deleted.",
            "- No fuzzy or edit-distance name matching is used.",
            "- Phone numbers are compared by digits only; country codes and leading zeros "
            "are not inferred or changed.",
            "- English month names are supported. Ambiguous dates are not resolved "
            "without an explicitly configured date_order.",
            "- Email validation checks format only; it does not prove that an address exists.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(config=None):
    config = dict(CONFIG if config is None else config)
    root = Path(__file__).resolve().parent
    input_path = resolve_input_path(config, root)
    output_dir = Path(config["output_dir"])
    if not output_dir.is_absolute():
        output_dir = root / output_dir

    run_date_value = config.get("run_date")
    if run_date_value is None:
        run_date = datetime.date.today()
    elif isinstance(run_date_value, datetime.date):
        run_date = run_date_value
    else:
        run_date = datetime.date.fromisoformat(run_date_value)
    config["run_date"] = run_date.isoformat()

    date_order = config.get("date_order")
    if date_order not in (None, "DMY", "MDY"):
        raise ValueError("date_order must be None, 'DMY', or 'MDY'.")
    min_date = datetime.date.fromisoformat(config["min_date"])

    raw_bytes, raw_rows, blank_lines, encoding = read_input(input_path)
    raw_headers = raw_rows[0]
    headers = []
    header_changes = []
    for index, raw_header in enumerate(raw_headers, 1):
        header = EDGE_WHITESPACE_RE.sub("", raw_header)
        if header != raw_header:
            header_changes.append(
                "column {0}: {1!r} -> {2!r}".format(index, raw_header, header)
            )
        if header == "":
            header = "column_{0}".format(index)
            header_changes.append(
                "column {0}: empty header labelled {1}".format(index, header)
            )
        headers.append(header)
    normalized_headers = [normalize_header(header) for header in headers]
    seen_headers = {}
    for index, normalized in enumerate(normalized_headers):
        if normalized in seen_headers:
            previous = headers[seen_headers[normalized]]
            raise ValueError(
                "Headers {0!r} and {1!r} normalise to the same value {2!r}.".format(
                    previous, headers[index], normalized
                )
            )
        seen_headers[normalized] = index

    mapping = map_logical_columns(headers, normalized_headers, config["column_aliases"])
    absent_required = [
        logical for logical in config["required_columns"] if logical not in mapping
    ]
    if absent_required:
        raise ValueError(
            "Required logical column(s) missing: " + ", ".join(absent_required)
        )
    skipped_rules = [
        "{0} not present - rules skipped".format(logical)
        for logical in ("first_name", "last_name", "full_name", "phone", "email", "customer_id")
        if logical not in mapping
    ]
    date_columns = get_date_columns(headers, normalized_headers, config)
    if config.get("date_columns") is None and not date_columns:
        skipped_rules.append("date columns not present - rules skipped")

    derived_names = ["source_row", "duplicate_group_id", "review_flags", "needs_review"]
    if "email" in mapping:
        derived_names.extend(["email_normalized", "email_status", "email_group"])
    for _index, header, _normalized in date_columns:
        derived_names.extend([header + "_iso", header + "_status"])
    if any(name in headers for name in derived_names):
        collisions = [name for name in derived_names if name in headers]
        raise ValueError(
            "Original header(s) conflict with derived output column(s): "
            + ", ".join(collisions)
        )

    data_rows = []
    structural_counts = Counter()
    raw_seen = {}
    removed_rows = []
    source_row = 1
    for raw_values in raw_rows[1:]:
        source_row += 1
        original = list(raw_values)
        if len(raw_values) < len(headers):
            structural_counts["ROW_TOO_SHORT"] += 1
            padded_values = list(raw_values) + [""] * (len(headers) - len(raw_values))
        else:
            padded_values = list(raw_values[: len(headers)])
        if len(raw_values) > len(headers):
            structural_counts["ROW_TOO_LONG"] += 1
            extra_raw_values = list(raw_values[len(headers) :])
            extra_fields = " | ".join(extra_raw_values)
        else:
            extra_raw_values = []
            extra_fields = ""
        raw_key = tuple(original)
        if raw_key in raw_seen:
            removed_rows.append(
                {
                    "source_row": source_row,
                    "kept_source_row": raw_seen[raw_key],
                    "raw_values": original,
                    "extra_fields": extra_fields,
                }
            )
            continue
        raw_seen[raw_key] = source_row

        row_flags = set()
        if len(raw_values) < len(headers):
            row_flags.add("ROW_TOO_SHORT")
        if len(raw_values) > len(headers):
            row_flags.add("ROW_TOO_LONG")
        if len(padded_values) == len(headers) and [
            clean_cell(value, False) for value in padded_values
        ] == headers:
            row_flags.add("HEADER_ROW_REPEATED")
            structural_counts["HEADER_ROW_REPEATED"] += 1

        data_rows.append(
            {
                "source_row": source_row,
                "raw_values": original,
                "values": padded_values,
                "extra_fields": extra_fields,
                "extra_raw_values": extra_raw_values,
                "flags": row_flags,
                "email_normalized": "",
                "email_status": "",
                "email_group": "",
                "duplicate_group_id": "",
                "date_iso": {},
                "date_status": {},
            }
        )

    changes = []
    missing_counts = {
        "before": [0] * len(headers),
        "after": [0] * len(headers),
    }
    trimmed_by_column = [0] * len(headers)
    placeholder_counts = Counter()
    missing_replacements = 0
    extra_cells_trimmed = 0
    extra_missing_before = 0
    extra_missing_after = 0

    required_indices = {
        mapping[logical]: logical
        for logical in config["required_columns"]
        if logical in mapping
    }
    name_indices = {
        mapping[logical]
        for logical in ("first_name", "last_name", "full_name")
        if logical in mapping
    }

    for row in data_rows:
        raw_values = row["raw_values"]
        cleaned_values = []
        for index, value in enumerate(row["values"]):
            original_value = raw_values[index] if index < len(raw_values) else ""
            cleaned = clean_cell(value, index in name_indices)
            whitespace_changed = cleaned != value
            trimmed_value = cleaned
            if whitespace_changed:
                trimmed_by_column[index] += 1
            normalized_missing = missing_value(cleaned)
            if normalized_missing:
                missing_counts["before"][index] += 1
                if cleaned != "":
                    missing_replacements += 1
                cleaned = ""
            if cleaned == "":
                missing_counts["after"][index] += 1
            if cleaned.lower() in POSSIBLE_PLACEHOLDERS:
                placeholder_counts[(headers[index], cleaned)] += 1

            if whitespace_changed:
                add_change(
                    changes,
                    row["source_row"],
                    headers[index],
                    original_value,
                    cleaned,
                    "W-01" if EDGE_WHITESPACE_RE.sub("", value) != value else "W-02",
                )
            if normalized_missing and trimmed_value != "":
                add_change(
                    changes,
                    row["source_row"],
                    headers[index],
                    original_value,
                    "",
                    "M-01",
                )
            cleaned_values.append(cleaned)
        row["values"] = cleaned_values
        cleaned_extra_values = []
        for value in row["extra_raw_values"]:
            cleaned = clean_cell(value, False)
            whitespace_changed = cleaned != value
            if whitespace_changed:
                extra_cells_trimmed += 1
            normalized_missing = missing_value(cleaned)
            if normalized_missing:
                extra_missing_before += 1
                if cleaned != "":
                    missing_replacements += 1
                    add_change(
                        changes,
                        row["source_row"],
                        "_extra_fields",
                        value,
                        "",
                        "M-01",
                    )
                cleaned = ""
            if cleaned == "":
                extra_missing_after += 1
            if cleaned.lower() in POSSIBLE_PLACEHOLDERS:
                placeholder_counts[("_extra_fields", cleaned)] += 1
            if whitespace_changed:
                add_change(
                    changes,
                    row["source_row"],
                    "_extra_fields",
                    value,
                    cleaned,
                    "W-01",
                )
            cleaned_extra_values.append(cleaned)
        row["extra_fields"] = " | ".join(cleaned_extra_values)

        if all(value == "" for value in cleaned_values):
            row["flags"].add("ALL_FIELDS_MISSING")
        for index, logical in required_indices.items():
            if row["values"][index] == "":
                row["flags"].add("MISSING_REQUIRED:" + logical)

    email_index = mapping.get("email")
    email_status_counts = Counter()
    repeated_email_rows = defaultdict(list)
    if email_index is not None:
        for row in data_rows:
            normalized, status, email_flags = email_result(row["values"][email_index])
            row["email_normalized"] = normalized
            row["email_status"] = status
            email_status_counts[status] += 1
            row["flags"].update(email_flags)
            if status == "INVALID":
                row["flags"].add("EMAIL_INVALID")
            if status == "VALID":
                repeated_email_rows[normalized].append(row)
    email_groups = []
    repeated_emails = []
    email_group_number = 0
    for email, matching_rows in repeated_email_rows.items():
        if len(matching_rows) < 2:
            continue
        email_group_number += 1
        group_id = "EMAIL-{0:04d}".format(email_group_number)
        source_rows = []
        for row in matching_rows:
            row["email_group"] = group_id
            row["flags"].add("EMAIL_DUPLICATE")
            source_rows.append(row["source_row"])
        email_groups.append((email, group_id))
        repeated_emails.append({"email": email, "source_rows": source_rows})

    date_status_counts = {}
    date_evidence_counts = {}
    date_results = [{} for _row in data_rows]
    for column_index, header, normalized_header in date_columns:
        status_counts = Counter()
        evidence = [0, 0]
        is_dob = is_dob_column(normalized_header)
        for row_index, row in enumerate(data_rows):
            original_value = row["values"][column_index]
            evidence_dmy, evidence_mdy = date_evidence(original_value)
            evidence[0] += evidence_dmy
            evidence[1] += evidence_mdy
            iso_value, status, date_flags = date_parse(original_value, date_order)
            if iso_value:
                parsed_date = datetime.date.fromisoformat(iso_value)
                if parsed_date < min_date:
                    status = "OUT_OF_RANGE"
                    date_flags.append("DATE_TOO_EARLY")
                elif parsed_date > run_date:
                    status = "OUT_OF_RANGE"
                    date_flags.append("DATE_IN_FUTURE")
                elif is_dob and age_on(parsed_date, run_date) > config["max_age_years"]:
                    status = "OUT_OF_RANGE"
                    date_flags.append("DOB_IMPLAUSIBLE_AGE")
            if status in ("AMBIGUOUS", "INVALID", "OUT_OF_RANGE"):
                for flag in date_flags:
                    row["flags"].add(flag + ":" + header)
            elif status == "VALID":
                for flag in date_flags:
                    row["flags"].add(flag + ":" + header)
            if status == "MISSING" and column_index in required_indices:
                row["flags"].add("MISSING_REQUIRED:" + required_indices[column_index])
            row["date_iso"][column_index] = iso_value
            row["date_status"][column_index] = status
            date_results[row_index][column_index] = (iso_value, status)
            status_counts[status] += 1
        date_status_counts[column_index] = status_counts
        date_evidence_counts[column_index] = evidence

    potential_pairs, group_confidences = find_potential_duplicates(
        data_rows, headers, mapping, date_columns, date_results
    )
    pair_confidence_counts = Counter(pair["confidence"] for pair in potential_pairs)

    for row in data_rows:
        row["review_flags"] = "|".join(sorted(row["flags"]))
        row["needs_review"] = (
            "Y"
            if any(flag_base(flag) in REVIEW_FLAGS for flag in row["flags"])
            else "N"
        )
    review_rows = [row for row in data_rows if row["needs_review"] == "Y"]
    flag_counts = Counter(
        flag for row in data_rows for flag in row["flags"]
        if flag_base(flag) in REVIEW_FLAGS
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    for stale_name in (
        "customers_clean.csv",
        "review_queue.csv",
        "exact_duplicates_removed.csv",
        "potential_duplicates.csv",
        "change_log.csv",
        "cleaning_report.md",
    ):
        stale_path = output_dir / stale_name
        if stale_path.is_file():
            stale_path.unlink()

    clean_headers = list(headers) + ["source_row"]
    if email_index is not None:
        clean_headers.extend(["email_normalized", "email_status", "email_group"])
    for _index, header, _normalized in date_columns:
        clean_headers.extend([header + "_iso", header + "_status"])
    has_extra_fields = any(row["extra_fields"] for row in data_rows) or any(
        item["extra_fields"] for item in removed_rows
    )
    if has_extra_fields:
        clean_headers.append("_extra_fields")
    clean_headers.extend(["duplicate_group_id", "review_flags", "needs_review"])

    def output_row(row):
        result = {header: value for header, value in zip(headers, row["values"])}
        result["source_row"] = row["source_row"]
        if email_index is not None:
            result["email_normalized"] = row["email_normalized"]
            result["email_status"] = row["email_status"]
            result["email_group"] = row["email_group"]
        for index, header, _normalized in date_columns:
            result[header + "_iso"] = row["date_iso"][index]
            result[header + "_status"] = row["date_status"][index]
        if has_extra_fields:
            result["_extra_fields"] = row["extra_fields"]
        result["duplicate_group_id"] = row["duplicate_group_id"]
        result["review_flags"] = row["review_flags"]
        result["needs_review"] = row["needs_review"]
        return result

    clean_output_rows = [output_row(row) for row in data_rows]
    write_csv(output_dir / "clean_customers.csv", clean_headers, clean_output_rows)

    raw_bytes_after = input_path.read_bytes()
    checks = {
        "AC-01 raw input bytes unchanged": raw_bytes == raw_bytes_after,
        "AC-02 rows_read = clean_rows + exact_duplicates_removed": (
            len(raw_rows) - 1 == len(data_rows) + len(removed_rows)
        ),
        "AC-03 source rows occur exactly once across clean and removed": (
            len({row["source_row"] for row in data_rows}.union(
                item["source_row"] for item in removed_rows
            ))
            == len(data_rows) + len(removed_rows)
        ),
        "AC-04 all original-cell changes are traceable": True,
        "AC-05 changes follow whitespace/missing rules": True,
        "AC-06 review queue matches needs_review": (
            len(review_rows)
            == sum(1 for row in data_rows if row["needs_review"] == "Y")
        ),
        "AC-07 all flags are in the flag catalogue": all(
            flag_base(flag) in REVIEW_FLAGS.union(INFO_FLAGS)
            or flag.startswith("MISSING_REQUIRED:")
            for row in data_rows
            for flag in row["flags"]
        ),
        "AC-08 cleaning acceptance criteria": True,
    }
    change_lookup = {
        (entry["source_row"], entry["column"], entry["original_value"], entry["new_value"])
        for entry in changes
    }
    for row in data_rows:
        for index, cleaned in enumerate(row["values"]):
            raw = row["raw_values"][index] if index < len(row["raw_values"]) else ""
            if raw == cleaned:
                continue
            if (
                row["source_row"],
                headers[index],
                raw,
                cleaned,
            ) not in change_lookup:
                checks["AC-04 all original-cell changes are traceable"] = False
            trimmed = clean_cell(raw, index in name_indices)
            if not (
                cleaned == trimmed
                or (missing_value(trimmed) and cleaned == "")
                or (index >= len(row["raw_values"]) and cleaned == "")
            ):
                checks["AC-05 changes follow whitespace/missing rules"] = False

    clean_sources = [row["source_row"] for row in data_rows]
    removed_sources = [item["source_row"] for item in removed_rows]
    checks["AC-03 source rows occur exactly once across clean and removed"] = (
        len(set(clean_sources + removed_sources)) == len(clean_sources) + len(removed_sources)
        and len(clean_sources) + len(removed_sources) == len(raw_rows) - 1
    )
    checks["AC-08 cleaning acceptance criteria"] = all(
        all(value == "" or not missing_value(value) for value in row["values"])
        and all(
            EDGE_WHITESPACE_RE.sub("", value) == value
            for value in row["values"]
        )
        for row in data_rows
    )
    if email_index is not None:
        checks["AC-08 cleaning acceptance criteria"] = checks[
            "AC-08 cleaning acceptance criteria"
        ] and all(
            row["email_status"] in ("VALID", "INVALID", "MISSING")
            and (
                row["email_status"] != "VALID"
                or EMAIL_RE.fullmatch(row["email_normalized"]) is not None
            )
            for row in data_rows
        )
    for row_index, row in enumerate(data_rows):
        for column_index, iso_value in row["date_iso"].items():
            if iso_value:
                try:
                    datetime.date.fromisoformat(iso_value)
                except ValueError:
                    checks["AC-08 cleaning acceptance criteria"] = False
            if row["date_status"][column_index] == "AMBIGUOUS" and iso_value:
                checks["AC-08 cleaning acceptance criteria"] = False
    for pair in potential_pairs:
        if not (
            pair["row_a"] < pair["row_b"]
            and pair["rules"]
            and pair["confidence"] in ("LOW", "MEDIUM", "HIGH")
        ):
            checks["AC-08 cleaning acceptance criteria"] = False

    state = {
        "headers": headers,
        "normalized_headers": normalized_headers,
        "header_changes": header_changes,
        "rows_read": len(raw_rows) - 1,
        "blank_lines": blank_lines,
        "structural_counts": structural_counts,
        "has_extra_fields": has_extra_fields,
        "removed_rows": removed_rows,
        "missing_counts": missing_counts,
        "cells_trimmed": sum(trimmed_by_column) + extra_cells_trimmed,
        "trimmed_by_column": trimmed_by_column,
        "missing_replacements": missing_replacements,
        "extra_cells_trimmed": extra_cells_trimmed,
        "extra_missing_before": extra_missing_before,
        "extra_missing_after": extra_missing_after,
        "placeholder_counts": placeholder_counts,
        "email_index": email_index,
        "email_status_counts": email_status_counts,
        "repeated_emails": repeated_emails,
        "date_columns": date_columns,
        "date_status_counts": date_status_counts,
        "date_evidence": date_evidence_counts,
        "potential_pairs": potential_pairs,
        "group_confidences": group_confidences,
        "pair_confidence_counts": pair_confidence_counts,
        "review_rows": review_rows,
        "flag_counts": flag_counts,
        "skipped_rules": skipped_rules,
        "input_path": str(input_path),
        "output_dir": str(output_dir),
        "encoding": encoding,
        "run_date": run_date,
        "config": config,
    }
    report = build_report(state, checks)
    with (output_dir / "cleaning_report.txt").open(
        "w", encoding="utf-8-sig", newline=""
    ) as destination:
        destination.write(report)

    print("Input: {0} ({1} rows)".format(input_path.name, state["rows_read"]))
    print("Exact duplicate rows removed: {0}".format(len(removed_rows)))
    print("Clean rows: {0}".format(len(data_rows)))
    print("Report result: {0}".format("PASS" if all(checks.values()) else "FAIL"))
    print("Outputs: {0}".format(output_dir))
    return 0 if all(checks.values()) else 1


def main():
    try:
        return run()
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        print("ERROR: {0}".format(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())