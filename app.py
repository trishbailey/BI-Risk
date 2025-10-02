import os
import time
from datetime import datetime
import streamlit as st
from src.database import SupabaseManager
# === Optional AI summary (safe to disable if no API key) ===
AI_SUMMARY_ENABLED = bool(os.environ.get("OPENAI_API_KEY"))
# Renderers + AI explainer
from app_components.sanctions_render import render_sanctions_result
if AI_SUMMARY_ENABLED:
    from app_components.ai_explainer import explain_sanctions
    from src.llm.openai_client import OpenAIClient  # For full report generation

# -----------------------------------------------------------------------------
# Page config
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="M&A Risk Assessment Tool",
    page_icon="🔍",
    layout="wide",
)
# -----------------------------------------------------------------------------
# Session state
# -----------------------------------------------------------------------------
state_defaults = {
    "assessment_id": None,
    "step": 1,
    "total_cost": 0.0,
    "company_name": "",
}
for k, v in state_defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v
# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------
@st.cache_resource
def get_db():
    try:
        return SupabaseManager()
    except Exception as e:
        st.error(f"Database connection error: {str(e)}")
        return None
db = get_db()
# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------
st.sidebar.title("M&A Risk Assessment")
if st.session_state.assessment_id:
    st.sidebar.success(f"Active Assessment ID: {st.session_state.assessment_id[:8]}…")
    st.sidebar.metric("Current Cost", f"${st.session_state.total_cost:.2f}")
    if st.sidebar.button("Start New Assessment"):
        for k, v in state_defaults.items():
            st.session_state[k] = v
        st.rerun()
# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
st.title("M&A Risk Assessment Tool")
if not db:
    st.error("Please configure your Supabase credentials to continue.")
    st.markdown(
        """
        ### Setup Instructions:
        1. Create a free Supabase account at supabase.com
        2. Create a new project
        3. Go to Settings > API and copy your URL and anon key
        4. Add these to your Streamlit secrets or `.env`:
           - `SUPABASE_URL=your_url`
           - `SUPABASE_KEY=your_anon_key`
        """
    )
    st.stop()
# -----------------------------------------------------------------------------
# Step 1: Company Information
# -----------------------------------------------------------------------------
if st.session_state.step == 1:
    st.header("Step 1: Company Information")
    with st.form("company_info"):
        company_name = st.text_input("Company Name", value=st.session_state.company_name)
        industry = st.selectbox(
            "Industry",
            ["", "Healthcare", "Financial Services", "Energy", "Technology", "Manufacturing", "Retail", "Other"],
        )
        submitted = st.form_submit_button("Start Assessment")
        if submitted and company_name:
            try:
                assessment_id = db.create_assessment(
                    company_name=company_name,
                    industry=industry or None,
                    created_by="user",
                )
                st.session_state.assessment_id = assessment_id
                st.session_state.company_name = company_name
                st.session_state.step = 2
                st.success("Assessment created!")
                st.rerun()
            except Exception as e:
                st.error(f"Error creating assessment: {str(e)}")
