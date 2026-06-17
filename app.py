import os
import re
from datetime import date, datetime
from difflib import SequenceMatcher

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

APP_TITLE = "TPRM DDA Artifact Coverage Agent"
DATA_DIR = "data"
DEFAULT_REVIEW_DATE = date(2026, 6, 16)

st.set_page_config(page_title=APP_TITLE, page_icon="🧭", layout="wide")

# -------------------------------
# Styling
# -------------------------------
st.markdown(
    """
<style>
    .main .block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1280px;}
    h1 {font-size: 3.2rem !important; line-height: 1.05 !important; letter-spacing: -0.04em;}
    h2, h3 {letter-spacing: -0.02em;}
    .muted {color: #6b7280; font-size: 0.96rem;}
    .micro {font-size: 0.78rem; letter-spacing: 0.06em; text-transform: uppercase; color: #6b7280; font-weight: 700;}
    .card {
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 20px 22px;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
        min-height: 130px;
    }
    .card-soft {
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 18px 20px;
        background: #f8fafc;
        min-height: 120px;
    }
    .metric-big {font-size: 2.4rem; font-weight: 800; letter-spacing: -0.05em; margin-top: 4px;}
    .metric-label {font-size: 0.84rem; color: #6b7280; font-weight: 600;}
    .pill {display:inline-block; padding: 5px 10px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; margin: 3px 4px 3px 0;}
    .pill-blue {background:#e8f1ff; color:#1d4ed8;}
    .pill-green {background:#ecfdf3; color:#027a48;}
    .pill-yellow {background:#fff8db; color:#92400e;}
    .pill-red {background:#fff1f2; color:#be123c;}
    .pill-gray {background:#f3f4f6; color:#374151;}
    .section-kicker {font-size:0.82rem; color:#ff4b4b; font-weight:800; text-transform:uppercase; letter-spacing:.09em; margin-bottom:0.2rem;}
    .action-box {border: 1px solid #fecaca; background:#fff7f7; border-radius:16px; padding:18px 20px;}
    .success-box {border: 1px solid #bbf7d0; background:#f0fdf4; border-radius:16px; padding:18px 20px;}
    .warn-box {border: 1px solid #fde68a; background:#fffbeb; border-radius:16px; padding:18px 20px;}
    div[data-testid="stMetric"] {background: #ffffff; border:1px solid #e5e7eb; border-radius:14px; padding:14px 16px;}
</style>
""",
    unsafe_allow_html=True,
)

# -------------------------------
# Data helpers
# -------------------------------
@st.cache_data
def load_csv(name: str) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, name)
    return pd.read_csv(path)


def parse_date(value):
    if pd.isna(value) or str(value).strip() == "":
        return None
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def months_between(d1: date, d2: date) -> float:
    return max((d2 - d1).days / 30.4375, 0)


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    if count == 1:
        return singular
    return plural_form if plural_form else singular + "s"


def calc_artifact_status(row, review_date: date, uploaded_ids=None):
    uploaded_ids = uploaded_ids or set()
    if row["artifact_id"] in uploaded_ids:
        return "Resolved by Upload"
    if str(row.get("current_status", "")).lower() == "missing":
        return "Missing"
    received = parse_date(row.get("last_received_date"))
    if received is None:
        return "Missing"
    age_months = months_between(received, review_date)
    validity = float(row.get("validity_months", 12))
    if age_months > validity:
        return "Expired"
    if age_months >= validity * 0.75:
        return "Expiring Soon"
    return "Reusable"


def status_badge(status: str) -> str:
    cls = {
        "Reusable": "pill-green",
        "Resolved by Upload": "pill-green",
        "Expiring Soon": "pill-yellow",
        "Expired": "pill-red",
        "Missing": "pill-red",
        "Review": "pill-blue",
    }.get(status, "pill-gray")
    return f'<span class="pill {cls}">{status}</span>'


