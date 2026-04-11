"""
pdf_parser.py — CrediSense
Handles BOTH text-based PDFs (pdfplumber) and image-based PDFs (OCR via pytesseract).
Automatically detects which method to use.
Tested on HDFC Bank image-based statements.
"""

import re
import os
import json
from pathlib import Path

# ─── Optional imports (graceful degradation) ──────────────────────────────────
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

try:
    from pdf2image import convert_from_path
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

DATE_PATTERNS = [
    r"\d{2}/\d{2}/\d{4}",   # 01/01/2026
    r"\d{2}/\d{2}/\d{2}",   # 01/01/26
    r"\d{2}-\d{2}-\d{4}",   # 01-01-2026
    r"\d{2}-\d{2}-\d{2}",   # 01-01-26
    r"\d{4}-\d{2}-\d{2}",   # 2026-01-01
]

def is_valid_date(value: str) -> bool:
    value = value.strip()
    for pattern in DATE_PATTERNS:
        if re.fullmatch(pattern, value):
            return True
    return False

def parse_amount(val: str) -> float:
    if not val or val.strip() in ["", "-", "|", "None"]:
        return 0.0
    cleaned = re.sub(r"[₹$,\s]", "", val.strip())
    cleaned = re.sub(r"(?i)(dr|cr)\s*", "", cleaned).strip()
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return 0.0

def extract_month(date_str: str) -> str:
    """Convert any date format to YYYY-MM key."""
    # Try DD/MM/YYYY or DD/MM/YY
    m = re.match(r"(\d{2})[/\-](\d{2})[/\-](\d{2,4})", date_str)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        if len(year) == 2:
            year = "20" + year
        # Check if format is YYYY-MM-DD
        if int(day) > 12:  # definitely DD first
            return f"{year}-{month.zfill(2)}"
        else:
            return f"{year}-{month.zfill(2)}"
    # Try YYYY-MM-DD
    m = re.match(r"(\d{4})[/\-](\d{2})[/\-](\d{2})", date_str)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return "unknown"

def determine_txn_type(prev_balance, current_balance, amount):
    """
    Determine DEBIT or CREDIT by comparing consecutive balances.
    More reliable than parsing Dr/Cr labels in OCR output.
    """
    if prev_balance is None:
        # First transaction — can't determine direction
        return "DEBIT", amount, 0.0
    diff = round(current_balance - prev_balance, 2)
    if diff >= 0:
        return "CREDIT", 0.0, amount
    else:
        return "DEBIT", amount, 0.0

