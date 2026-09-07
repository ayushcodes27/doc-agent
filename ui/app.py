import streamlit as st
import requests
import json
import os
import html

API_URL = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="DocAgent", page_icon="🧾", layout="wide")

# ----------------------------------------------------------------------------
# Style system
# ----------------------------------------------------------------------------
STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
    --ink: #1B2030;
    --ink-soft: #5B5F70;
    --paper: #F6F4EE;
    --line: #DEDACC;
    --brass: #A9782F;
    --forest: #33604A;
    --rust: #9C3B2C;
    --ochre: #B5751D;
    --slate: #6E6A5E;
}

html, body, [class*="css"]  { color: var(--ink); }
.stApp { background-color: var(--paper); }
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 2.5rem; max-width: 1100px; }

/* ---- Header ---- */
.da-header { margin-bottom: 0.25rem; }
[data-testid="stMarkdownContainer"] p.da-title {
    font-family: 'Fraunces', serif !important;
    font-weight: 600 !important;
    font-size: 2.5rem !important;
    letter-spacing: -0.02em;
    margin: 0 0 0.1rem 0 !important;
    line-height: 1.05 !important;
}
[data-testid="stMarkdownContainer"] p.da-subtitle {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.95rem !important;
    color: var(--ink-soft);
    margin: 0.5rem 0 1.1rem 0 !important;
    max-width: 62ch;
}
.da-rule { height: 2px; background: var(--brass); border: none; margin: 0 0 1.8rem 0; width: 100%; }

/* ---- Upload row ---- */
.da-field-label {
    font-family: 'Inter', sans-serif;
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--ink);
    margin-bottom: 0.35rem;
}
[data-testid="stFileUploaderDropzone"] {
    background: transparent;
    border: 1px solid var(--line);
    border-radius: 2px;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--brass); }

/* Upload hint styling */
[data-testid="stFileUploader"] small {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.78rem !important;
    color: var(--ink-soft) !important;
}
[data-testid="stFileUploaderDropzone"] [data-testid="stFileUploaderDropzoneInstructions"]>div>span {
    display: none;
}
[data-testid="stFileUploaderDropzone"] [data-testid="stFileUploaderDropzoneInstructions"]>div::after {
    content: "PDF invoices, up to 200MB";
    font-family: 'Inter', sans-serif;
    font-size: 0.82rem;
    color: var(--ink-soft);
    display: block;
}

/* ---- Action button & Disabled state ---- */
.stButton>button {
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    background-color: var(--ink);
    color: var(--paper);
    border: 1px solid var(--ink);
    border-radius: 2px;
    padding: 0.5rem 1.3rem;
    transition: all 0.15s ease-in-out;
}
.stButton>button:hover:not(:disabled) {
    background-color: var(--brass);
    border-color: var(--brass);
    color: var(--paper);
}
.stButton>button:disabled,
.stButton>button[disabled] {
    background-color: #E6E2D6 !important;
    color: #8C887B !important;
    border: 1px solid #D5D0C2 !important;
    cursor: not-allowed !important;
    opacity: 0.85 !important;
}

/* ---- Empty state ---- */
.empty-state {
    margin-top: 2rem;
    padding: 2.5rem 2rem;
    border: 1px dashed var(--line);
    background: rgba(0,0,0,0.015);
    border-radius: 4px;
    text-align: center;
}
.empty-icon { font-size: 2rem; margin-bottom: 0.5rem; opacity: 0.85; }
.empty-title {
    font-family: 'Fraunces', serif;
    font-weight: 600;
    font-size: 1.25rem;
    color: var(--ink);
    margin-bottom: 0.4rem;
}
.empty-subtitle {
    font-family: 'Inter', sans-serif;
    font-size: 0.88rem;
    color: var(--ink-soft);
    max-width: 58ch;
    margin: 0 auto 1.8rem auto;
    line-height: 1.45;
}
.empty-preview-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1rem;
    max-width: 800px;
    margin: 0 auto;
    text-align: left;
}
.empty-preview-card {
    background: #FFFFFF;
    border: 1px solid var(--line);
    padding: 0.9rem 1.1rem;
    border-radius: 2px;
}
.empty-card-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: var(--brass);
    font-weight: 500;
    display: block;
    margin-bottom: 0.3rem;
}
.empty-preview-card p {
    font-family: 'Inter', sans-serif;
    font-size: 0.8rem;
    color: var(--ink-soft);
    margin: 0;
    line-height: 1.35;
}

