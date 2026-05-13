"""
tests/test_agent.py — Unit tests for models, data loading, and escalation logic.

Run:  pytest tests/ -v
"""

from __future__ import annotations
import csv
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from models import FollowUpStage, GeneratedEmail, InvoiceRecord


# ─────────────────────────────────────────────────────────────────────────────
# InvoiceRecord tests
# ─────────────────────────────────────────────────────────────────────────────

def make_record(**kwargs) -> InvoiceRecord:
    defaults = dict(
        invoice_no="INV-TEST-001",
        client_name="Test Client",
        amount=10000.0,
        due_date=date.today() - timedelta(days=5),
        contact_email="test@client.in",
        follow_up_count=0,
        payment_link="https://pay.example.com/INV-TEST-001",
        days_overdue=5,
    )
    defaults.update(kwargs)
    return InvoiceRecord(**defaults)


def test_stage_1():
    r = make_record(days_overdue=5)
    assert r.stage == FollowUpStage.STAGE_1

def test_stage_2():
    r = make_record(days_overdue=10)
    assert r.stage == FollowUpStage.STAGE_2

def test_stage_3():
    r = make_record(days_overdue=18)
    assert r.stage == FollowUpStage.STAGE_3

def test_stage_4():
    r = make_record(days_overdue=25)
    assert r.stage == FollowUpStage.STAGE_4

def test_legal_stage():
    r = make_record(days_overdue=35)
    assert r.stage == FollowUpStage.LEGAL

def test_formatted_amount_inr():
    r = make_record(amount=45000, currency="INR")
    assert "₹" in r.formatted_amount
    assert "45,000" in r.formatted_amount

def test_invalid_amount():
    with pytest.raises(Exception):
        make_record(amount=-100)

def test_invalid_email():
    with pytest.raises(Exception):
        make_record(contact_email="not-an-email")

def test_injection_in_email():
    with pytest.raises(Exception):
        make_record(contact_email="bad{{inject}}@x.com")


# ─────────────────────────────────────────────────────────────────────────────
# GeneratedEmail tests
# ─────────────────────────────────────────────────────────────────────────────

def make_email(**kwargs) -> GeneratedEmail:
    defaults = dict(
        invoice_no="INV-TEST-001",
        client_name="Test Client",
        contact_email="test@client.in",
        subject="Reminder – INV-TEST-001",
        body="Dear Test, please pay INV-TEST-001 of ₹10,000. Link: https://pay.example.com",
        stage=FollowUpStage.STAGE_1,
        tone="Warm & Friendly",
        days_overdue=5,
        amount="₹10,000.00",
        payment_link="https://pay.example.com/INV-TEST-001",
    )
    defaults.update(kwargs)
    return GeneratedEmail(**defaults)


def test_email_valid():
    e = make_email()
    assert e.invoice_no == "INV-TEST-001"

def test_email_missing_invoice_in_body():
    """Hallucination guard: body must contain the invoice number."""
    with pytest.raises(Exception, match="does not mention invoice"):
        make_email(body="Please pay your outstanding invoice. Thanks.")

def test_email_empty_subject():
    with pytest.raises(Exception):
        make_email(subject="   ")


# ─────────────────────────────────────────────────────────────────────────────
# Data agent tests
# ─────────────────────────────────────────────────────────────────────────────

def test_load_csv():
    from agents.data_agent import load_invoices

    today = date.today()
    due_10 = (today - timedelta(days=10)).isoformat()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "invoice_no","client_name","amount","currency",
            "due_date","contact_email","follow_up_count","payment_link"
        ])
        writer.writeheader()
        writer.writerow(dict(
            invoice_no="INV-T-001", client_name="Alpha Corp",
            amount=50000, currency="INR", due_date=due_10,
            contact_email="alpha@corp.in", follow_up_count=1,
            payment_link="https://pay.example.com/INV-T-001"
        ))
        tmppath = f.name

    records = load_invoices(tmppath)
    assert len(records) == 1
    assert records[0].invoice_no == "INV-T-001"
    assert records[0].days_overdue == 10
    assert records[0].stage == FollowUpStage.STAGE_2

def test_load_missing_file():
    from agents.data_agent import load_invoices
    with pytest.raises(FileNotFoundError):
        load_invoices("non_existent.csv")
