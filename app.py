import os
import time
from datetime import datetime
import streamlit as st
from src.database import SupabaseManager
# === Optional AI summary (safe to disable if no API key) ===
AI_SUMMARY_ENABLED = bool(os.environ.get("OPENAI_API_KEY"))
# AI explainer functions (no renderers needed now)
if AI_SUMMARY_ENABLED:
    from app_components.ai_explainer import explain_ofac, explain_os, explain_sanctions, explain_batch
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
                # NEW: Check for existing assessment for this company
                existing_assessment = db.get_assessment_by_company(company_name)  # Assume this method queries 'assessments' by company_name, returns latest incomplete or completed
                if existing_assessment:
                    assessment_id = existing_assessment['id']
                    st.session_state.assessment_id = assessment_id
                    st.session_state.company_name = company_name
                    st.session_state.step = existing_assessment.get('last_step', 2)  # Resume from last step
                    st.session_state.total_cost = existing_assessment.get('total_cost', 0.0)
                    # Load cached data
                    st.session_state.ofac_result = next((r["response_data"] for r in db.get_api_responses(assessment_id) if r["api_name"] == "OFAC_SDN"), {})
                    st.session_state.os_result = next((r["response_data"] for r in db.get_api_responses(assessment_id) if r["api_name"] == "OpenSanctions"), {})
                    st.session_state.ofac_summary = next((r["response_data"].get("summary", "") for r in db.get_api_responses(assessment_id) if r["api_name"] == "OFAC_Summary"), "")
                    st.session_state.os_summary = next((r["response_data"].get("summary", "") for r in db.get_api_responses(assessment_id) if r["api_name"] == "OpenSanctions_Summary"), {})
                    st.session_state.combined_summary = next((r["response_data"].get("combined", "") for r in db.get_api_responses(assessment_id) if r["api_name"] == "Combined_Summary"), "")
                    st.success(f"Resuming previous assessment for {company_name} (from Step {st.session_state.step}).")
                else:
                    # Create new
                    assessment_id = db.create_assessment(
                        company_name=company_name,
                        industry=industry or None,
                        created_by="user",
                    )
                    st.session_state.assessment_id = assessment_id
                    st.session_state.company_name = company_name
                    st.session_state.step = 2
                    st.success("New assessment created!")
                st.rerun()
            except Exception as e:
                st.error(f"Error with assessment: {str(e)}")
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
   
    # Define columns at the top of the block to ensure scope
    col1, col2 = st.columns(2)
   
    # OFAC Section (persistent summary + pagination button)
    with col1:
        # Initialize pagination if not set
        if 'ofac_page' not in st.session_state:
            st.session_state.ofac_page = 1
            st.session_state.ofac_full_matches = []  # Store all matches
       
        # Persistent OFAC summary (initial + batches)
        if st.session_state.get('ofac_summary'):
            st.subheader("OFAC Summary")
            st.write(st.session_state.ofac_summary)
       
        # Pagination button (dynamic label)
        ofac_res = st.session_state.get('ofac_result