def clean_narration(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\x20-\x7E]", "", text)
    text = re.sub(r"[|]", "", text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# METHOD 1 — OCR PARSER (for image-based PDFs like HDFC scanned statements)
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_line_ocr(line: str) -> dict | None:
    """
    Parse a single OCR text line into a transaction dict (partial).
    Returns None if line doesn't look like a transaction.
    """
    # Must start with a date
    date_match = re.match(r"^\s*(\d{2}/\d{2}/\d{2,4})", line)
    if not date_match:
        return None

    date = date_match.group(1)
    rest = line[date_match.end():]

    # Find all decimal amounts in the rest of the line
    amounts = re.findall(r"\d{1,3}(?:,\d{2,3})*(?:\.\d{2})?", rest)

    if len(amounts) < 2:
        return None  # Need at least transaction amount + closing balance

    closing_balance   = parse_amount(amounts[-1])
    transaction_amount = parse_amount(amounts[-2])

    # Narration = everything before the first amount, cleaned
    first_amt_idx = rest.find(amounts[0])
    raw_narration = rest[:first_amt_idx]
    narration = clean_narration(raw_narration)[:120]

    return {
        "date":              date,
        "narration":         narration,
        "closing_balance":   closing_balance,
        "transaction_amount": transaction_amount,
    }


def _extract_via_ocr(pdf_path: str, password: str = None) -> list[dict]:
    """
    Full OCR pipeline:
    1. Convert each PDF page to image (300 DPI)
    2. Run Tesseract OCR
    3. Parse lines to extract transactions
    4. Determine DEBIT/CREDIT from balance direction
    """
    if not OCR_AVAILABLE:
        raise ImportError(
            "OCR libraries not installed. Run: pip install pdf2image pytesseract"
        )

    print("  [OCR] Converting PDF pages to images...")
    convert_kwargs = {"dpi": 300}
    if password:
        convert_kwargs["userpw"] = password

    try:
        images = convert_from_path(pdf_path, **convert_kwargs)
    except Exception as e:
        raise ValueError(f"Could not convert PDF to images: {e}")

    print(f"  [OCR] Running OCR on {len(images)} pages...")

    all_transactions = []
    prev_balance = None

    for page_num, img in enumerate(images):
        ocr_text = pytesseract.image_to_string(img, config="--psm 6")
        lines = ocr_text.split("\n")

        for line in lines:
            result = _parse_line_ocr(line)
            if result is None:
                continue

            txn_type, withdrawal, deposit = determine_txn_type(
                prev_balance,
                result["closing_balance"],
                result["transaction_amount"]
            )
            prev_balance = result["closing_balance"]

            all_transactions.append({
                "date":             result["date"],
                "narration":        result["narration"],
                "chq_ref_no":       "",
                "value_date":       result["date"],
                "withdrawal_amt":   withdrawal,
                "deposit_amt":      deposit,
                "closing_balance":  result["closing_balance"],
                "transaction_type": txn_type,
                "month":            extract_month(result["date"]),
                "page_number":      page_num + 1,
            })

    print(f"  [OCR] Extracted {len(all_transactions)} transactions")
    return all_transactions


# ═══════════════════════════════════════════════════════════════════════════════
# METHOD 2 — PDFPLUMBER PARSER (for text-based PDFs)
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_raw_cell(cell) -> str:
    if cell is None:
        return ""
    return str(cell).strip()

def _extract_rows_from_page(page) -> list[list[str]]:
    all_rows = []

    # Strategy 1: line-based
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
                    all_rows.append([_extract_raw_cell(c) for c in row])
            if all_rows:
                return all_rows
    except Exception:
        pass

    # Strategy 2: text-based
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
                    all_rows.append([_extract_raw_cell(c) for c in row])
            if all_rows:
                return all_rows
    except Exception:
        pass

    # Strategy 3: raw text lines
    try:
        raw_text = page.extract_text() or ""
        for line in raw_text.splitlines():
            line = line.strip()
            if line:
                all_rows.append([line])
    except Exception:
        pass

    return all_rows

HEADER_KEYWORDS = [
    "date", "narration", "particulars", "description",
    "chq", "ref", "cheque", "withdrawal", "deposit",
    "debit", "credit", "balance", "value dt", "transaction",
    "sl no", "sr no", "s.no", "opening", "closing",
    "statement of account", "page no", "page :", "continued",
    "branch", "account no", "ifsc", "micr", "nomination",
]

def _is_header_row(row: list[str]) -> bool:
    joined = " ".join(row).strip().lower()
    if not joined:
        return True
    if all(c.strip() == "" for c in row):
        return True
    for kw in HEADER_KEYWORDS:
        if kw in joined and not any(is_valid_date(c) for c in row[:3]):
            return True
    return False

def _map_row(row: list[str], page_num: int) -> dict | None:
    while len(row) < 7:
        row.append("")

    col_count = len([c for c in row if c.strip() != ""])
    date = narration = ""
    withdrawal_amt = deposit_amt = closing_balance = 0.0
    dr_cr_hint = ""

    if col_count >= 6:
        date           = row[0]
        narration      = row[1]
        withdrawal_amt = parse_amount(row[4])
        deposit_amt    = parse_amount(row[5])
        closing_balance = parse_amount(row[6])
    elif col_count == 5:
        date           = row[0]
        narration      = row[1]
        withdrawal_amt = parse_amount(row[2])
        deposit_amt    = parse_amount(row[3])
        closing_balance = parse_amount(row[4])
    elif col_count == 4:
        date           = row[0]
        narration      = row[1]
        amount         = parse_amount(row[2])
        closing_balance = parse_amount(row[3])
        withdrawal_amt = amount
    else:
        return None

    if not is_valid_date(date):
        return None

    if withdrawal_amt > 0 and deposit_amt == 0:
        txn_type = "DEBIT"
    elif deposit_amt > 0 and withdrawal_amt == 0:
        txn_type = "CREDIT"
    else:
        txn_type = "UNKNOWN"

    return {
        "date":             date.strip(),
        "narration":        clean_narration(narration),
        "chq_ref_no":       "",
        "value_date":       date.strip(),
        "withdrawal_amt":   withdrawal_amt,
        "deposit_amt":      deposit_amt,
        "closing_balance":  closing_balance,
        "transaction_type": txn_type,
        "month":            extract_month(date.strip()),
        "page_number":      page_num,
    }

def _extract_via_pdfplumber(pdf_path: str, password: str = None) -> list[dict]:
    if not PDFPLUMBER_AVAILABLE:
        raise ImportError("pdfplumber not installed. Run: pip install pdfplumber")

    open_kwargs = {}
    if password:
        open_kwargs["password"] = password

    transactions = []
    with pdfplumber.open(pdf_path, **open_kwargs) as pdf:
        for page_num, page in enumerate(pdf.pages):
            rows = _extract_rows_from_page(page)
            for row in rows:
                if _is_header_row(row):
                    continue
                txn = _map_row(row, page_num + 1)
                if txn:
                    transactions.append(txn)

    # Remove duplicates
    seen = set()
    unique = []
    for t in transactions:
        key = (t["date"], t["narration"][:30], t["withdrawal_amt"], t["deposit_amt"])
        if key not in seen:
            seen.add(key)
            unique.append(t)

    return unique


# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-DETECT: is PDF text-based or image-based?
# ═══════════════════════════════════════════════════════════════════════════════

def _is_image_based_pdf(pdf_path: str, password: str = None) -> bool:
    """
    Returns True if the PDF contains only images (no embedded text).
    This happens with scanned/photographed bank statements like HDFC DigiSave.
    """
    if not PDFPLUMBER_AVAILABLE:
        return True  # Assume image-based if pdfplumber unavailable

    try:
        open_kwargs = {"password": password} if password else {}
        with pdfplumber.open(pdf_path, **open_kwargs) as pdf:
            for page in pdf.pages[:2]:  # Check first 2 pages only
                chars = page.chars
                images = page.images
                # If page has images but no text chars → image-based PDF
                if len(images) > 0 and len(chars) == 0:
                    return True
                # If page has text chars → text-based PDF
                if len(chars) > 50:
                    return False
    except Exception:
        pass

    return True  # Default to OCR if uncertain


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — this is what routes/api.py calls
# ═══════════════════════════════════════════════════════════════════════════════

def extract_bank_statement(pdf_path: str, password: str = None) -> dict:
    """
    Main entry point. Auto-detects PDF type and uses the right method.

    Args:
        pdf_path : path to the PDF file (temp file from Flask upload)
        password : optional password for protected PDFs

    Returns:
        { "transactions": [ {...}, ... ] }
    
    Each transaction dict has:
        date, narration, transaction_type (DEBIT/CREDIT),
        withdrawal_amt, deposit_amt, closing_balance, month, page_number
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    print(f"[Parser] Detecting PDF type for: {Path(pdf_path).name}")

    try:
        is_image = _is_image_based_pdf(pdf_path, password)
    except Exception as e:
        print(f"[Parser] Could not detect PDF type ({e}), assuming text-based")
        is_image = False

    if is_image:
        if not OCR_AVAILABLE:
            raise RuntimeError(
                "Image-based PDF detected, but OCR dependencies are missing. "
                "Install pdf2image, pytesseract, and the Tesseract binary."
            )

        try:
            import subprocess
            subprocess.run(['tesseract', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "Image-based PDF detected, but Tesseract OCR is not installed or not available in PATH. "
                "Install Tesseract and restart the backend."
            )

        print("[Parser] Image-based PDF detected → using OCR")
        transactions = _extract_via_ocr(pdf_path, password)
    else:
        print("[Parser] Text-based PDF detected → using pdfplumber")
        transactions = _extract_via_pdfplumber(pdf_path, password)

    # Filter out garbage (zero amount + unknown type)
    transactions = [
        t for t in transactions
        if not (
            t["transaction_type"] == "UNKNOWN"
            and t["withdrawal_amt"] == 0.0
            and t["deposit_amt"] == 0.0
        )
    ]

    print(f"[Parser] Final transaction count: {len(transactions)}")
    return {"transactions": transactions}


# ═══════════════════════════════════════════════════════════════════════════════
# CLI TEST — run directly: python pdf_parser.py statement.pdf
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_parser.py <pdf_path> [password]")
        sys.exit(1)

    pdf_file = sys.argv[1]
    pdf_pass = sys.argv[2] if len(sys.argv) > 2 else None

    result = extract_bank_statement(pdf_file, pdf_pass)
    transactions = result["transactions"]

    print(f"\n{'='*60}")
    print(f"TOTAL TRANSACTIONS: {len(transactions)}")
    print(f"{'='*60}")

    for i, t in enumerate(transactions):
        txn_type = t["transaction_type"]
        amount   = t["deposit_amt"] if txn_type == "CREDIT" else t["withdrawal_amt"]
        sign     = "+" if txn_type == "CREDIT" else "-"
        print(f"{i+1:3d}. [{t['date']}] {sign}₹{amount:>10.2f}  Bal:{t['closing_balance']:>10.2f}  {t['narration'][:50]}")

    # Save to JSON
    out_path = "output_transactions.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved to {out_path}")