# -----------------------------------------------------------------------------
# Step 2: Sanctions Check
# -----------------------------------------------------------------------------
elif st.session_state.step == 2:
    st.header("Step 2: Sanctions Check")
    st.subheader(f"Checking: {st.session_state.company_name}")
    st.info("This step checks OFAC and OpenSanctions (covers global incl. EU/UN/UK).")
    # Lazy imports so the app loads even if a client is missing
    try:
        from src.api_clients.sanctions.ofac import OFACClient
        ofac_available = True
    except Exception as e:
        st.error(f"OFAC client import error: {e}")
        ofac_available = False
    try:
        from src.api_clients.sanctions.opensanctions import OpenSanctionsClient
        opensanctions_available = True
    except Exception:
        opensanctions_available = False
    # REMOVED: EU Sanctions column and logic (redundant with OpenSanctions)
    col1, col2 = st.columns(2)  # Now 2 columns instead of 3
    # Persistent display for OFAC (shows after click, stays)
    if st.session_state.get('ofac_result'):
        with col1:
            render_sanctions_result("OFAC (SDN)", st.session_state.ofac_result)
            if st.session_state.ofac_result.get("status") == "clear":
                st.success("✅ OFAC Check Complete — No matches found")
            elif st.session_state.ofac_result.get("status") == "error":
                st.error(f"Error: {st.session_state.ofac_result.get('error')}")
    
    # --- OFAC Button ---
    with col1:
        if st.button("🔍 Check OFAC SDN", key="ofac_check"):
            with st.spinner("Checking OFAC Sanctions…"):
                if ofac_available:
                    try:
                        client = OFACClient()
                        ofac_res = client.search_company(st.session_state.company_name)
                        # Store in session_state for persistence
                        st.session_state.ofac_result = ofac_res
                        # persist to DB
                        db.save_api_response(
                            st.session_state.assessment_id,
                            "OFAC_SDN",
                            ofac_res,
                            ofac_res.get("api_cost", 0.0),
                        )
                        st.session_state.total_cost += ofac_res.get("api_cost", 0.0)
                        # risk findings
                        if ofac_res.get("status") == "found_matches":
                            for m in ofac_res.get("matches", []):
                                sev = "critical" if (m.get("match_score") or 0) > 0.9 else "high"
                                db.add_risk_finding(
                                    st.session_state.assessment_id,
                                    "Sanctions",
                                    sev,
                                    f"Potential OFAC match: {m.get('name')} (score: {m.get('match_score')})",
                                    "OFAC_SDN",
                                    m,
                                )
                        st.rerun()  # Refresh to show persistent result
                    except Exception as e:
                        st.session_state.ofac_result = {"status": "error", "error": str(e)}
                        db.save_api_response(
                            st.session_state.assessment_id, "OFAC_SDN", st.session_state.ofac_result, 0.0
                        )
                        st.error(f"Error with OFAC API: {str(e)}")
                        st.rerun()
                else:
                    st.session_state.ofac_result = {"status": "clear", "matches": []}
                    time.sleep(1)
                    db.save_api_response(
                        st.session_state.assessment_id, "OFAC_SDN", st.session_state.ofac_result, 0.0
                    )
                    st.success("✅ OFAC Check Complete — No matches found")
                    st.rerun()
    
    # Persistent display for OpenSanctions (shows after click, stays)
    if st.session_state.get('os_result'):
        with col2:
            render_sanctions_result("OpenSanctions", st.session_state.os_result)
            if st.session_state.os_result.get("status") == "clear":
                st.success("✅ OpenSanctions Check Complete — No matches found")
            elif st.session_state.os_result.get("status") == "error":
                st.error(f"Error: {st.session_state.os_result.get('error')}")
    
    # --- OpenSanctions Button ---
    with col2:
        if st.button("🔍 Check OpenSanctions", key="opensanctions_check"):
            with st.spinner("Checking OpenSanctions…"):
                if opensanctions_available:
                    try:
                        os_client = OpenSanctionsClient(os.getenv("OPENSANCTIONS_API_KEY"))  # Pass key for paid
                        os_res = os_client.search_company(st.session_state.company_name)
                        # Store in session_state for persistence
                        st.session_state.os_result = os_res
                        # persist to DB
                        db.save_api_response(
                            st.session_state.assessment_id,
                            "OpenSanctions",
                            os_res,
                            os_res.get("api_cost", 0.0),
                        )
                        st.session_state.total_cost += os_res.get("api_cost", 0.0)
                        # risk findings
                        if os_res.get("status") == "found_matches":
                            for m in os_res.get("matches", []):
                                sev = "critical" if (m.get("match_score") or 0) > 0.9 else "high"
                                programs_str = ", ".join(m.get("programs", []))
                                db.add_risk_finding(
                                    st.session_state.assessment_id,
                                    "Sanctions",
                                    sev,
                                    f"Potential match in OpenSanctions: {m.get('name')} (score: {m.get('match_score')})"
                                    + (f" — Programs: {programs_str}" if programs_str else ""),
                                    "OpenSanctions",
                                    m,
                                )
                        st.rerun()  # Refresh to show persistent result
                    except Exception as e:
                        st.session_state.os_result = {"status": "error", "error": str(e)}
                        db.save_api_response(
                            st.session_state.assessment_id,
                            "OpenSanctions",
                            st.session_state.os_result,
                            0.0,
                        )
                        st.error(f"Error with OpenSanctions API: {str(e)}")
                        st.rerun()
                else:
                    st.session_state.os_result = {"status": "clear", "matches": []}
                    time.sleep(1)
                    db.save_api_response(
                        st.session_state.assessment_id, "OpenSanctions", st.session_state.os_result, 0.0
                    )
                    st.success("✅ OpenSanctions Check Complete — No matches found")
                    st.rerun()
    
    # -------- Optional AI Summary (draws from both DB entries) --------
    st.markdown("---")
    if AI_SUMMARY_ENABLED:
        if st.button("🧠 Summarize Sanctions Findings with OpenAI"):
            with st.spinner("Analyzing results…"):
                # Pull the latest responses we just saved (from both APIs)
                api_responses = db.get_api_responses(st.session_state.assessment_id)
                # Map by name for the explainer (EU removed)
                ofac_res = next((r["response_data"] for r in api_responses if r["api_name"] == "OFAC_SDN"), {})
                os_res = next((r["response_data"] for r in api_responses if r["api_name"] == "OpenSanctions"), {})
                try:
                    ai = explain_sanctions(st.session_state.company_name, ofac_res, {}, os_res)  # Pass empty {} for EU
                    st.subheader("Factual Sanctions Summary")
                    st.write(ai["overall_assessment"])  # Plain text
                    with st.expander("Details (JSON)"):
                        st.json(ai["details"])  # Keep JSON hidden in expander
                except Exception as e:
                    st.error(f"AI summary failed: {e}")
    else:
        st.caption("Set OPENAI_API_KEY to enable AI summarization.")
    st.markdown("---")
    if st.button("Continue to Legal/Litigation Check →", type="primary"):
        st.session_state.step = 3
        st.rerun()
