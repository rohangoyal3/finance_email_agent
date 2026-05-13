# finance_email_agent
# 💼 Finance Credit Follow-Up Email Agent

> **AI Enablement Internship — Task 2**
> An intelligent AI agent that automates overdue invoice follow-ups with tone-escalating emails, built with Claude AI and Python.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![Claude](https://img.shields.io/badge/LLM-Claude%20Sonnet%204-orange?logo=anthropic)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-red?logo=streamlit)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 📌 Project Overview

Finance teams spend significant time chasing overdue payments. Manual follow-ups are inconsistent in tone and timing. This AI agent solves that by:

- Automatically reading overdue invoice records from CSV/Excel
- Classifying each invoice into an escalation stage based on days overdue
- Calling **Claude AI** to generate a personalised, professional email at the correct tone
- Dispatching (or dry-running) the email via SMTP
- Writing an immutable **audit log** for every action taken
- Flagging records beyond 30 days for **legal review** — no auto-email sent

---

## 🎥 Demo

> Run the Streamlit dashboard to see the agent in action:

```bash
"d:\Python 3114\python.exe" -m streamlit run dashboard.py
```

---

## 🗂️ Project Structure

```
finance_email_agent/
├── main.py                  # Orchestrator — runs the full pipeline
├── dashboard.py             # Streamlit UI dashboard
├── models.py                # Pydantic data models (structured output)
├── agents/
│   ├── data_agent.py        # CSV/Excel ingestion + validation
│   ├── email_agent.py       # Claude API email generation
│   └── send_agent.py        # SMTP dispatch + audit logging
├── data/
│   └── invoices.csv         # Sample invoice data
├── output/
│   ├── emails/              # Generated email .txt files
│   │   ├── INV-2024-001_stage1.txt
│   │   └── INV-2024-003_stage3.txt
│   └── logs/
│       └── audit.jsonl      # Immutable audit trail
├── tests/
│   └── test_agent.py        # pytest unit tests
├── .env.example             # Environment variable template
├── .gitignore
├── requirements.txt
└── README.md
```

---

## ⚙️ Agent Architecture

```
CSV / Excel
     │
     ▼
┌─────────────────────┐
│     DataAgent       │  Reads & validates all invoice records
│  data_agent.py      │  Computes days_overdue from today's date
└────────┬────────────┘
         │ (per overdue record)
         ▼
┌─────────────────────┐
│     EmailAgent      │  Classifies stage (1–4 or Legal)
│  email_agent.py     │  Calls Claude API with sanitised prompt
│                     │  Validates structured JSON response
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│     SendAgent       │  DRY_RUN → saves .txt + logs audit
│  send_agent.py      │  LIVE    → SMTP dispatch + logs audit
└────────┬────────────┘
         │
         ▼
   audit.jsonl  +  output/emails/
```

**Architecture pattern:** Plan-and-Execute — the orchestrator pre-plans the full pipeline then executes each stage deterministically for a batch workflow.

---

## 📊 Tone Escalation Matrix

| Stage | Days Overdue | Tone | Key Message | CTA |
|-------|-------------|------|-------------|-----|
| Stage 1 | 1–7 days | 🟢 Warm & Friendly | Gentle reminder, assume oversight | Pay now link |
| Stage 2 | 8–14 days | 🔵 Polite but Firm | Payment still pending | Confirm payment date |
| Stage 3 | 15–21 days | 🟡 Formal & Serious | Escalating concern, mention impact | Respond within 48 hrs |
| Stage 4 | 22–30 days | 🔴 Stern & Urgent | Final reminder before escalation | Pay immediately |
| Legal Flag | 30+ days | ⚫ Escalated | Human review required — no auto email | Assign to manager |

---

## 🛠️ Tech Stack & Decision Log

### LLM: Claude Sonnet 4 (Anthropic)

| Factor | Decision |
|--------|----------|
| **Model** | `claude-sonnet-4-20250514` |
| **Why Claude over GPT-4o** | Superior instruction-following for strict JSON output; 200K context window handles large invoice batches; competitive cost for high-volume generation |
| **Why Sonnet over Opus** | Sufficient capability for structured email generation at lower cost and higher speed |
| **Output mode** | JSON-only via strict system prompt + Pydantic validation |

### Agent Framework: Direct Anthropic SDK + Custom Orchestration

| Factor | Decision |
|--------|----------|
| **Why not LangChain/CrewAI** | Pipeline is linear — a full framework adds overhead without benefit for this deterministic batch flow |
| **Why direct SDK** | Full control over retry logic, prompt construction, and output validation |
| **Observability** | LangSmith tracing ready via `LANGCHAIN_TRACING_V2=true` env var |

### Other Libraries

| Layer | Choice | Reason |
|-------|--------|--------|
| Data ingestion | `pandas` | Handles CSV + Excel uniformly |
| Validation | `pydantic` | Structured output + hallucination guard |
| Email dispatch | `smtplib` | Built-in, no extra dependency for SMTP |
| UI | `streamlit` | Rapid dashboard with minimal boilerplate |
| Testing | `pytest` | Industry standard, clean fixtures |

---

## 🔐 Security Mitigations

| Risk | Mitigation Implemented |
|------|----------------------|
| **Prompt Injection** | All CSV fields pass Pydantic validators before reaching the LLM prompt. `sanitise_email()` blocks `{{`, `}}`, `<script`, newlines, and `javascript:` patterns. System prompt enforces JSON-only output. |
| **Data Privacy / PII** | Email addresses masked in all debug logs (`r*****@domain.com`). PII injected as individual typed fields — never as raw CSV strings. `DRY_RUN=true` default prevents PII transmission over network during development. |
| **API Key Exposure** | Loaded via `python-dotenv` from `.env` file. Never hardcoded anywhere. `.env` listed in `.gitignore`. Use AWS Secrets Manager / GCP Secret Manager in production. |
| **Hallucination Risk** | `GeneratedEmail.body_references_invoice` Pydantic model validator rejects any LLM response that doesn't contain the correct invoice number. 3-attempt retry with fresh prompt on failure. |
| **Unauthorised Access** | `API_SECRET_KEY` env var for endpoint protection. Rate limiting via `RATE_LIMIT_PER_MINUTE`. Add OAuth2/JWT middleware for production deployment. |
| **Email Spoofing** | SPF/DKIM/DMARC must be configured on the sending domain. Verified sender via `SENDER_EMAIL` env var. Dry-run mode prevents spoofed sends during testing. |
| **Escalation Cap** | After 30+ days overdue, agent flags for legal instead of sending — prevents automated contact during potential legal proceedings. |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Anthropic API key ([get one here](https://console.anthropic.com))

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/finance-email-agent.git
cd finance-email-agent

# 2. Install dependencies
python -m pip install anthropic langchain langchain-anthropic pandas python-dotenv pydantic jinja2 streamlit openpyxl

# 3. Set up environment variables
cp .env.example .env
# Open .env and add your ANTHROPIC_API_KEY

# 4. Run the agent (dry-run by default — no real emails sent)
python main.py

# 5. Launch the Streamlit dashboard
python -m streamlit run dashboard.py

# 6. Run tests
python -m pytest tests/ -v
```

### Windows (if Python path has spaces)
```cmd
"d:\Python 3114\python.exe" main.py
"d:\Python 3114\python.exe" -m streamlit run dashboard.py
```

---

## 📋 Environment Variables

Copy `.env.example` to `.env` and fill in:

```env
# Required
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxx
LLM_MODEL=claude-sonnet-4-20250514

# Email (only needed for live send)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SENDER_NAME=Finance Team
SENDER_EMAIL=finance@yourcompany.com

# Agent config
DRY_RUN=true          # Change to false for live sending
DATA_SOURCE=data/invoices.csv
AUDIT_LOG=output/logs/audit.jsonl
EMAIL_OUTPUT_DIR=output/emails
```

---

## 📝 Prompt Design

### System Prompt Strategy
The system prompt enforces:
1. Output **ONLY valid JSON** with keys `subject` and `body` — no markdown, no preamble
2. All invoice fields must appear **verbatim** in the body
3. Tone is specified explicitly per invocation
4. Body capped at **200 words**

### Prompt Iteration Log
| Version | Issue | Fix |
|---------|-------|-----|
| v1 | LLM added "Best regards, AI Assistant" hallucinations | Added strict field requirement |
| v2 | LLM wrapped output in markdown fences | Added `re.sub` to strip fences |
| v3 (current) | Occasional invoice number omission | Added Pydantic body validator as hard gate |

---

## 📧 Sample Output

### Stage 1 — Warm & Friendly
```
Subject: Quick Reminder – INV-2024-001 | ₹45,000.00 Due

Hi Rajesh,

I hope you're doing well! This is a friendly reminder that Invoice
INV-2024-001 for ₹45,000.00 was due on 09 May 2026.

If you have already processed this, please disregard. Otherwise,
complete the payment here: https://pay.example.com/INV-2024-001

Thank you!
Finance Team
```

### Stage 3 — Formal & Serious
```
Subject: IMPORTANT: Outstanding Payment – INV-2024-003 (15 Days Overdue)

Dear Karan Singh,

Despite our previous reminders, INV-2024-003 for ₹31,500.00 remains
unpaid — now 15 days overdue. Continued non-payment may impact your
credit terms. Please respond within 48 hours:

https://pay.example.com/INV-2024-003

Finance & Credit Team
```

### Stage 4 — Stern & Urgent
```
Subject: FINAL NOTICE – INV-2024-005 – Immediate Action Required

Dear Ramesh Patel,

This is our final reminder. INV-2024-005 for ₹19,900.00 is now 23
days overdue. Failure to remit within 24 hours will result in
escalation to our legal and recovery team.

Pay immediately: https://pay.example.com/INV-2024-005

Finance & Credit Control
```

---

## 📊 Audit Log Format

Every action is logged to `output/logs/audit.jsonl` as a JSON line:

```json
{
  "timestamp": "2026-05-14T09:00:04+00:00",
  "invoice_no": "INV-2024-003",
  "client_name": "Karan Singh",
  "contact_email": "karan@ghisolutions.in",
  "stage": "stage_3",
  "tone": "Formal & Serious",
  "subject": "IMPORTANT: Outstanding Payment – INV-2024-003 (15 Days Overdue)",
  "send_status": "dry_run",
  "dry_run": true,
  "error": null
}
```

---

## ✅ Deliverables Checklist

- [x] GitHub Repository with all source code
- [x] `.env.example` — API keys never committed
- [x] `requirements.txt`
- [x] `README.md` with architecture, LLM rationale, security mitigations
- [x] Sample output — `output/emails/` and `output/logs/audit.jsonl`
- [x] Streamlit dashboard (`dashboard.py`)
- [x] Dry-run / sandbox mode (`DRY_RUN=true` default)
- [x] All 5 escalation stages implemented
- [x] Legal escalation cap (30+ days → no auto-email, flagged for review)
- [x] Hallucination mitigation via Pydantic validators
- [x] Unit tests (`pytest tests/`)
- [x] Mandatory security documentation

---

## 🧪 Running Tests

```bash
python -m pytest tests/ -v
```

Tests cover:
- All 5 escalation stage classifications
- Pydantic validation for invalid amounts and emails
- Prompt injection detection in email fields
- Hallucination guard (invoice number in body)
- CSV loading and days_overdue computation

---

## 📈 Future Improvements

- [ ] Scheduling via APScheduler or GitHub Actions cron
- [ ] SendGrid / Mailgun integration as SMTP alternative
- [ ] LangSmith tracing for full observability
- [ ] Google Sheets as data source
- [ ] Multi-currency support with live FX rates
- [ ] WhatsApp / SMS fallback for unresponsive clients

---

## 👤 Author

**[Your Name]**
AI Enablement Internship — Task 2
May 2026

---

## 📄 License

MIT License — free to use and modify with attribution.