def build_coverage(historical, artifacts, triggered, review_date: date, uploaded_artifacts=None):
    uploaded_ids = set()
    if uploaded_artifacts is not None and len(uploaded_artifacts) > 0:
        uploaded_ids = set(uploaded_artifacts["artifact_id"].astype(str).tolist())

    art = artifacts.copy()
    art["artifact_status"] = art.apply(lambda r: calc_artifact_status(r, review_date, uploaded_ids), axis=1)
    art["needs_vendor_request"] = art["artifact_status"].isin(["Expired", "Missing", "Expiring Soon"])
    art.loc[art["artifact_status"].eq("Resolved by Upload"), "needs_vendor_request"] = False

    rows = []
    for _, dda in triggered.iterrows():
        domain = dda["domain"]
        h = historical[historical["domain"].eq(domain)].iloc[0]
        domain_art = art[art["domain"].eq(domain)]
        reusable = int(domain_art["artifact_status"].isin(["Reusable", "Resolved by Upload"]).sum())
        expiring = int(domain_art["artifact_status"].eq("Expiring Soon").sum())
        expired = int(domain_art["artifact_status"].eq("Expired").sum())
        missing = int(domain_art["artifact_status"].eq("Missing").sum())
        request_count = int(domain_art["needs_vendor_request"].sum())
        supported_by_reuse = int(domain_art.loc[domain_art["artifact_status"].isin(["Reusable", "Resolved by Upload"]), "questions_supported"].sum())
        supported_by_stale = int(domain_art.loc[domain_art["artifact_status"].isin(["Expiring Soon", "Expired"]), "questions_supported"].sum())
        supported_by_missing = int(domain_art.loc[domain_art["artifact_status"].eq("Missing"), "questions_supported"].sum())
        rows.append(
            {
                "domain": domain,
                "dda_name": dda["dda_name"],
                "triggered_questions": int(dda["triggered_questions"]),
                "historically_answered_questions": int(h["historically_answered_questions"]),
                "artifact_count": int(len(domain_art)),
                "reusable_artifacts": reusable,
                "expiring_artifacts": expiring,
                "expired_artifacts": expired,
                "missing_artifacts": missing,
                "net_new_or_updated_artifacts": request_count,
                "questions_supported_by_reuse": supported_by_reuse,
                "questions_at_risk_due_to_stale_artifacts": supported_by_stale,
                "questions_with_missing_artifact_support": supported_by_missing,
            }
        )
    return pd.DataFrame(rows), art


def build_dda_summary(row) -> str:
    request_count = int(row["net_new_or_updated_artifacts"])
    expired = int(row["expired_artifacts"])
    expiring = int(row["expiring_artifacts"])
    missing = int(row["missing_artifacts"])
    return (
        f"The {row['dda_name']} has {int(row['triggered_questions'])} triggered questions. "
        f"Historically, {int(row['historically_answered_questions'])} of those questions were answered using "
        f"{int(row['artifact_count'])} {plural(int(row['artifact_count']), 'artifact')}. "
        f"{int(row['reusable_artifacts'])} {plural(int(row['reusable_artifacts']), 'artifact')} "
        f"{'is' if int(row['reusable_artifacts']) == 1 else 'are'} reusable. "
        f"{expired} {plural(expired, 'artifact')} {'has' if expired == 1 else 'have'} expired, "
        f"{expiring} {plural(expiring, 'artifact')} {'is' if expiring == 1 else 'are'} approaching refresh, "
        f"and {missing} {plural(missing, 'artifact')} {'is' if missing == 1 else 'are'} missing. "
        f"To complete the refreshed DDA, request {request_count} net-new or updated "
        f"{plural(request_count, 'artifact')}."
    )


def build_abbreviated_request(open_artifacts: pd.DataFrame) -> str:
    if open_artifacts.empty:
        return "No net-new vendor artifact request is required. Existing evidence appears sufficient for Risk Advisor review."
    lines = [
        "Abbreviated DDA Artifact Request",
        "",
        "Please provide the following updated or net-new artifacts to complete the refreshed due diligence review:",
        "",
    ]
    for i, (_, r) in enumerate(open_artifacts.iterrows(), 1):
        lines.append(
            f"{i}. {r['artifact_name']} ({r['domain']}) — Priority: {r['priority']}. "
            f"Reason: {r['why_needed']}. This artifact supports approximately {int(r['questions_supported'])} DDA questions."
        )
    lines.extend([
        "",
        "Please provide the most current approved version, including effective date, owner, and any supporting evidence or test results where applicable.",
    ])
    return "\n".join(lines)