/* ---- Verdict bar ---- */
.verdict {
    border-left: 5px solid var(--slate);
    background: rgba(0,0,0,0.02);
    padding: 1.1rem 1.4rem;
    margin: 1.6rem 0 2rem 0;
}
.verdict.approve { border-color: var(--forest); }
.verdict.flag { border-color: var(--ochre); }
.verdict.reject { border-color: var(--rust); }
.verdict-top { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 1rem; }
.verdict-status {
    font-family: 'Fraunces', serif;
    font-weight: 600;
    font-size: 1.5rem;
}
.verdict.approve .verdict-status { color: var(--forest); }
.verdict.flag .verdict-status { color: var(--ochre); }
.verdict.reject .verdict-status { color: var(--rust); }

/* ---- Risk gauge with thresholds ---- */
.verdict-gauge {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    min-width: 290px;
}
.gauge-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.gauge-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    font-weight: 500;
    color: var(--ink);
    white-space: nowrap;
}
.gauge-track-container { position: relative; }
.gauge-track {
    position: relative;
    height: 7px;
    background: var(--line);
    border-radius: 1px;
    overflow: visible;
}
.gauge-threshold {
    position: absolute;
    top: -2px;
    bottom: -2px;
    width: 2px;
    background: var(--ink-soft);
    opacity: 0.6;
    z-index: 2;
}
.gauge-fill { position: absolute; top: 0; left: 0; height: 100%; }
.verdict.approve .gauge-fill { background: var(--forest); }
.verdict.flag .gauge-fill { background: var(--ochre); }
.verdict.reject .gauge-fill { background: var(--rust); }
.gauge-scale {
    position: relative;
    display: flex;
    justify-content: space-between;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: var(--ink-soft);
    margin-top: 0.25rem;
}
.verdict-level {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: var(--ink-soft);
    border: 1px solid var(--line);
    padding: 0.1rem 0.5rem;
    background: #FFFFFF;
}
.verdict-reasoning {
    font-family: 'Inter', sans-serif;
    font-size: 0.9rem;
    color: var(--ink-soft);
    margin-top: 0.7rem;
    font-style: italic;
}

/* ---- Section titles ---- */
[data-testid="stMarkdownContainer"] p.section-title {
    font-family: 'Fraunces', serif !important;
    font-weight: 600 !important;
    font-size: 1.15rem !important;
    margin: 0 0 0.9rem 0 !important;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--line);
}

/* ---- Ledger (key/value) ---- */
.ledger-row {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.4rem 0;
    border-bottom: 1px solid var(--line);
    font-size: 0.88rem;
}
.ledger-label { font-family: 'Inter', sans-serif; color: var(--ink-soft); }
.ledger-value { font-family: 'IBM Plex Mono', monospace; color: var(--ink); text-align: right; }
.confidence-tag {
    display: inline-block;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: var(--forest);
    border: 1px solid var(--forest);
    padding: 0.1rem 0.5rem;
    margin-bottom: 0.9rem;
}

/* ---- Line items (tightened proportions) ---- */
.items-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-top: 1.1rem; table-layout: fixed; }
.items-table th:nth-child(1), .items-table td:nth-child(1) { width: 48%; }
.items-table th:nth-child(2), .items-table td:nth-child(2) { width: 14%; text-align: right; }
.items-table th:nth-child(3), .items-table td:nth-child(3) { width: 18%; text-align: right; }
.items-table th:nth-child(4), .items-table td:nth-child(4) { width: 20%; text-align: right; }