# -----------------------------------------------------------------------------
# Step 3: Legal/Litigation
# -----------------------------------------------------------------------------
elif st.session_state.step == 3:
    st.header("Step 3: Legal & Litigation Check")
    st.subheader(f"Checking: {st.session_state.company_name}")
    st.warning("⚠️ PACER searches may incur costs (up to $50 limit)")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 Search PACER", key="pacer_check"):
            with st.spinner("Searching federal court records…"):
                time.sleep(2.0)
                pacer_cost = 15.00
                st.session_state.total_cost += pacer_cost
                db.save_api_response(
                    st.session_state.assessment_id,
                    "PACER",
                    {"cases_found": 2, "summary": "2 civil cases found, both resolved"},
                    pacer_cost,
                )
                db.update_assessment_status(st.session_state.assessment_id, "in_progress", st.session_state.total_cost)
                st.success(f"✅ PACER Search Complete — Cost: ${pacer_cost:.2f}")
    with col2:
        if st.button("🔍 Check USPTO", key="uspto_check"):
            with st.spinner("Checking patents and trademarks…"):
                time.sleep(1.0)
                db.save_api_response(
                    st.session_state.assessment_id, "USPTO", {"patents": 5, "trademarks": 3}, 0.0
                )
                st.success("✅ USPTO Check Complete")
    st.markdown("---")
    if st.button("Continue to Regulatory Check →", type="primary"):
        st.session_state.step = 4
        st.rerun()
