import pdfplumber
import re
import json
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — OPEN PDF (with or without password)
# ═══════════════════════════════════════════════════════════════════════════

def open_pdf(pdf_path: str, password: str = None):
    """
    Opens any PDF file.
    If the PDF is password protected, the password entered by the user is used.
    Raises a clear error if the password is wrong or the file is corrupt.
    """
    try:
        if password and password.strip() != "":
            return pdfplumber.open(pdf_path, password=password.strip())
        return pdfplumber.open(pdf_path)
    except Exception as e:
        raise ValueError(
            f"Could not open PDF.\n"
            f"Possible reasons: Wrong password / Corrupt file / Unsupported format.\n"
            f"Error: {e}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2 — EXTRACT RAW DATA FROM ALL PAGES, ALL TABLES
# ═══════════════════════════════════════════════════════════════════════════

def extract_raw_cell(cell) -> str:
    """Convert any cell to string safely."""
    if cell is None:
        return ""
    return str(cell).strip()


def extract_raw_rows_from_page(page) -> list[list[str]]:
    """
    Tries multiple extraction strategies to handle any bank statement format.
    Strategy 1: Line-based  (works for ruled/bordered tables like HDFC, SBI)
    Strategy 2: Text-based  (works for borderless/passbook style PDFs)
    Strategy 3: Raw words   (last resort fallback for any PDF)
    Returns a flat list of raw rows (each row is a list of string cells).
    """
    all_rows = []

    # Strategy 1: Line-based table extraction
    try:
        tables = page.extract_tables({
            "vertical_strategy":   "lines",
            "horizontal_strategy": "lines",
            "snap_tolerance":      5,
            "join_tolerance":      5,
            "edge_min_length":     10,
        })
        if tables:
            for table in tables:
                for row in table:
                    all_rows.append([extract_raw_cell(c) for c in row])
            if all_rows:
                return all_rows
    except Exception:
        pass

    # Strategy 2: Text-based table extraction
    try:
        tables = page.extract_tables({
            "vertical_strategy":   "text",
            "horizontal_strategy": "text",
            "snap_tolerance":      5,
            "join_tolerance":      5,
        })
        if tables:
            for table in tables:
                for row in table:
                    all_rows.append([extract_raw_cell(c) for c in row])
            if all_rows:
                return all_rows
    except Exception:
        pass

    # Strategy 3: Fallback — extract raw text lines as single-column rows
    try:
        raw_text = page.extract_text() or ""
        for line in raw_text.splitlines():
            line = line.strip()
            if line:
                all_rows.append([line])
    except Exception:
        pass

    return all_rows


def extract_all_raw_data(pdf_path: str, password: str = None) -> dict:
    """
    STEP 2 OUTPUT:
    Opens the PDF and extracts every row from every table on every page.
    Returns raw JSON with all pages and their rows — no cleaning done yet.
    """
    pdf = open_pdf(pdf_path, password)
    raw_pages = []

    try:
        for page_num, page in enumerate(pdf.pages):
            rows = extract_raw_rows_from_page(page)
            raw_pages.append({
                "page_number": page_num + 1,
                "raw_rows":    rows
            })
    finally:
        pdf.close()

    return {
        "source":      Path(pdf_path).name,
        "total_pages": len(raw_pages),
        "pages":       raw_pages
    }


# ═══════════════════════════════════════════════════════════════════════════
# STEP 3 — CLEAN THE RAW DATA
# ═══════════════════════════════════════════════════════════════════════════

# ── 3a. Detect if a row is a real transaction row ──────────────────────────

DATE_PATTERNS = [
    r"^\d{2}/\d{2}/\d{4}$",   # 01/01/2026
    r"^\d{2}/\d{2}/\d{2}$",   # 01/01/26
    r"^\d{2}-\d{2}-\d{4}$",   # 01-01-2026
    r"^\d{2}-\d{2}-\d{2}$",   # 01-01-26
    r"^\d{4}-\d{2}-\d{2}$",   # 2026-01-01
    r"^\d{2}\s+\w{3}\s+\d{4}$",  # 01 Jan 2026
    r"^\d{2}\s+\w{3}\s+\d{2}$",  # 01 Jan 26
]

def is_valid_date(value: str) -> bool:
    """Returns True if value looks like any known date format."""
    value = value.strip()
    for pattern in DATE_PATTERNS:
        if re.match(pattern, value):
            return True
    return False


def is_transaction_row(row: list[str]) -> bool:
    """
    A transaction row must have a valid date in the first non-empty column.
    Handles both left-to-right and passbook styles.
    """
    for cell in row[:3]:  # check first 3 columns
        if cell and is_valid_date(cell):
            return True
    return False


def is_header_or_garbage_row(row: list[str]) -> bool:
    """
    Detects and filters out:
    - Column header rows (Date, Narration, Particulars, etc.)
    - Completely empty rows
    - Footer/disclaimer rows
    - Page number rows
    """
    joined = " ".join(row).strip().lower()

    if not joined:
        return True

    header_keywords = [
        "date", "narration", "particulars", "description",
        "chq", "ref", "cheque", "withdrawal", "deposit",
        "debit", "credit", "balance", "value dt", "transaction",
        "sl no", "sr no", "s.no", "opening", "closing",
        "statement of account", "page no", "page :", "continued",
        "branch", "account no", "ifsc", "micr", "nomination",
        "closing balance brought forward", "carried forward"
    ]

    for kw in header_keywords:
        if kw in joined and not is_transaction_row(row):
            return True

    # Row with all empty cells
    if all(c.strip() == "" for c in row):
        return True

    return False


# ── 3b. Merge multi-line narrations ───────────────────────────────────────

def is_continuation_row(row: list[str]) -> bool:
    """
    A continuation row has no date in col 0 but has text in col 1.
    This happens when narration wraps to the next line in pdfplumber.
    """
    if not row:
        return False
    col0 = row[0].strip() if len(row) > 0 else ""
    col1 = row[1].strip() if len(row) > 1 else ""
    return col0 == "" and col1 != "" and not is_valid_date(col0)


def merge_continuation_rows(rows: list[list[str]]) -> list[list[str]]:
    """
    Merges wrapped narration lines into their parent transaction row.
    Works for HDFC, SBI, ICICI, Axis, passbook styles.
    """
    merged = []
    for row in rows:
        if is_header_or_garbage_row(row):
            continue
        if is_transaction_row(row):
            merged.append(row[:])
        elif is_continuation_row(row) and merged:
            # Append extra narration text to previous row's narration column
            extra = row[1].strip() if len(row) > 1 else ""
            if extra and len(merged[-1]) > 1:
                merged[-1][1] = merged[-1][1] + " " + extra
    return merged


# ── 3c. Amount parsing ─────────────────────────────────────────────────────

def parse_amount(value: str) -> float:
    """
    Parses Indian-format amounts.
    '1,23,456.78' -> 123456.78
    '5,000.00'    -> 5000.0
    'Dr 500.00'   -> 500.0
    ''            -> 0.0
    """
    if not value or value.strip() == "":
        return 0.0
    # Remove currency symbols, Dr, Cr labels, commas
    cleaned = re.sub(r"[₹$,]", "", value)
    cleaned = re.sub(r"(?i)(dr|cr)\s*", "", cleaned).strip()
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return 0.0


def detect_dr_cr_from_value(value: str) -> str:
    """
    Some banks write 'Dr' or 'Cr' inside the amount cell.
    Returns 'DEBIT', 'CREDIT', or '' if not found.
    """
    if re.search(r"(?i)\bdr\b", value):
        return "DEBIT"
    if re.search(r"(?i)\bcr\b", value):
        return "CREDIT"
    return ""


# ── 3d. Narration cleaning ─────────────────────────────────────────────────

def clean_narration(text: str) -> str:
    """
    Cleans raw narration text:
    - Collapses extra spaces and newlines
    - Removes stray special characters
    - Fixes broken words split across lines (e.g. 'SUPE RYES' stays as-is
      since that is how the bank recorded it)
    """
    text = re.sub(r"\s+", " ", text)          # collapse all whitespace
    text = re.sub(r"[^\x20-\x7E]", "", text)  # remove non-printable chars
    return text.strip()


# ── 3e. Determine transaction type ────────────────────────────────────────

def determine_transaction_type(
    withdrawal: float,
    deposit: float,
    dr_cr_hint: str = ""
) -> str:
    """
    Determines DEBIT or CREDIT from:
    1. Withdrawal/Deposit amounts
    2. Dr/Cr hint from amount cell
    3. Falls back to UNKNOWN
    """
    if dr_cr_hint:
        return dr_cr_hint
    if withdrawal > 0 and deposit == 0:
        return "DEBIT"
    if deposit > 0 and withdrawal == 0:
        return "CREDIT"
    if withdrawal > 0 and deposit > 0:
        return "DEBIT"   # edge case: treat as debit
    return "UNKNOWN"


# ── 3f. Map raw row to transaction dict ───────────────────────────────────

def map_row_to_transaction(row: list[str], page_number: int) -> dict | None:
    """
    Maps a cleaned merged row to the final transaction dictionary.
    Handles variable column counts across different bank formats:

    HDFC / ICICI / Axis (7 cols):
      Date | Narration | Chq/Ref | Value Dt | Withdrawal | Deposit | Balance

    SBI Passbook (5 cols):
      Date | Particulars | Debit | Credit | Balance

    Generic (6 cols):
      Date | Description | Ref | Debit | Credit | Balance

    Returns None if the row cannot be mapped to a valid transaction.
    """
    # Pad row to at least 7 columns
    while len(row) < 7:
        row.append("")

    col_count = len([c for c in row if c.strip() != ""])

    date            = ""
    narration       = ""
    chq_ref_no      = ""
    value_date      = ""
    withdrawal_amt  = 0.0
    deposit_amt     = 0.0
    closing_balance = 0.0
    dr_cr_hint      = ""

    if col_count >= 6:
        # Standard 7-column format (HDFC, ICICI, Axis, Kotak)
        date            = row[0]
        narration       = row[1]
        chq_ref_no      = row[2]
        value_date      = row[3]
        dr_cr_hint      = detect_dr_cr_from_value(row[4]) or detect_dr_cr_from_value(row[5])
        withdrawal_amt  = parse_amount(row[4])
        deposit_amt     = parse_amount(row[5])
        closing_balance = parse_amount(row[6])

    elif col_count == 5:
        # 5-column format (SBI passbook, PNB)
        date            = row[0]
        narration       = row[1]
        dr_cr_hint      = detect_dr_cr_from_value(row[2]) or detect_dr_cr_from_value(row[3])
        withdrawal_amt  = parse_amount(row[2])
        deposit_amt     = parse_amount(row[3])
        closing_balance = parse_amount(row[4])

    elif col_count == 4:
        # 4-column format (some passbooks: Date | Desc | Amount | Balance)
        date            = row[0]
        narration       = row[1]
        dr_cr_hint      = detect_dr_cr_from_value(row[2])
        amount          = parse_amount(row[2])
        closing_balance = parse_amount(row[3])
        if dr_cr_hint == "DEBIT":
            withdrawal_amt = amount
        elif dr_cr_hint == "CREDIT":
            deposit_amt = amount
        else:
            withdrawal_amt = amount  # assume debit if unknown

    else:
        return None  # cannot map this row

    # Final validation — must have a valid date
    if not is_valid_date(date):
        return None

    txn_type = determine_transaction_type(withdrawal_amt, deposit_amt, dr_cr_hint)

    return {
        "date":             date.strip(),
        "narration":        clean_narration(narration),
        "chq_ref_no":       chq_ref_no.strip(),
        "value_date":       value_date.strip(),
        "withdrawal_amt":   withdrawal_amt,
        "deposit_amt":      deposit_amt,
        "closing_balance":  closing_balance,
        "transaction_type": txn_type,
        "page_number":      page_number,
    }


# ── 3g. Remove duplicates ─────────────────────────────────────────────────

def remove_duplicates(transactions: list[dict]) -> list[dict]:
    """
    Removes exact duplicate transactions.
    A duplicate is defined as same date + narration + withdrawal + deposit.
    """
    seen = set()
    unique = []
    for t in transactions:
        key = (
            t["date"],
            t["narration"],
            t["withdrawal_amt"],
            t["deposit_amt"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


# ── 3h. Remove UNKNOWN rows ────────────────────────────────────────────────

def remove_unknown_transactions(transactions: list[dict]) -> list[dict]:
    """
    Removes rows where both withdrawal and deposit are 0
    and transaction type is UNKNOWN — these are garbage rows.
    """
    return [
        t for t in transactions
        if not (t["transaction_type"] == "UNKNOWN"
                and t["withdrawal_amt"] == 0.0
                and t["deposit_amt"] == 0.0)
    ]


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4 — FULL PIPELINE: RAW EXTRACT → CLEAN → FINAL JSON
# ═══════════════════════════════════════════════════════════════════════════

def clean_raw_data(raw_data: dict) -> dict:
    """
    STEP 3+4:
    Takes the raw JSON from Step 2 and produces the final cleaned
    transaction JSON. Pipeline per page:
      raw rows → filter headers/garbage → merge multi-line narrations
      → map to transaction dict → remove duplicates → remove unknowns
    """
    all_transactions = []

    for page in raw_data["pages"]:
        page_num = page["page_number"]
        rows     = page["raw_rows"]

        # Filter garbage/header rows and merge continuation rows
        merged = merge_continuation_rows(rows)

        # Map each row to a transaction dict
        for row in merged:
            txn = map_row_to_transaction(row, page_num)
            if txn:
                all_transactions.append(txn)

    # Remove duplicates
    all_transactions = remove_duplicates(all_transactions)

    # Remove UNKNOWN zero-amount garbage rows
    all_transactions = remove_unknown_transactions(all_transactions)

    return {"transactions": all_transactions}


def extract_bank_statement(pdf_path: str, password: str = None) -> dict:
    """
    PUBLIC FUNCTION — this is what Tejas calls from routes/api.py.

    Full pipeline:
      1. Open PDF (with optional password)
      2. Extract all raw rows from all pages
      3. Clean: filter, merge, parse, deduplicate
      4. Return final JSON with transactions list only

    Args:
        pdf_path : path to the PDF file
        password : password entered by user (None if unprotected)

    Returns:
        { "transactions": [ { ... }, ... ] }
    """
    # Step 2: Extract raw data
    raw_data = extract_all_raw_data(pdf_path, password)

    # Step 3 + 4: Clean and return final JSON
    final_data = clean_raw_data(raw_data)

    return final_data


# ═══════════════════════════════════════════════════════════════════════════
# STEP 5 — SAVE TO JSON FILE
# ═══════════════════════════════════════════════════════════════════════════

def save_to_json(data: dict, output_path: str):
    """Saves final cleaned data to a JSON file."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"JSON saved -> {output_path}")


# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT — run directly from terminal for testing
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_parser.py <path_to_pdf> [password]")
        sys.exit(1)

    pdf_file = sys.argv[1]
    pdf_pass = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Opening  : {pdf_file}")
    print(f"Password : {'Provided' if pdf_pass else 'None (unprotected)'}")
    print("Extracting and cleaning...")

    result = extract_bank_statement(pdf_file, pdf_pass)

    save_to_json(result, "output.json")
    print(f"Total transactions extracted : {len(result['transactions'])}")