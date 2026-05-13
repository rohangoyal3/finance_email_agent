import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Finance Email Agent",
    page_icon="💼",
    layout="wide",
)

try:
    from agents.data_agent import load_invoices
    from agents.email_agent import generate_email
    from agents.send_agent import dispatch, flag_for_legal
    from models import FollowUpStage, SendStatus
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False

DATA_PATH  = Path(os.environ.get("DATA_SOURCE",        "data/invoices.csv"))
AUDIT_LOG  = Path(os.environ.get("AUDIT_LOG",          "output/logs/audit.jsonl"))
EMAIL_DIR  = Path(os.environ.get("EMAIL_OUTPUT_DIR",   "output/emails"))
DRY_RUN    = os.environ.get("DRY_RUN", "true").lower() not in {"false", "0", "no"}

STAGE_COLORS = {
    "stage_1": "🟢",
    "stage_2": "🔵",
    "stage_3": "🟡",
    "stage_4": "🔴",
    "legal":   "⚫",
}
STAGE_LABELS = {
    "stage_1": "Stage 1 — Warm",
    "stage_2": "Stage 2 — Polite",
    "stage_3": "Stage 3 — Formal",
    "stage_4": "Stage 4 — Stern",
    "legal":   "Legal Flag",
}


with st.sidebar:
    st.title("⚙️ Agent Config")
    dry_run_toggle = st.toggle("Dry Run (no real emails)", value=DRY_RUN)
    data_file = st.text_input("Data file path", str(DATA_PATH))
    st.divider()
    st.caption("Model: " + os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514"))
    st.caption("Audit log: " + str(AUDIT_LOG))
    st.caption("Email output: " + str(EMAIL_DIR))

    if not AGENT_AVAILABLE:
        st.warning("Agent modules not found. Install requirements first.")

st.title("💼 Finance Credit Follow-Up Email Agent")
st.caption(f"Today: {date.today().isoformat()}  |  Mode: {'🔶 DRY RUN' if dry_run_toggle else '🚀 LIVE SEND'}")

@st.cache_data(show_spinner="Loading invoice data…")
def get_records(path: str):
    return load_invoices(path) if AGENT_AVAILABLE else []

try:
    records = get_records(data_file)
except Exception as e:
    st.error(f"Failed to load data: {e}")
    records = []

if records:
    total      = len(records)
    legal      = sum(1 for r in records if r.stage == FollowUpStage.LEGAL)
    total_amt  = sum(r.amount for r in records)
    queued     = total - legal

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Invoices",   total)
    c2.metric("Total Overdue",    f"₹{total_amt:,.0f}")
    c3.metric("Emails to Send",   queued)
    c4.metric("Legal Escalations", legal, delta=f"-{legal}" if legal else None, delta_color="inverse")

    st.divider()

    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        stage_filter = st.selectbox(
            "Filter by stage",
            ["All"] + list(STAGE_LABELS.values()),
            index=0,
        )
    with col_f2:
        run_btn = st.button("▶ Run Agent Now", type="primary", disabled=not AGENT_AVAILABLE)

    rows = []
    for r in records:
        sl = STAGE_LABELS[r.stage.value]
        if stage_filter != "All" and sl != stage_filter:
            continue
        rows.append({
            "Invoice":      r.invoice_no,
            "Client":       r.client_name,
            "Amount":       r.formatted_amount,
            "Due Date":     r.due_date.isoformat(),
            "Days Overdue": r.days_overdue,
            "Stage":        STAGE_COLORS[r.stage.value] + " " + sl,
            "Email":        r.contact_email,
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()
    st.subheader("📧 Preview Generated Email")
    inv_options = [r.invoice_no for r in records if r.stage != FollowUpStage.LEGAL]
    if inv_options:
        selected = st.selectbox("Select invoice to preview", inv_options)
        sel_record = next(r for r in records if r.invoice_no == selected)

        if st.button("Generate Preview") and AGENT_AVAILABLE:
            with st.spinner("Calling Claude…"):
                try:
                    email = generate_email(sel_record)
                    if email:
                        st.text_input("Subject", email.subject)
                        st.text_area("Body", email.body, height=260)
                        st.caption(f"Stage: {email.stage.value} | Tone: {email.tone} | Days overdue: {email.days_overdue}")
                        if st.button("Send / Log this email"):
                            status = dispatch(email, AUDIT_LOG, EMAIL_DIR, dry_run=dry_run_toggle)
                            st.success(f"Status: {status.value}")
                except Exception as exc:
                    st.error(str(exc))
    else:
        st.info("No non-escalated invoices to preview.")

    if run_btn and AGENT_AVAILABLE:
        progress = st.progress(0, text="Starting agent…")
        results  = []
        for i, rec in enumerate(records):
            progress.progress((i + 1) / total, text=f"Processing {rec.invoice_no}…")
            if rec.stage == FollowUpStage.LEGAL:
                flag_for_legal(rec, AUDIT_LOG)
                results.append((rec.invoice_no, "⚫ Legal escalated"))
            else:
                try:
                    email = generate_email(rec)
                    if email:
                        status = dispatch(email, AUDIT_LOG, EMAIL_DIR, dry_run=dry_run_toggle)
                        results.append((rec.invoice_no, f"✅ {status.value}"))
                except Exception as exc:
                    results.append((rec.invoice_no, f"❌ {exc}"))
        progress.empty()
        st.success("Agent run complete!")
        st.dataframe(pd.DataFrame(results, columns=["Invoice", "Result"]), hide_index=True)
        st.cache_data.clear()

else:
    st.info("No overdue invoices found or data file not loaded.")

st.divider()
st.subheader("📋 Audit Log")

if AUDIT_LOG.exists():
    lines = AUDIT_LOG.read_text().strip().splitlines()[-50:]  
    entries = []
    for line in lines:
        try:
            e = json.loads(line)
            entries.append({
                "Timestamp":   e.get("timestamp", "")[:19].replace("T", " "),
                "Invoice":     e.get("invoice_no"),
                "Client":      e.get("client_name"),
                "Stage":       e.get("stage"),
                "Status":      e.get("send_status"),
                "Dry Run":     "✓" if e.get("dry_run") else "✗",
                "Error":       e.get("error") or "—",
            })
        except json.JSONDecodeError:
            continue
    if entries:
        st.dataframe(pd.DataFrame(entries), use_container_width=True, hide_index=True)
    else:
        st.caption("No entries in audit log yet.")
else:
    st.caption("Audit log will appear here after first run.")
