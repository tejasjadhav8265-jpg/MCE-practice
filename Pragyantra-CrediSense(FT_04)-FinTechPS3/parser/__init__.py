# parser/__init__.py
# FIX: module name was 'pdf_parser' — corrected to match the actual file 'parser.py'
from .parser import extract_bank_statement

__all__ = ["extract_bank_statement"]