.items-table th {
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    color: var(--ink-soft);
    text-align: left;
    font-size: 0.75rem;
    padding: 0.3rem 0.4rem;
    border-bottom: 1px solid var(--ink);
}
.items-table td {
    font-family: 'IBM Plex Mono', monospace;
    padding: 0.4rem 0.4rem;
    border-bottom: 1px solid var(--line);
}
.items-table td.num, .items-table th.num { text-align: right; }
.totals-block { margin-top: 0.8rem; padding-top: 0.4rem; }
.totals-row { display: flex; justify-content: flex-end; gap: 1.5rem; padding: 0.25rem 0.4rem; font-size: 0.85rem; }
.totals-row .t-label { font-family: 'Inter', sans-serif; color: var(--ink-soft); }
.totals-row .t-value { font-family: 'IBM Plex Mono', monospace; min-width: 8ch; text-align: right; }
.totals-row.grand { border-top: 1px solid var(--ink); margin-top: 0.2rem; padding-top: 0.5rem; font-weight: 500; }

/* ---- Compliance checklist & promoted failures ---- */
.compliance-alert {
    font-family: 'Inter', sans-serif;
    font-size: 0.82rem;
    font-weight: 600;
    padding: 0.45rem 0.75rem;
    border-radius: 2px;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}
.compliance-alert.fail {
    background: rgba(156, 59, 44, 0.08);
    color: var(--rust);
    border: 1px solid rgba(156, 59, 44, 0.25);
}
.compliance-alert.pass {
    background: rgba(51, 96, 74, 0.08);
    color: var(--forest);
    border: 1px solid rgba(51, 96, 74, 0.25);
}

.check-row { display: flex; gap: 0.7rem; padding: 0.55rem 0.4rem; border-bottom: 1px solid var(--line); }
.check-row.failed-row {
    background: rgba(156, 59, 44, 0.04);
    border-left: 3px solid var(--rust);
    padding-left: 0.6rem;
}
.check-mark {
    flex-shrink: 0;
    width: 1.1rem; height: 1.1rem;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.7rem;
    margin-top: 0.1rem;
    border: 1px solid;
}
.check-mark.pass { color: var(--forest); border-color: var(--forest); }
.check-mark.fail { color: var(--rust); border-color: var(--rust); }
.check-name { font-family: 'Inter', sans-serif; font-weight: 500; font-size: 0.87rem; }
.check-row.failed-row .check-name { color: var(--rust); font-weight: 600; }
.check-msg { font-family: 'Inter', sans-serif; font-size: 0.82rem; color: var(--ink-soft); margin-top: 0.1rem; }

/* ---- Anomalies ---- */
.anomaly-none { font-family: 'Inter', sans-serif; font-size: 0.87rem; color: var(--forest); display: flex; gap: 0.5rem; align-items: center; }
.anomaly-row { font-family: 'Inter', sans-serif; font-size: 0.87rem; color: var(--ink); padding: 0.4rem 0; border-bottom: 1px solid var(--line); }
.anomaly-row .a-type { color: var(--ochre); font-weight: 500; }

/* ---- Timeline & terminal step styling ---- */
.timeline { position: relative; margin-top: 0.5rem; padding-left: 1.4rem; }
.timeline::before {
    content: "";
    position: absolute;
    left: 4px; top: 4px; bottom: 4px;
    width: 1px;
    background: var(--line);
}
.timeline-item { position: relative; padding-bottom: 1.1rem; }
.timeline-item::before {
    content: "";
    position: absolute;
    left: -1.4rem;
    top: 0.3rem;
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--brass);
}
.timeline-item.terminal::before {
    left: -1.5rem;
    top: 0.2rem;
    width: 9px;
    height: 9px;
    border: 2px solid #FFFFFF;
    box-shadow: 0 0 0 1px var(--ink-soft);
}
.timeline-item.terminal.approve::before { background: var(--forest); box-shadow: 0 0 0 1px var(--forest); }
.timeline-item.terminal.flag::before { background: var(--ochre); box-shadow: 0 0 0 1px var(--ochre); }
.timeline-item.terminal.reject::before { background: var(--rust); box-shadow: 0 0 0 1px var(--rust); }

