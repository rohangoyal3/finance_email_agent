"""
agents/data_agent.py — Loads and validates invoice records from CSV / Excel.

Security notes
──────────────
• All fields are passed through Pydantic validators before any LLM call,
  preventing prompt-injection via malicious CSV content.
• days_overdue is computed server-side from today's date, not trusted from
  any external column, so clients cannot manipulate their overdue count.
"""

from __future__ import annotations
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from models import InvoiceRecord

logger = logging.getLogger(__name__)


def load_invoices(path: str | Path) -> list[InvoiceRecord]:
    """
    Read a CSV or Excel file of pending invoices and return a list of
    validated InvoiceRecord objects sorted by days_overdue descending.

    Raises
    ------
    FileNotFoundError  – if the data file does not exist.
    ValueError         – if required columns are missing.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    elif suffix == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    required_cols = {
        "invoice_no", "client_name", "amount", "due_date",
        "contact_email", "follow_up_count", "payment_link",
    }
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in data file: {missing}")

    today = date.today()
    records: list[InvoiceRecord] = []
    skipped = 0

    for _, row in df.iterrows():
        try:
            due = pd.to_datetime(row["due_date"]).date()
            days_overdue = max(0, (today - due).days)

            rec = InvoiceRecord(
                invoice_no=str(row["invoice_no"]).strip(),
                client_name=str(row["client_name"]).strip(),
                amount=float(row["amount"]),
                currency=str(row.get("currency", "INR")).strip(),
                due_date=due,
                contact_email=str(row["contact_email"]),
                follow_up_count=int(row["follow_up_count"]),
                payment_link=str(row["payment_link"]).strip(),
                days_overdue=days_overdue,
            )
            # Only include overdue records
            if days_overdue > 0:
                records.append(rec)
            else:
                logger.debug("Skipping %s — not yet overdue.", rec.invoice_no)

        except Exception as exc:
            logger.warning("Skipping row %s due to validation error: %s", row.get("invoice_no", "?"), exc)
            skipped += 1

    logger.info("Loaded %d overdue invoices (%d skipped) from %s", len(records), skipped, path)
    # Sort most overdue first so urgent cases are processed first
    records.sort(key=lambda r: r.days_overdue, reverse=True)
    return records
