"""
agents/send_agent.py — Dispatches generated emails via SMTP or logs them
in dry-run mode. Every action is written to the immutable JSONL audit trail.

Security notes
──────────────
• SMTP credentials loaded from environment — never passed as arguments.
• DRY_RUN=true (default) prevents accidental sends during development.
• Audit trail is append-only (mode="a"); records are never deleted.
• Email content is written to disk as .txt files for the sample output
  deliverable required by the submission brief.
"""

from __future__ import annotations
import json
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

from models import AuditEntry, FollowUpStage, GeneratedEmail, InvoiceRecord, SendStatus

load_dotenv()
logger = logging.getLogger(__name__)


def _write_audit(entry: AuditEntry, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry.model_dump_json() + "\n")


def _save_email_file(email: GeneratedEmail, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fname = output_dir / f"{email.invoice_no}_stage{email.stage.value[-1]}.txt"
    content = (
        f"To: {email.contact_email}\n"
        f"Subject: {email.subject}\n"
        f"Stage: {email.stage.value} | Tone: {email.tone}\n"
        f"Days Overdue: {email.days_overdue}\n"
        f"{'─' * 60}\n\n"
        f"{email.body}\n"
    )
    fname.write_text(content, encoding="utf-8")
    logger.debug("Email saved: %s", fname)


def dispatch(
    email: GeneratedEmail,
    audit_log: Path,
    output_dir: Path,
    dry_run: bool = True,
) -> SendStatus:
    """
    Send or simulate sending a generated email.

    Parameters
    ----------
    email      : validated GeneratedEmail from the LLM agent
    audit_log  : path to the JSONL audit trail file
    output_dir : directory for saved email text files
    dry_run    : if True, log only — do not actually connect to SMTP

    Returns
    -------
    SendStatus enum value
    """
    status   = SendStatus.DRY_RUN if dry_run else SendStatus.SENT
    error_msg: str | None = None

    if not dry_run:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = email.subject
            msg["From"]    = f"{os.environ.get('SENDER_NAME', 'Finance Team')} <{os.environ.get('SENDER_EMAIL')}>"
            msg["To"]      = email.contact_email

            msg.attach(MIMEText(email.body, "plain"))

            with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])) as server:
                server.ehlo()
                server.starttls()
                server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                server.sendmail(
                    os.environ["SMTP_USER"],
                    [email.contact_email],
                    msg.as_string(),
                )
            logger.info("SMTP: sent %s to %s", email.invoice_no, email.contact_email)

        except smtplib.SMTPException as exc:
            status    = SendStatus.FAILED
            error_msg = str(exc)
            logger.error("SMTP error for %s: %s", email.invoice_no, exc)
    else:
        logger.info("DRY RUN: would send %s to %s", email.invoice_no, email.contact_email)

    # Persist email file regardless of dry-run
    _save_email_file(email, output_dir)

    # Write immutable audit entry
    entry = AuditEntry(
        timestamp=datetime.now(timezone.utc),
        invoice_no=email.invoice_no,
        client_name=email.client_name,
        contact_email=email.contact_email,
        stage=email.stage,
        tone=email.tone,
        subject=email.subject,
        send_status=status,
        dry_run=dry_run,
        error=error_msg,
    )
    _write_audit(entry, audit_log)
    return status


def flag_for_legal(record: InvoiceRecord, audit_log: Path) -> None:
    """Write a legal-escalation audit record; no email is generated."""
    entry = AuditEntry(
        timestamp=datetime.now(timezone.utc),
        invoice_no=record.invoice_no,
        client_name=record.client_name,
        contact_email=record.contact_email,
        stage=FollowUpStage.LEGAL,
        tone="Escalated",
        subject="[LEGAL ESCALATION — no email sent]",
        send_status=SendStatus.LEGAL,
        dry_run=False,
    )
    _write_audit(entry, audit_log)
    logger.warning(
        "LEGAL ESCALATION: %s (%s) — %d days overdue. Flagged for manual review.",
        record.invoice_no, record.client_name, record.days_overdue,
    )