def build_vendor_email(open_artifacts: pd.DataFrame) -> str:
    if open_artifacts.empty:
        return "No vendor outreach is required based on current artifact coverage."
    request_lines = []
    for i, (_, r) in enumerate(open_artifacts.iterrows(), 1):
        request_lines.append(f"{i}. {r['artifact_name']} — {r['domain']} — {r['why_needed']}")
    return (
        "Subject: Request for Updated Due Diligence Artifacts\n\n"
        "Hello,\n\n"
        "As part of the refreshed third-party risk review, we reviewed previously available due diligence evidence and identified a limited set of updated artifacts needed to complete the assessment.\n\n"
        "Please provide the following artifacts:\n"
        + "\n".join(request_lines)
        + "\n\nPlease include the current approved version, effective date, and any applicable supporting evidence.\n\n"
        "Thank you,\nRisk Advisor"
    )


def render_card(title, value, caption="", pill_html=""):
    st.markdown(
        f"""
<div class="card">
  <div class="micro">{caption}</div>
  <div class="metric-big">{value}</div>
  <div style="font-weight:750; font-size:1.05rem; margin-top:4px;">{title}</div>
  <div style="margin-top:8px;">{pill_html}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_stacked_coverage_chart(coverage: pd.DataFrame):
    if coverage.empty:
        return
    chart_width = 980
    row_height = 46
    label_width = 210
    bar_width = 660
    chart_height = 40 + row_height * len(coverage)
    svg_font = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

    parts = [
        f'''
        <svg width="100%" height="{chart_height}" viewBox="0 0 {chart_width} {chart_height}"
             xmlns="http://www.w3.org/2000/svg"
             style="font-family: {svg_font};">
        ''',
    ]
    y = 38
    for _, r in coverage.iterrows():
        total = max(int(r["triggered_questions"]), 1)
        reuse = int(r["questions_supported_by_reuse"])
        stale = int(r["questions_at_risk_due_to_stale_artifacts"])
        missing = int(r["questions_with_missing_artifact_support"])
        # Clamp segments to visible width.
        reuse_w = min(bar_width, int((reuse / total) * bar_width))
        stale_w = min(bar_width - reuse_w, int((stale / total) * bar_width))
        missing_w = min(bar_width - reuse_w - stale_w, int((missing / total) * bar_width))
        parts.append(f'<text x="0" y="{y+18}" font-size="13" font-weight="700" fill="#374151">{r["domain"]}</text>')
        parts.append(f'<rect x="{label_width}" y="{y}" width="{bar_width}" height="24" fill="#f3f4f6" rx="8"/>')
        parts.append(f'<rect x="{label_width}" y="{y}" width="{reuse_w}" height="24" fill="#4F83F1" rx="8"/>')
        parts.append(f'<rect x="{label_width + reuse_w}" y="{y}" width="{stale_w}" height="24" fill="#F5B041"/>')
        parts.append(f'<rect x="{label_width + reuse_w + stale_w}" y="{y}" width="{missing_w}" height="24" fill="#E57373"/>')
        parts.append(f'<text x="{label_width + bar_width + 16}" y="{y+17}" font-size="12" fill="#374151">{reuse}/{total} reusable-supported</text>')
        y += row_height
    parts.append('</svg>')
    components.html("".join(parts), height=chart_height + 20)


def render_vertical_artifact_chart(coverage: pd.DataFrame):
    totals = {
        "Reusable": int(coverage["reusable_artifacts"].sum()),
        "Expiring": int(coverage["expiring_artifacts"].sum()),
        "Expired": int(coverage["expired_artifacts"].sum()),
        "Missing": int(coverage["missing_artifacts"].sum()),
    }
    colors = {
    "Reusable": "#4F83F1",
    "Expiring": "#58C27D",
    "Expired": "#F5B041",
    "Missing": "#E57373",
    }
    max_val = max(max(totals.values()), 1)
    chart_width, chart_height = 540, 280
    baseline, max_bar_h, bar_w, gap, left = 210, 160, 70, 45, 55
    svg_font = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

    parts = [
        f'''
        <svg width="100%" height="{chart_height}" viewBox="0 0 {chart_width} {chart_height}"
             xmlns="http://www.w3.org/2000/svg"
             style="font-family: {svg_font};">
        ''',
        f'<line x1="35" y1="{baseline}" x2="{chart_width-30}" y2="{baseline}" stroke="#d1d5db"/>',
    ]
    for i, (label, val) in enumerate(totals.items()):
        h = int((val / max_val) * max_bar_h) if val else 0
        x = left + i * (bar_w + gap)
        y = baseline - h
        parts.append(f'<rect x="{x}" y="{y}" width="{bar_w}" height="{h}" fill="{colors[label]}" rx="7"/>')
        parts.append(f'<text x="{x+bar_w/2}" y="{y-8}" text-anchor="middle" font-size="13" font-weight="700" fill="#374151">{val}</text>')
        parts.append(f'<text x="{x+bar_w/2}" y="{baseline+24}" text-anchor="middle" font-size="12" fill="#374151">{label}</text>')
    parts.append('</svg>')
    components.html("".join(parts), height=chart_height)


def build_context_packet(coverage, artifacts, lexis, open_artifacts, abbreviated_request):
    lines = ["You are a TPRM Risk Advisor assistant. Answer only from this context.", ""]
    lines.append("DDA Coverage Summary:")
    for _, r in coverage.iterrows():
        lines.append("- " + build_dda_summary(r))
    lines.append("\nOpen / requested artifacts:")
    if open_artifacts.empty:
        lines.append("- None")
    else:
        for _, r in open_artifacts.iterrows():
            lines.append(f"- {r['artifact_name']} | Domain: {r['domain']} | Status: {r['artifact_status']} | Priority: {r['priority']} | Questions supported: {int(r['questions_supported'])} | Reason: {r['why_needed']}")
    lines.append("\nLexisNexis-style vendor matches:")
    for _, r in lexis.iterrows():
        lines.append(f"- {r['vendor_name_observed']} -> {r['canonical_vendor_name']} | Score: {r['match_score']} | Signal: {r['risk_signal']} | Notes: {r['notes']}")
    lines.append("\nAbbreviated DDA request:")
    lines.append(abbreviated_request)
    return "\n".join(lines)


def fallback_answer(question, coverage, open_artifacts, lexis):
    q = question.lower()
    if "artifact" in q and ("need" in q or "request" in q or "missing" in q):
        if open_artifacts.empty:
            return "Based on the current coverage analysis, no net-new vendor artifact request is required."
        names = ", ".join(open_artifacts["artifact_name"].tolist())
        return f"The Risk Advisor should request or refresh these artifacts: {names}."
    if "stale" in q or "expired" in q or "expir" in q:
        stale = open_artifacts[open_artifacts["artifact_status"].isin(["Expired", "Expiring Soon"])]
        if stale.empty:
            return "No expired or expiring artifacts are currently shown in the coverage output."
        return "Expired or expiring artifacts include: " + ", ".join(stale["artifact_name"].tolist()) + "."
    if "lexis" in q or "duplicate" in q or "match" in q:
        top = lexis[lexis["match_score"] >= 0.75]
        return "LexisNexis-style matching found potential vendor/entity matches: " + ", ".join(top["vendor_name_observed"].tolist()) + ". Risk Advisor should confirm if these represent the same vendor, product alias, subsidiary, or unrelated entity."
    if "model" in q:
        row = coverage[coverage["domain"].eq("Model Risk")]
        if not row.empty:
            return build_dda_summary(row.iloc[0])
    return "The available demo data does not contain enough information to answer that question. Try asking about missing artifacts, stale artifacts, Model Risk coverage, or LexisNexis matches."


def call_openai(question, context):
    api_key = st.secrets.get("OPENAI_API_KEY", None)
    if not api_key or OpenAI is None:
        return None
    client = OpenAI(api_key=api_key)
    prompt = (
        "You are a third-party risk management assistant. Answer the user's question using only the provided context. "
        "Do not invent evidence. Do not make final risk decisions. If the context is insufficient, say so. "
        "Keep the answer concise and actionable for a Risk Advisor.\n\n"
        f"CONTEXT:\n{context}\n\nUSER QUESTION:\n{question}"
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return response.choices[0].message.content

# -------------------------------
# App state and data load
# -------------------------------
historical = load_csv("historical_ddas.csv")
artifacts = load_csv("artifacts_required_to_complete_ddas.csv")
lexis = load_csv("lexisnexis_vendor_records.csv")
triggered = load_csv("new_triggered_dda_package.csv")
public_evidence = load_csv("public_evidence_library.csv")
sample_upload = load_csv("vendor_uploaded_artifacts.csv")

if "coverage_run" not in st.session_state:
    st.session_state.coverage_run = False
if "uploaded_artifacts" not in st.session_state:
    st.session_state.uploaded_artifacts = pd.DataFrame(columns=sample_upload.columns)
if "abbrev_generated" not in st.session_state:
    st.session_state.abbrev_generated = False
if "vendor_email_generated" not in st.session_state:
    st.session_state.vendor_email_generated = False

# -------------------------------
# Header
# -------------------------------
st.markdown('<div class="section-kicker">Phase 2 Demo</div>', unsafe_allow_html=True)
st.title("DDA Evidence Reuse & Risk Advisor Workflow")
st.markdown(
    """
<div class="muted">
This app demonstrates how a TPRM agent can reuse historical Archer DDA evidence, evaluate artifact freshness, identify LexisNexis-style vendor/entity matches, generate an abbreviated artifact request, and support Risk Advisor Q&A.
</div>
""",
    unsafe_allow_html=True,
)

st.divider()

# -------------------------------
# Sidebar controls
# -------------------------------
with st.sidebar:
    st.header("Demo Controls")
    vendor_options = sorted(historical["vendor"].unique())
    default_vendor = "Contoso AI Services"
    default_index = vendor_options.index(default_vendor) if default_vendor in vendor_options else 0
    vendor = st.selectbox("Vendor", vendor_options, index=default_index)
    review_date = st.date_input("Current review date", value=DEFAULT_REVIEW_DATE)

    triggered_for_vendor = triggered[triggered["vendor"].eq(vendor)].copy()
    domain_options = triggered_for_vendor["domain"].tolist()
    selected_domains = st.multiselect(
        "Triggered DDA domains",
        options=domain_options,
        default=domain_options,
    )
    st.caption("Tip: select Contoso AI Services for the primary demo story, or switch vendors to show the same workflow works across a portfolio.")
    if st.button("Reset demo state"):
        st.session_state.coverage_run = False
        st.session_state.uploaded_artifacts = pd.DataFrame(columns=sample_upload.columns)
        st.session_state.abbrev_generated = False
        st.session_state.vendor_email_generated = False
        st.rerun()

triggered_filtered = triggered_for_vendor[triggered_for_vendor["domain"].isin(selected_domains)].copy()
historical_filtered = historical[historical["vendor"].eq(vendor)].copy()
artifacts_filtered = artifacts[artifacts["vendor"].eq(vendor)].copy()
lexis_filtered = lexis[lexis["canonical_vendor_name"].eq(vendor)].copy()
# Only apply uploaded artifacts for the selected vendor.
uploaded_for_vendor = st.session_state.uploaded_artifacts
if not uploaded_for_vendor.empty and "vendor" in uploaded_for_vendor.columns:
    uploaded_for_vendor = uploaded_for_vendor[uploaded_for_vendor["vendor"].eq(vendor)].copy()

coverage, artifact_status = build_coverage(
    historical_filtered,
    artifacts_filtered,
    triggered_filtered,
    review_date,
    uploaded_for_vendor,
)
open_artifacts = artifact_status[artifact_status["needs_vendor_request"]].copy().sort_values(["priority", "domain"])
abbrev_text = build_abbreviated_request(open_artifacts)

# -------------------------------
# Tabs
# -------------------------------
tab_overview, tab_action, tab_qa = st.tabs(["1. Coverage Overview", "2. Risk Advisor Action Center", "3. Q&A"])

with tab_overview:
    st.subheader("Historical DDA repository")
    st.markdown('<div class="muted">Seven prior DDAs are available for the selected synthetic vendor. Each DDA is tied to required artifacts and a completion date.</div>', unsafe_allow_html=True)
    st.write("")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_card("Historical DDAs", len(historical_filtered), "Repository")
    with c2:
        render_card("Triggered domains", len(triggered_filtered), "Current package")
    with c3:
        render_card("Artifacts mapped", len(artifacts_filtered), "DDA-to-artifact map")
    with c4:
        render_card("LexisNexis candidates", len(lexis_filtered[lexis_filtered["match_score"] >= 0.75]), "Entity matching")

    st.write("")
    st.markdown("#### DDA cards")
    cards = st.columns(4)
    for i, (_, r) in enumerate(historical_filtered.iterrows()):
        with cards[i % 4]:
            status = "Triggered" if r["domain"] in selected_domains else "Not in current package"
            pill = status_badge("Review" if status == "Triggered" else "Not selected")
            st.markdown(
                f"""
<div class="card-soft">
  <div class="micro">{r['domain']}</div>
  <h4 style="margin:.25rem 0;">{r['dda_name']}</h4>
  <div class="muted">Completed: {r['completed_date']}</div>
  <div class="muted">Questions: {int(r['total_questions'])} | Prior answers: {int(r['historically_answered_questions'])}</div>
  <div style="margin-top:10px;">{pill}</div>
</div>
""",
                unsafe_allow_html=True,
            )

    st.divider()
    st.subheader("Run artifact coverage analysis")
    left, right = st.columns([1, 2])
    with left:
        if st.button("Run Coverage Analysis", type="primary"):
            st.session_state.coverage_run = True
            st.success("Coverage analysis completed.")
    with right:
        st.markdown('<div class="muted">The analysis checks which required artifacts are reusable, expiring, expired, or missing. It then converts DDA question gaps into artifact requests.</div>', unsafe_allow_html=True)

    if st.session_state.coverage_run:
        total_questions = int(coverage["triggered_questions"].sum())
        reusable_supported = int(coverage["questions_supported_by_reuse"].sum())
        open_count = int(open_artifacts.shape[0])
        reusable_artifacts = int(coverage["reusable_artifacts"].sum())

        st.write("")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Triggered Questions", total_questions)
        m2.metric("Questions Supported by Reusable Artifacts", reusable_supported)
        m3.metric("Reusable / Resolved Artifacts", reusable_artifacts)
        m4.metric("Artifacts Needing Request", open_count)

        st.write("")
        st.write("")
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("#### Question Coverage by Artifact Status")
            st.caption(
                "Shows how triggered DDA questions are supported by reusable, stale/expiring, or missing artifacts across each domain."
            )
            st.markdown(
                """
                <div style="display:flex; gap:18px; align-items:center; margin:8px 0 4px 0; font-size:13px; color:#4b5563;">
                    <div><span style="display:inline-block; width:12px; height:12px; background:#4F83F1; border-radius:3px; margin-right:6px;"></span>Reusable / Resolved</div>
                    <div><span style="display:inline-block; width:12px; height:12px; background:#F5B041; border-radius:3px; margin-right:6px;"></span>Stale / Expiring</div>
                    <div><span style="display:inline-block; width:12px; height:12px; background:#E57373; border-radius:3px; margin-right:6px;"></span>Missing</div>
                    <div><span style="display:inline-block; width:12px; height:12px; background:#f3f4f6; border-radius:3px; margin-right:6px; border:1px solid #e5e7eb;"></span>Unmapped / Remaining</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            render_stacked_coverage_chart(coverage)
        
        with col2:
            st.markdown("#### Artifact Health Summary")
            st.caption(
                "Shows the total number of artifacts by current evidence status for the selected vendor and triggered DDA package."
            )
            render_vertical_artifact_chart(coverage)

        st.write("")
        st.markdown("#### Coverage summaries")
        
        summary_cards = st.columns(3)
        
        for i, (_, row) in enumerate(coverage.iterrows()):
            with summary_cards[i % 3]:
                status = "Fully covered" if int(row["net_new_or_updated_artifacts"]) == 0 else "Needs request"
                pill = status_badge("Reusable" if status == "Fully covered" else "Review")
        
                st.markdown(
                    f"""
        <div class="card-soft">
          <div class="micro">{row['domain']}</div>
          <h4 style="margin:.25rem 0;">{row['dda_name']}</h4>
          <div class="muted">Triggered questions: {int(row['triggered_questions'])}</div>
          <div class="muted">Historically answered: {int(row['historically_answered_questions'])}</div>
          <div class="muted">Reusable artifacts: {int(row['reusable_artifacts'])}</div>
          <div class="muted">Expiring / expired / missing: {int(row['expiring_artifacts'])} / {int(row['expired_artifacts'])} / {int(row['missing_artifacts'])}</div>
          <div class="muted">Net-new or updated artifacts needed: {int(row['net_new_or_updated_artifacts'])}</div>
          <div style="margin-top:10px;">{pill}</div>
        </div>
        """,
                    unsafe_allow_html=True,
                )

        st.markdown("#### Artifact status workbench")
        display_cols = [
            "domain", "dda_name", "artifact_id", "artifact_name", "artifact_type", "questions_supported", "last_received_date", "validity_months", "artifact_status", "priority", "why_needed"
        ]
        st.dataframe(artifact_status[display_cols], use_container_width=True, hide_index=True)

        st.markdown("#### LexisNexis-style vendor/entity matching")
        st.markdown('<div class="muted">This simulates fuzzy matching where the same vendor may appear under alternate names, product names, or related entity names.</div>', unsafe_allow_html=True)
        st.dataframe(lexis_filtered, use_container_width=True, hide_index=True)
        likely = lexis_filtered[lexis_filtered["match_score"] >= 0.75]
        st.info(
            f"LexisNexis-style matching found {len(likely)} potential vendor/entity records for {vendor}. Risk Advisor should confirm whether these represent the same vendor, product alias, subsidiary, or unrelated entity."
        )

with tab_action:
    st.subheader("Risk Advisor Action Center")
    st.markdown('<div class="muted">Use this area to generate the abbreviated DDA request, draft vendor outreach, simulate vendor artifact intake, and re-run coverage.</div>', unsafe_allow_html=True)

    if not st.session_state.coverage_run:
        st.warning("Run Coverage Analysis in the first tab before taking Risk Advisor actions.")
    else:
        a1, a2, a3 = st.columns(3)
        with a1:
            if st.button("Generate Abbreviated DDA Request", type="primary"):
                st.session_state.abbrev_generated = True
        with a2:
            if st.button("Draft Vendor Outreach"):
                st.session_state.vendor_email_generated = True
        with a3:
            if st.button("Use Sample Vendor Upload"):
                st.session_state.uploaded_artifacts = sample_upload[sample_upload["vendor"].eq(vendor)].copy()
                st.success(f"Sample vendor artifacts for {vendor} loaded. Click Re-run Coverage to apply them.")

        st.write("")
        if st.session_state.abbrev_generated:
            st.markdown("#### Abbreviated DDA Artifact Request")
            st.markdown(
                """
                <div class="action-box">
                    <b>Generated abbreviated DDA artifact request</b><br>
                    <span class="muted">Review and edit the request below before sending it to the vendor.</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.text_area("Risk Advisor editable request", value=abbrev_text, height=260, key="abbrev_request_text")

        if st.session_state.vendor_email_generated:
            st.markdown("#### Draft Vendor Outreach")
            st.text_area("Draft email", value=build_vendor_email(open_artifacts), height=260)

        st.divider()
        st.markdown("#### Upload vendor artifact CSV or use sample")
        uploaded = st.file_uploader("Upload vendor artifact CSV", type=["csv"])
        if uploaded is not None:
            try:
                df_uploaded = pd.read_csv(uploaded)
                required_cols = set(sample_upload.columns)
                if required_cols.issubset(set(df_uploaded.columns)):
                    st.session_state.uploaded_artifacts = df_uploaded.copy()
                    st.success("Uploaded artifact file accepted. Click Re-run Coverage to apply it.")
                else:
                    st.error("Uploaded CSV does not match the expected vendor artifact schema.")
            except Exception as exc:
                st.error(f"Unable to read uploaded CSV: {exc}")

        if not st.session_state.uploaded_artifacts.empty:
            st.markdown("##### Current vendor artifact intake queue")
            st.dataframe(st.session_state.uploaded_artifacts, use_container_width=True, hide_index=True)

        if st.button("Re-run Coverage After Vendor Upload", type="primary"):
            st.session_state.coverage_run = True
            st.success("Coverage refreshed using the vendor artifact intake queue.")
            st.rerun()

        st.divider()
        st.markdown("#### Before / After Coverage")
        before_cov, before_art = build_coverage(historical_filtered, artifacts_filtered, triggered_filtered, review_date, pd.DataFrame(columns=sample_upload.columns))
        after_cov, after_art = build_coverage(historical_filtered, artifacts_filtered, triggered_filtered, review_date, uploaded_for_vendor)
        compare = pd.DataFrame([
            {"Metric": "Artifacts needing request", "Before": int(before_art["needs_vendor_request"].sum()), "After": int(after_art["needs_vendor_request"].sum())},
            {"Metric": "Reusable / resolved artifacts", "Before": int(before_art["artifact_status"].isin(["Reusable", "Resolved by Upload"]).sum()), "After": int(after_art["artifact_status"].isin(["Reusable", "Resolved by Upload"]).sum())},
            {"Metric": "Expired artifacts", "Before": int(before_art["artifact_status"].eq("Expired").sum()), "After": int(after_art["artifact_status"].eq("Expired").sum())},
            {"Metric": "Expiring artifacts", "Before": int(before_art["artifact_status"].eq("Expiring Soon").sum()), "After": int(after_art["artifact_status"].eq("Expiring Soon").sum())},
        ])
        st.dataframe(compare, use_container_width=True, hide_index=True)
        if int(after_art["needs_vendor_request"].sum()) < int(before_art["needs_vendor_request"].sum()):
            st.success("The uploaded artifact package resolved one or more previously open artifact requests.")

with tab_qa:
    st.subheader("Ask the TPRM Agent")
    st.markdown(
        '<div class="muted">The Q&A tab answers from the current demo context: historical DDAs, artifact coverage, abbreviated request, and LexisNexis-style matches. If an OpenAI key is configured in Streamlit Secrets, the tab uses OpenAI. Otherwise, it falls back to rule-based responses.</div>',
        unsafe_allow_html=True,
    )
    examples = [
        "Which artifacts should the Risk Advisor request from the vendor?",
        "Why is the Model Risk DDA incomplete?",
        "Which artifacts are stale or expired?",
        "What did the LexisNexis-style search find?",
        "What changed after the vendor uploaded new artifacts?",
    ]
    selected_example = st.selectbox("Try an example question", [""] + examples)
    user_q = st.text_input("Ask a question", value=selected_example)

    if st.button("Ask Agent") and user_q.strip():
        context = build_context_packet(coverage, artifact_status, lexis_filtered, open_artifacts, abbrev_text)
        answer = None
        try:
            answer = call_openai(user_q, context)
        except Exception as exc:
            st.warning(f"OpenAI Q&A was not available, using fallback answer. Detail: {exc}")
        if not answer:
            answer = fallback_answer(user_q, coverage, open_artifacts, lexis_filtered)
        st.markdown("#### Agent Answer")
        st.markdown(f'<div class="success-box">{answer}</div>', unsafe_allow_html=True)

    with st.expander("Show Q&A context packet"):
        st.text(build_context_packet(coverage, artifact_status, lexis_filtered, open_artifacts, abbrev_text))

st.caption("Synthetic demo only. The agent does not make final risk decisions; Risk Advisor and SME review remain required.")
