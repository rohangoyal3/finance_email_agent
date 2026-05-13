# Finance Credit Follow-Up Email Agent

> **AI Enablement Internship — Task 2**  
> Automated, escalating follow-up emails for overdue invoices 

## Project Overview

This agent automates the finance team's credit follow-up workflow. It reads overdue invoice records, classifies each by days-overdue into one of four escalation stages, calls Claude to generate a personalised email at the correct tone, dispatches (or dry-runs) the email, and writes an immutable audit log entry for every action.

```
CSV / Excel  →  DataAgent  →  EmailAgent (Claude)  →  SendAgent  →  Audit Log
                  validate      generate email          SMTP / dry-run   JSONL
```

---

## Agent Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                              │
│  Orchestrator — loads env, calls each agent in sequence     │
└────────────────────────┬────────────────────────────────────┘
                         │
        ┌────────────────▼─────────────────┐
        │         DataAgent                │
        │  • Reads CSV / Excel             │
        │  • Pydantic validates all fields │
        │  • Computes days_overdue         │
        │  • Returns sorted InvoiceRecords │
        └────────────────┬─────────────────┘
                         │  (per record)
        ┌────────────────▼─────────────────┐
        │         EmailAgent               │
        │  • Classifies stage (1–4/legal)  │
        │  • Builds sanitised prompt       │
        │  • Calls Claude API (JSON mode)  │
        │  • Validates GeneratedEmail      │
        └────────────────┬─────────────────┘
                         │
        ┌────────────────▼─────────────────┐
        │         SendAgent                │
        │  • DRY_RUN: log + save .txt      │
        │  • LIVE: SMTP dispatch           │
        │  • Appends AuditEntry to JSONL   │
        └──────────────────────────────────┘
```

---

## Tone Escalation Matrix

| Stage | Days Overdue | Tone | Key Message | CTA |
|-------|-------------|------|-------------|-----|
| Stage 1 | 1–7 days | Warm & Friendly | Gentle reminder | Pay now link |
| Stage 2 | 8–14 days | Polite but Firm | Payment still pending | Confirm payment date |
| Stage 3 | 15–21 days | Formal & Serious | Escalating concern | Respond within 48 hrs |
| Stage 4 | 22–30 days | Stern & Urgent | Final reminder | Pay immediately |
| Legal Flag | 30+ days | ⚫ Escalated | Human review required | Assign to manager |

---

## Technical Stack & Decision Log

### LLM: Claude claude-sonnet-4-20250514 (Anthropic)

**Why Claude Sonnet 4?**
- 200K token context window — handles large invoice batches without truncation.
- Native JSON mode (structured output) — critical for hallucination mitigation.
- Tool-calling support available for future multi-agent expansion.
- Competitive cost vs. GPT-4o for high-volume email generation tasks.
- Strong instruction-following for strict tone constraints.

### Agent Framework: Direct Anthropic SDK + Custom Orchestration

**Why not LangChain/CrewAI?**
- The pipeline is linear (load → generate → send) — a full agent framework adds overhead without benefit for this flow.
- Direct SDK calls give full control over retry logic, prompt construction, and output validation.
- LangSmith tracing can still be added via the `LANGCHAIN_TRACING_V2` env var for observability (bonus marks).

**Architecture pattern:** Plan-and-Execute — the orchestrator (`main.py`) pre-plans the full pipeline then executes each stage deterministically, rather than a ReAct loop. This is appropriate for a batch workflow where actions are known upfront.

### Prompt Design

**System prompt** enforces:
1. Output ONLY valid JSON (`subject`, `body` keys) — no markdown, no preamble.
2. All data fields from the invoice must appear verbatim in the body.
3. Tone is specified explicitly per invocation.
4. Body length capped at 200 words.

**User prompt** injects only sanitised, Pydantic-validated fields — never raw CSV row strings. This eliminates prompt injection via malicious CSV content.

**Prompt iteration notes:**
- v1: Free-form prompt → LLM added "Best regards, AI Assistant" hallucinations.
- v2: Added JSON schema instruction → eliminated hallucinations but LLM sometimes wrapped in markdown fences. Added `re.sub` to strip fences.
- v3 (current): Strict JSON-only instruction + hallucination guard (invoice number must appear in body) → zero false positives in testing.

---

## Security Mitigations

| Risk | Mitigation Implemented |
|------|----------------------|
| **Prompt Injection** | All input fields pass Pydantic validators before reaching the prompt. `InvoiceRecord.sanitise_email` blocks `{{`, `}}`, `<script`, `javascript:`, newlines. System prompt enforces JSON-only output. |
| **Data Privacy / PII** | Email addresses are masked in all debug logs (`_mask_email`). PII is passed as individual typed fields, not as raw strings. `DRY_RUN=true` by default — no PII sent over network during dev. |
| **API Key Exposure** | Loaded via `python-dotenv` from `.env`. Never hardcoded. `.env` listed in `.gitignore`. Use a secrets manager (AWS Secrets Manager / GCP Secret Manager) in production. |
| **Hallucination Risk** | `GeneratedEmail.body_references_invoice` model validator rejects any LLM response that doesn't include the correct invoice number. 3-attempt retry with exponential backoff. |
| **Unauthorised Access** | Dashboard API protected by `API_SECRET_KEY` env var. Rate limiting via `RATE_LIMIT_PER_MINUTE`. In production: add OAuth2 / JWT middleware. |
| **Email Spoofing** | SPF/DKIM/DMARC must be configured on the sending domain. Verified sender address via `SENDER_EMAIL` env var. `DRY_RUN` mode prevents spoofed sends during testing. |
| **Escalation Cap** | After 30+ days overdue, agent flags for legal instead of sending email — prevents harassment of debtors in legal proceedings. |

---

## File Structure

```
finance_email_agent/
├── main.py                  # Orchestrator
├── dashboard.py             # Streamlit UI
├── models.py                # Pydantic data models
├── agents/
│   ├── data_agent.py        # CSV/Excel ingestion + validation
│   ├── email_agent.py       # Claude API email generation
│   └── send_agent.py        # SMTP dispatch + audit logging
├── data/
│   └── invoices.csv         # Sample invoice data
├── output/
│   ├── emails/              # Generated email .txt files
│   └── logs/audit.jsonl     # Immutable audit trail
├── tests/
│   └── test_agent.py        # pytest unit tests
├── .env.example             # Environment variable template
├── requirements.txt
└── README.md
```

---

## Deliverables Checklist

- [x] GitHub Repository with source code
- [x] `.env.example` (API keys never committed)
- [x] `requirements.txt`
- [x] `README.md` with architecture, LLM choice, security mitigations
- [x] Sample output — `output/emails/` and `output/logs/audit.jsonl`
- [x] Streamlit dashboard (`dashboard.py`)
- [x] Dry-run / sandbox mode (`DRY_RUN=true`)
- [x] Tone escalation matrix implemented (all 5 stages)
- [x] Legal escalation cap (30+ days → no auto-email)
- [x] Hallucination mitigation (Pydantic validators)
- [x] Unit tests (`pytest tests/`)

---

## Pro Tips Applied

- Structured output (Pydantic) from day one — saved hours of debugging.
- DRY_RUN=true default — never accidentally emailed real clients.
- Prompt iterations documented above.
- LangSmith tracing ready via env vars (set `LANGCHAIN_TRACING_V2=true`).
