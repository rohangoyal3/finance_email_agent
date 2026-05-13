"""
agents/email_agent.py — Uses Claude (via Anthropic SDK) to generate
personalised follow-up emails for each overdue invoice.

Architecture
────────────
• ReAct-style single-agent: system prompt sets strict JSON output schema,
  user prompt injects only sanitised, validated data fields.
• Structured output (JSON mode via Pydantic) eliminates free-form LLM
  hallucination risks before any email is queued.
• PII is passed only as individual typed fields — never as a raw CSV row
  string — reducing prompt injection surface area.

Security mitigations implemented here
──────────────────────────────────────
1. Prompt injection     — input fields are Pydantic-validated before prompt construction;
                          system prompt instructs model to output ONLY JSON.
2. Hallucination guard  — GeneratedEmail.body_references_invoice validator
                          rejects responses that don't mention the invoice number.
3. API key              — loaded from environment via python-dotenv; never hardcoded.
4. PII in logs          — email address is masked in debug logs.
"""

from __future__ import annotations
import json
import logging
import os
import re

import anthropic
from dotenv import load_dotenv

from models import FollowUpStage, GeneratedEmail, InvoiceRecord

load_dotenv()
logger = logging.getLogger(__name__)

_TONE_MAP = {
    FollowUpStage.STAGE_1: "Warm & Friendly",
    FollowUpStage.STAGE_2: "Polite but Firm",
    FollowUpStage.STAGE_3: "Formal & Serious",
    FollowUpStage.STAGE_4: "Stern & Urgent",
    FollowUpStage.LEGAL:   "Escalated — No Email",
}

_SYSTEM_PROMPT = """
You are a professional finance email agent for a B2B company.
Your sole job is to generate a single follow-up email for an overdue invoice
using the data and tone instructions provided.

STRICT RULES:
1. Respond ONLY with a valid JSON object — no preamble, no markdown, no backticks.
2. The JSON must have exactly these keys:
   subject, body
3. The body MUST include: client_name, invoice_no, formatted_amount, due_date,
   days_overdue, and payment_link — all verbatim from the input data.
4. Do NOT invent facts, amounts, dates, or contact details.
5. Do NOT include content unrelated to the payment reminder.
6. Match the tone EXACTLY as instructed.
7. Keep the body under 200 words. Be clear and professional.
""".strip()


def _mask_email(email: str) -> str:
    """Mask PII in log output: rajesh@abc.in → r*****@abc.in"""
    parts = email.split("@")
    if len(parts) != 2:
        return "****"
    return parts[0][0] + "*****@" + parts[1]


def generate_email(record: InvoiceRecord) -> GeneratedEmail | None:
    """
    Call the LLM to generate a follow-up email for one invoice.

    Returns None for legal-escalation records (no email sent).
    Returns a validated GeneratedEmail or raises on persistent failure.
    """
    if record.stage == FollowUpStage.LEGAL:
        logger.info("%s: legal escalation — skipping email generation.", record.invoice_no)
        return None

    tone = _TONE_MAP[record.stage]

    user_prompt = f"""
Generate a follow-up email using EXACTLY this data:

invoice_no:     {record.invoice_no}
client_name:    {record.client_name}
formatted_amount: {record.formatted_amount}
due_date:       {record.due_date.isoformat()}
days_overdue:   {record.days_overdue}
payment_link:   {record.payment_link}
contact_email:  {record.contact_email}
follow_up_number: {record.follow_up_count + 1}

Tone instruction: {tone}
Stage: {record.stage.value}

Return ONLY the JSON object with keys: subject, body
""".strip()

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model  = os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")

    for attempt in range(1, 4):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=600,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = response.content[0].text.strip()

            # Strip any accidental markdown fences
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

            data = json.loads(raw)
            email = GeneratedEmail(
                invoice_no=record.invoice_no,
                client_name=record.client_name,
                contact_email=record.contact_email,
                subject=data["subject"],
                body=data["body"],
                stage=record.stage,
                tone=tone,
                days_overdue=record.days_overdue,
                amount=record.formatted_amount,
                payment_link=record.payment_link,
            )
            logger.info(
                "%s: email generated for %s (stage=%s, attempt=%d)",
                record.invoice_no, _mask_email(record.contact_email), record.stage.value, attempt
            )
            return email

        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("%s: attempt %d failed — %s", record.invoice_no, attempt, exc)
            if attempt == 3:
                raise RuntimeError(
                    f"Failed to generate valid email for {record.invoice_no} after 3 attempts."
                ) from exc

    return None  # unreachable but satisfies type checker