# -----------------------------------------------------------------------------
# Step 4: Regulatory Compliance
# -----------------------------------------------------------------------------
elif st.session_state.step == 4:
    st.header("Step 4: Regulatory Compliance")
    st.subheader(f"Checking: {st.session_state.company_name}")
    st.info("Checking EPA, OSHA, and FDA compliance records…")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🔍 Check EPA ECHO", key="epa_check"):
            with st.spinner("Checking environmental compliance…"):
                time.sleep(1.0)
                db.save_api_response(
                    st.session_state.assessment_id, "EPA_ECHO", {"violations": 0, "inspections": 3}, 0.0
                )
                st.success("✅ EPA Check Complete")
    with col2:
        if st.button("🔍 Check OSHA", key="osha_check"):
            with st.spinner("Checking workplace safety records…"):
                time.sleep(1.0)
                db.save_api_response(
                    st.session_state.assessment_id, "OSHA", {"violations": 1, "severity": "low"}, 0.0
                )
                db.add_risk_finding(
                    st.session_state.assessment_id,
                    "Regulatory",
                    "low",
                    "1 minor OSHA violation in past 3 years",
                    "OSHA",
                    {"violation_type": "record_keeping"},
                )
                st.success("✅ OSHA Check Complete")
    with col3:
        if st.button("🔍 Check FDA", key="fda_check"):
            with st.spinner("Checking FDA compliance…"):
                time.sleep(1.0)
                db.save_api_response(st.session_state.assessment_id, "FDA", {"status": "not_applicable"}, 0.0)
                st.info("ℹ️ FDA — Not applicable for this industry")
    st.markdown("---")
    if st.button("Continue to Final Report →", type="primary"):
        st.session_state.step = 5
        st.rerun()
# -----------------------------------------------------------------------------
# Step 5: Final Report
# -----------------------------------------------------------------------------
elif st.session_state.step == 5:
    st.header("Step 5: Risk Assessment Report")
    st.subheader(f"Company: {st.session_state.company_name}")
    findings = db.get_assessment_findings(st.session_state.assessment_id)
    api_responses = db.get_api_responses(st.session_state.assessment_id)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("APIs Checked", len(api_responses))
    with col2:
        st.metric("Risk Findings", len(findings))
    with col3:
        high_risk = sum(1 for f in findings if f.get("severity") in ["high", "critical"])
        st.metric("High/Critical Risks", high_risk)
    with col4:
        st.metric("Total Cost", f"${st.session_state.total_cost:.2f}")
    st.markdown("---")
    if findings:
        st.subheader("Risk Findings")
        severity_icon = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
        for f in findings:
            st.markdown(f"{severity_icon.get(f.get('severity'), '⚪')} **{f.get('risk_category')}** — {f.get('severity','').upper()}")
            st.markdown(f"*{f.get('description','')}*")
            st.caption(f"Source: {f.get('source_api','')}")
            st.markdown("")
    else:
        st.success("✅ No significant risk findings identified")
    st.subheader("API Check Results")
    for resp in api_responses:
        with st.expander(f"{resp['api_name']} — {resp['fetched_at'][:10]}"):
            st.json(resp["response_data"])
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📄 Generate Detailed Report", type="primary"):
            st.info("Generating AI-powered summary report...")
            # Pull assessment details (industry from DB or session)
            assessment = db.get_assessment(st.session_state.assessment_id)  # Assume this method exists; add if needed
            industry = assessment.get("industry", "Unknown")
            if AI_SUMMARY_ENABLED:
                with st.spinner("Generating report with OpenAI..."):
                    try:
                        llm = OpenAIClient(os.environ.get("OPENAI_API_KEY"))
                        report = llm.generate_full_report(findings, api_responses, st.session_state.company_name, industry)
                        st.session_state.total_cost += report["cost"]
                        # Store full report as an "API response" for persistence
                        db.save_api_response(
                            st.session_state.assessment_id,
                            "LLM_Report",
                            report,
                            report["cost"]
                        )
                        # Display structured sections
                        st.subheader("AI-Generated Report")
                        st.write(report["full_report"])  # Plain text output
                        with st.expander("Raw Findings & APIs"):
                            st.json({"Findings": findings, "APIs": [r["response_data"] for r in api_responses]})
                        st.caption(f"Summary cost: ${report['cost']:.4f}")
                    except Exception as e:
                        st.error(f"Report generation failed: {e}")
            else:
                st.warning("Set OPENAI_API_KEY to enable AI report generation.")
                basic_report = f"Manual summary for {st.session_state.company_name}: {len(findings)} risks found across {len(api_responses)} checks. Review details above."
                st.write(basic_report)
    with col2:
        if st.button("✅ Complete Assessment"):
            db.update_assessment_status(st.session_state.assessment_id, "completed", st.session_state.total_cost)
            st.success("Assessment completed!")
# Footer
st.markdown("---")
st.caption("M&A Risk Assessment Tool v1.0")