.timeline-ts { font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; color: var(--ink-soft); }
.timeline-step { font-family: 'Inter', sans-serif; font-weight: 600; font-size: 0.85rem; margin: 0.1rem 0; }
.timeline-detail { font-family: 'Inter', sans-serif; font-size: 0.85rem; color: var(--ink-soft); }
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}


def esc(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def fmt_money(value, currency="USD"):
    symbol = CURRENCY_SYMBOLS.get(currency, currency + " ")
    try:
        return f"{symbol}{float(value):,.2f}"
    except (TypeError, ValueError):
        return esc(value)


def step_label(step: str) -> str:
    return step.replace("_", " ").capitalize() if step else "Step"


# ----------------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------------
st.markdown(
    """
    <div class="da-header">
        <p class="da-title">DocAgent</p>
        <p class="da-subtitle">Upload an invoice and the agent extracts its data, checks it against
        compliance rules, screens for anomalies, and routes it to the right level of approval.</p>
    </div>
    <hr class="da-rule" />
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
# Upload
# ----------------------------------------------------------------------------
st.markdown(
    '<p class="da-field-label">Invoice document <span style="font-weight:400; color:var(--ink-soft); font-size:0.78rem; margin-left:0.4rem;">(PDF or TXT invoices up to 200MB)</span></p>',
    unsafe_allow_html=True,
)
uploaded_file = st.file_uploader(" ", type=["pdf", "txt"], label_visibility="collapsed")
process_clicked = st.button("Process invoice", type="primary", disabled=uploaded_file is None)

# ----------------------------------------------------------------------------
# Processing / Results / Empty State
# ----------------------------------------------------------------------------
if uploaded_file is not None and process_clicked:
    with st.spinner("Agent is processing the document…"):
        try:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            response = requests.post(f"{API_URL}/process", files=files, timeout=60)

            if response.status_code == 200:
                result = response.json()

                decision = result.get("decision", "unknown")
                risk_score = float(result.get("risk_score", 0.0) or 0.0)
                level = result.get("approval_level", "unknown").upper()
                reasoning = result.get("reasoning", "No reasoning provided.")

                decision_map = {
                    "auto_approve": ("approve", "Auto-approved"),
                    "flag_review": ("flag", "Flagged for review"),
                    "reject": ("reject", "Rejected"),
                }
                css_class, status_label = decision_map.get(decision, ("", "Decision pending"))

                st.markdown(
                    f"""
                    <div class="verdict {css_class}">
                        <div class="verdict-top">
                            <div class="verdict-status">{esc(status_label)}</div>
                            <div class="verdict-gauge">
                                <div class="gauge-header">
                                    <span class="gauge-label">Risk score: {risk_score:.0%}</span>
                                    <span class="verdict-level">{esc(level)}</span>
                                </div>
                                <div class="gauge-track-container">
                                    <div class="gauge-track">
                                        <div class="gauge-threshold" style="left: 30%;" title="Auto-approve cutoff (30%)"></div>
                                        <div class="gauge-threshold" style="left: 70%;" title="Review cutoff (70%)"></div>
                                        <div class="gauge-fill" style="width:{max(0, min(risk_score, 1)) * 100:.0f}%"></div>
                                    </div>
                                    <div class="gauge-scale">
                                        <span>0% Safe</span>
                                        <span style="left:30%; position:absolute; transform:translateX(-50%);">30% Auto</span>
                                        <span style="left:70%; position:absolute; transform:translateX(-50%);">70% Review</span>
                                        <span>100% Risk</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="verdict-reasoning">{esc(reasoning)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                col1, col2 = st.columns([1.1, 1])

                # ---------------- Extracted data ----------------
                with col1:
                    st.markdown('<p class="section-title">Extracted data</p>', unsafe_allow_html=True)
                    invoice_data = result.get("invoice")

                    if invoice_data:
                        currency = invoice_data.get("currency", "USD")
                        confidence = invoice_data.get("confidence_score")
                        if confidence is not None:
                            try:
                                st.markdown(
                                    f'<span class="confidence-tag">{float(confidence):.0%} extraction confidence</span>',
                                    unsafe_allow_html=True,
                                )
                            except (TypeError, ValueError):
                                pass

                        header_fields = [
                            ("Vendor", invoice_data.get("vendor_name")),
                            ("Vendor ID", invoice_data.get("vendor_id")),
                            ("Invoice number", invoice_data.get("invoice_number")),
                            ("Invoice date", invoice_data.get("invoice_date")),
                            ("Due date", invoice_data.get("due_date")),
                            ("Payment terms", invoice_data.get("payment_terms")),
                        ]
                        rows_html = "".join(
                            f'<div class="ledger-row"><span class="ledger-label">{esc(label)}</span>'
                            f'<span class="ledger-value">{esc(value) if value not in (None, "") else "—"}</span></div>'
                            for label, value in header_fields
                        )
                        st.markdown(rows_html, unsafe_allow_html=True)

                        line_items = invoice_data.get("line_items", [])
                        if line_items:
                            rows = ""
                            for item in line_items:
                                qty = item.get("quantity", "")
                                unit_price = item.get("unit_price")
                                total = item.get("total")
                                rows += (
                                    "<tr>"
                                    f'<td>{esc(item.get("description", ""))}</td>'
                                    f'<td class="num">{esc(qty)}</td>'
                                    f'<td class="num">{fmt_money(unit_price, currency) if unit_price is not None else "—"}</td>'
                                    f'<td class="num">{fmt_money(total, currency) if total is not None else "—"}</td>'
                                    "</tr>"
                                )
                            st.markdown(
                                f"""
                                <table class="items-table">
                                    <thead>
                                        <tr>
                                            <th>Description</th>
                                            <th class="num">Qty</th>
                                            <th class="num">Unit price</th>
                                            <th class="num">Total</th>
                                        </tr>
                                    </thead>
                                    <tbody>{rows}</tbody>
                                </table>
                                """,
                                unsafe_allow_html=True,
                            )

                        totals_html = '<div class="totals-block">'
                        if invoice_data.get("subtotal") is not None:
                            totals_html += (
                                '<div class="totals-row"><span class="t-label">Subtotal</span>'
                                f'<span class="t-value">{fmt_money(invoice_data.get("subtotal"), currency)}</span></div>'
                            )
                        if invoice_data.get("tax_amount") is not None:
                            totals_html += (
                                '<div class="totals-row"><span class="t-label">Tax</span>'
                                f'<span class="t-value">{fmt_money(invoice_data.get("tax_amount"), currency)}</span></div>'
                            )
                        if invoice_data.get("total_amount") is not None:
                            totals_html += (
                                '<div class="totals-row grand"><span class="t-label">Total</span>'
                                f'<span class="t-value">{fmt_money(invoice_data.get("total_amount"), currency)}</span></div>'
                            )
                        totals_html += "</div>"
                        st.markdown(totals_html, unsafe_allow_html=True)
                    else:
                        st.markdown(
                            '<p style="color: var(--ink-soft); font-family: Inter, sans-serif; font-size: 0.88rem;">'
                            "No data could be extracted from this document.</p>",
                            unsafe_allow_html=True,
                        )

                # ---------------- Compliance & anomalies ----------------
                with col2:
                    st.markdown('<p class="section-title">Compliance & anomalies</p>', unsafe_allow_html=True)

                    validations = result.get("validation_results", [])
                    if not validations:
                        st.markdown(
                            '<p style="color: var(--ink-soft); font-family: Inter, sans-serif; font-size: 0.85rem;">'
                            "No compliance checks were run.</p>",
                            unsafe_allow_html=True,
                        )
                    else:
                        failed_count = sum(1 for v in validations if not v.get("passed"))
                        if failed_count > 0:
                            issue_label = "issue needs" if failed_count == 1 else "issues need"
                            st.markdown(
                                f'<div class="compliance-alert fail">⚠️ {failed_count} {issue_label} review</div>',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(
                                '<div class="compliance-alert pass">✓ All compliance checks passed</div>',
                                unsafe_allow_html=True,
                            )

                        checks_html = ""
                        for v in validations:
                            passed = v.get("passed")
                            mark_class = "pass" if passed else "fail"
                            row_class = "" if passed else "failed-row"
                            mark_symbol = "✓" if passed else "✕"
                            checks_html += (
                                f'<div class="check-row {row_class}">'
                                f'<div class="check-mark {mark_class}">{mark_symbol}</div>'
                                "<div>"
                                f'<div class="check-name">{esc(v.get("rule_name", "Rule"))}</div>'
                                f'<div class="check-msg">{esc(v.get("message", ""))}</div>'
                                "</div>"
                                "</div>"
                            )
                        st.markdown(checks_html, unsafe_allow_html=True)

                    st.markdown(
                        '<p class="section-title" style="margin-top:1.6rem;">Anomalies & fraud detection</p>',
                        unsafe_allow_html=True,
                    )
                    anomalies = result.get("anomalies", [])
                    if anomalies:
                        anomaly_html = "".join(
                            f'<div class="anomaly-row"><span class="a-type">{esc(a.get("type"))}</span> — '
                            f'{esc(a.get("message"))}</div>'
                            for a in anomalies
                        )
                        st.markdown(anomaly_html, unsafe_allow_html=True)
                    else:
                        st.markdown(
                            '<div class="anomaly-none">✓ No anomalies detected</div>',
                            unsafe_allow_html=True,
                        )

                # ---------------- Audit trail ----------------
                st.markdown('<p class="section-title" style="margin-top:2rem;">Agent audit trail</p>', unsafe_allow_html=True)
                audit_trail = result.get("audit_trail", [])
                with st.expander("Show step-by-step log", expanded=False):
                    if not audit_trail:
                        st.markdown(
                            '<p style="color: var(--ink-soft); font-family: Inter, sans-serif; font-size: 0.85rem;">'
                            "No audit events recorded.</p>",
                            unsafe_allow_html=True,
                        )
                    else:
                        items_html = ""
                        total_entries = len(audit_trail)
                        for idx, entry in enumerate(audit_trail):
                            ts = (entry.get("timestamp") or "")[:19].replace("T", " ")
                            is_terminal = (idx == total_entries - 1) or (entry.get("step") in ["decision", "report_generated"])
                            terminal_class = "terminal" if is_terminal else ""
                            items_html += (
                                f'<div class="timeline-item {terminal_class}">'
                                f'<div class="timeline-ts">{esc(ts)}</div>'
                                f'<div class="timeline-step">{esc(step_label(entry.get("step", "")))}</div>'
                                f'<div class="timeline-detail">{esc(entry.get("detail", ""))}</div>'
                                "</div>"
                            )
                        st.markdown(f'<div class="timeline">{items_html}</div>', unsafe_allow_html=True)

            else:
                st.error(f"Error from server: {response.status_code}")
                try:
                    st.json(response.json())
                except Exception:
                    st.write(response.text)

        except requests.exceptions.ConnectionError:
            st.error(f"Could not connect to the backend API at {API_URL}. Is the FastAPI server running?")
        except Exception as e:
            st.error(f"An error occurred: {e}")

else:
    # ----------------------------------------------------------------------------
    # Empty state placeholder
    # ----------------------------------------------------------------------------
    st.markdown(
        """
        <div class="empty-state">
            <div class="empty-icon">🧾</div>
            <div class="empty-title">Awaiting invoice document</div>
            <div class="empty-subtitle">Upload a PDF or TXT invoice above and click <strong>Process invoice</strong> to trigger agent extraction, compliance validation, fraud screening, and routing.</div>
            <div class="empty-preview-grid">
                <div class="empty-preview-card">
                    <span class="empty-card-label">01. Extract</span>
                    <p>Vendor details, line items, taxes, totals & extraction confidence.</p>
                </div>
                <div class="empty-preview-card">
                    <span class="empty-card-label">02. Validate</span>
                    <p>Vendor whitelist, math accuracy, terms & duplicate screening.</p>
                </div>
                <div class="empty-preview-card">
                    <span class="empty-card-label">03. Route</span>
                    <p>Risk-weighted auto-approval, manager flag, or rejection decision.</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
