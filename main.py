from __future__ import annotations
import argparse
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

from agents.data_agent import load_invoices
from agents.email_agent import generate_email
from agents.send_agent import dispatch, flag_for_legal
from models import FollowUpStage, SendStatus


def run(data_path: str, dry_run: bool) -> None:
    audit_log  = Path(os.environ.get("AUDIT_LOG",        "output/logs/audit.jsonl"))
    output_dir = Path(os.environ.get("EMAIL_OUTPUT_DIR", "output/emails"))

    logger.info("═" * 60)
    logger.info("Finance Credit Follow-Up Email Agent")
    logger.info("Mode: %s", "DRY RUN ⚠️" if dry_run else "LIVE SEND 🚀")
    logger.info("Data: %s", data_path)
    logger.info("═" * 60)

    records = load_invoices(data_path)
    if not records:
        logger.info("No overdue invoices found. Exiting.")
        return

    stats = {s: 0 for s in ["generated", "sent", "dry_run", "legal", "failed"]}

    for record in records:
        logger.info("Processing %s | %s | %d days overdue | stage=%s",
                    record.invoice_no, record.client_name,
                    record.days_overdue, record.stage.value)

        if record.stage == FollowUpStage.LEGAL:
            flag_for_legal(record, audit_log)
            stats["legal"] += 1
            continue

        try:
            email = generate_email(record)
            if email is None:
                continue

            stats["generated"] += 1
            status = dispatch(email, audit_log, output_dir, dry_run=dry_run)

            if status == SendStatus.SENT:
                stats["sent"] += 1
            elif status == SendStatus.DRY_RUN:
                stats["dry_run"] += 1
            elif status == SendStatus.FAILED:
                stats["failed"] += 1

        except Exception as exc:
            logger.error("Unhandled error for %s: %s", record.invoice_no, exc)
            stats["failed"] += 1

    logger.info("═" * 60)
    logger.info("Run complete.")
    logger.info("  Invoices processed : %d", len(records))
    logger.info("  Emails generated   : %d", stats["generated"])
    logger.info("  Emails sent        : %d", stats["sent"])
    logger.info("  Dry-run logged     : %d", stats["dry_run"])
    logger.info("  Legal escalations  : %d", stats["legal"])
    logger.info("  Failures           : %d", stats["failed"])
    logger.info("  Audit log          : %s", audit_log)
    logger.info("  Email files        : %s/", output_dir)
    logger.info("═" * 60)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Finance Credit Follow-Up Email Agent"
    )

    BASE_DIR = Path(__file__).resolve().parent

    DEFAULT_DATA = BASE_DIR / "data" / "invoices.csv"

    parser.add_argument(
        "--data",
        default=str(DEFAULT_DATA)
    )

    args = parser.parse_args()

    dry_run = os.environ.get(
        "DRY_RUN",
        "true"
    ).lower() not in {"false", "0", "no"}

    run(
        data_path=args.data,
        dry_run=dry_run
    )