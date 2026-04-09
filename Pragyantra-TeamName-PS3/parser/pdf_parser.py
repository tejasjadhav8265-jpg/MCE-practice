import pdfplumber
import re
import json
from pathlib import Path


def open_pdf(pdf_path: str, password: str = None):
    try:
        if password:
            return pdfplumber.open(pdf_path, password=password)
        return pdfplumber.open(pdf_path)
    except Exception as e:
        raise ValueError(f"Could not open PDF. Wrong password or corrupt file.\nError: {e}")


def clean_cell(cell) -> str:
    if cell is None:
        return ""
    return str(cell).strip()


def is_transaction_row(row: list) -> bool:
    if not row or not row[0]:
        return False
    return bool(re.match(r"^\d{2}/\d{2}/\d{2}$", clean_cell(row[0])))


def is_continuation_row(row: list) -> bool:
    if not row:
        return False
    col0 = clean_cell(row[0])
    col1 = clean_cell(row[1]) if len(row) > 1 else ""
    return col0 == "" and col1 != ""


def merge_multiline_rows(raw_rows: list) -> list:
    merged = []
    for row in raw_rows:
        first = clean_cell(row[0]).lower() if row else ""
        if first in ("date", ""):
            if not is_transaction_row(row):
                continue
        if is_transaction_row(row):
            merged.append([clean_cell(c) for c in row])
        elif is_continuation_row(row) and merged:
            extra = clean_cell(row[1]) if len(row) > 1 else ""
            if extra:
                merged[-1][1] = merged[-1][1] + " " + extra
    return merged


def parse_amount(value: str) -> float:
    if not value or value.strip() == "":
        return 0.0
    try:
        return float(value.replace(",", "").strip())
    except ValueError:
        return 0.0


def extract_transactions_from_page(page, page_num: int) -> list[dict]:
    transactions = []

    table_settings = {
        "vertical_strategy":   "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance":      5,
        "join_tolerance":      5,
        "edge_min_length":     10,
    }

    tables = page.extract_tables(table_settings)

    if not tables:
        table_settings["vertical_strategy"]   = "text"
        table_settings["horizontal_strategy"] = "text"
        tables = page.extract_tables(table_settings)

    for table in tables:
        if not table:
            continue

        merged_rows = merge_multiline_rows(table)

        for row in merged_rows:
            while len(row) < 7:
                row.append("")

            withdrawal_amt  = parse_amount(row[4])
            deposit_amt     = parse_amount(row[5])
            closing_balance = parse_amount(row[6])

            if withdrawal_amt > 0:
                txn_type = "DEBIT"
            elif deposit_amt > 0:
                txn_type = "CREDIT"
            else:
                txn_type = "UNKNOWN"

            transactions.append({
                "date":             row[0],
                "narration":        re.sub(r"\s+", " ", row[1]).strip(),
                "chq_ref_no":       row[2],
                "value_date":       row[3],
                "withdrawal_amt":   withdrawal_amt,
                "deposit_amt":      deposit_amt,
                "closing_balance":  closing_balance,
                "transaction_type": txn_type,
                "page_number":      page_num,
            })

    return transactions


def extract_bank_statement(pdf_path: str, password: str = None) -> dict:
    pdf_path = str(pdf_path)
    all_transactions = []

    pdf = open_pdf(pdf_path, password)

    try:
        for page_num, page in enumerate(pdf.pages):
            page_txns = extract_transactions_from_page(page, page_num + 1)
            all_transactions.extend(page_txns)
    finally:
        pdf.close()

    return {"transactions": all_transactions}


def save_to_json(data: dict, output_path: str):
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"JSON saved -> {output_path}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_parser.py <path_to_pdf> [password]")
        sys.exit(1)

    pdf_file = sys.argv[1]
    pdf_pass = sys.argv[2] if len(sys.argv) > 2 else None

    result = extract_bank_statement(pdf_file, pdf_pass)
    save_to_json(result, "output.json")
    print(f"Total transactions extracted: {len(result['transactions'])}")



#  How Tejas calls it from routes/api.py:
# pythonfrom parser.pdf_parser import extract_bank_statement

# result = extract_bank_statement("statement.pdf", password="userpassword")
# transactions = result["transactions"]
