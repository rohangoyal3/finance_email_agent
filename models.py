"""
models.py — Pydantic data models for structured, validated agent outputs.
Using Pydantic ensures the LLM cannot hallucinate malformed fields and
every email is fully populated before dispatch (security + correctness).
"""

from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator, model_validator


class FollowUpStage(str, Enum):
    STAGE_1 = "stage_1"   
    STAGE_2 = "stage_2"   
    STAGE_3 = "stage_3"   
    STAGE_4 = "stage_4"   
    LEGAL   = "legal"     


class SendStatus(str, Enum):
    QUEUED  = "queued"
    SENT    = "sent"
    FAILED  = "failed"
    DRY_RUN = "dry_run"
    LEGAL   = "legal_escalation"


class InvoiceRecord(BaseModel):
    """Represents one row from the data source (CSV / Excel / DB)."""
    invoice_no:    str
    client_name:   str
    amount:        float
    currency:      str = "INR"
    due_date:      date
    contact_email: str         
    follow_up_count: int
    payment_link:  str
    days_overdue:  int = 0      

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be positive")
        return v

    @field_validator("follow_up_count")
    @classmethod
    def followup_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("follow_up_count cannot be negative")
        return v

    @field_validator("contact_email")
    @classmethod
    def sanitise_email(cls, v: str) -> str:
        """
        Basic sanitisation — strip whitespace and lower-case.
        Prevents prompt-injection via crafted email fields.
        """
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError(f"Invalid email address: {v!r}")
        for danger in ["{{", "}}", "<script", "javascript:", "\n", "\r"]:
            if danger in v:
                raise ValueError(f"Suspicious content in email field: {v!r}")
        return v

    @property
    def stage(self) -> FollowUpStage:
        d = self.days_overdue
        if d <= 7:  return FollowUpStage.STAGE_1
        if d <= 14: return FollowUpStage.STAGE_2
        if d <= 21: return FollowUpStage.STAGE_3
        if d <= 30: return FollowUpStage.STAGE_4
        return FollowUpStage.LEGAL

    @property
    def formatted_amount(self) -> str:
        symbol = {"INR": "₹", "USD": "$", "EUR": "€"}.get(self.currency, self.currency)
        return f"{symbol}{self.amount:,.2f}"


class GeneratedEmail(BaseModel):
    """
    Structured output from the LLM.  Every field is required — the LLM
    cannot skip population; missing fields raise a ValidationError before
    anything is sent, implementing the hallucination-mitigation strategy.
    """
    invoice_no:    str
    client_name:   str
    contact_email: str
    subject:       str
    body:          str
    stage:         FollowUpStage
    tone:          str
    days_overdue:  int
    amount:        str          
    payment_link:  str

    @field_validator("subject", "body")
    @classmethod
    def no_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("LLM returned an empty subject or body")
        return v

    @field_validator("body")
    @classmethod
    def must_contain_invoice(cls, v: str, info) -> str:
        """Hallucination guard: body must reference the invoice number."""
        return v

    @model_validator(mode="after")
    def body_references_invoice(self) -> "GeneratedEmail":
        if self.invoice_no not in self.body:
            raise ValueError(
                f"LLM body does not mention invoice {self.invoice_no!r} — "
                "possible hallucination; email rejected."
            )
        return self


class AuditEntry(BaseModel):
    """One immutable log record written to the JSONL audit trail."""
    timestamp:    datetime
    invoice_no:   str
    client_name:  str
    contact_email: str
    stage:        FollowUpStage
    tone:         str
    subject:      str
    send_status:  SendStatus
    dry_run:      bool
    error:        Optional[str] = None
