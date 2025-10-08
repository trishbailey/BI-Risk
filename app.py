import os
import time
from datetime import datetime
import streamlit as st
from src.database import SupabaseManager

# === Optional AI summary (safe to disable if no API key) ===
# NOTE: In a real environment, you must ensure OPENAI_API_KEY is set in your environment variables or secrets.
AI_SUMMARY_ENABLED = bool(os.environ.get("OPENAI_API_KEY"))

try:
    if AI_SUMMARY_ENABLED:
        from app_components.ai_explainer import (
            explain_ofac, explain_os, explain_sanctions, explain_batch
        )
    else:
        explain_ofac = explain_os = explain_sanctions = explain_batch = None
except Exception as e:
    # If the file is missing or import fails, disable AI and keep the app running
    AI_SUMMARY_ENABLED = False
    explain_ofac = explain_os = explain_sanctions = explain_batch = None
    st.warning(f"AI summarization disabled: {e}")

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
    "ofac_page": 1, # Added for completeness
    "os_page": 1,   # Added for completeness
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
        # NOTE: This relies on SUPABASE_URL and SUPABASE_KEY being set in your Streamlit secrets or environment.
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

# Navigation
st.sidebar.markdown("---")
if st.sidebar.button("Go to Step 1"):
    st.session_state.step = 1
    st.rerun()
if st.session_state.assessment_id and st.sidebar.button("Go to Step 2: Sanctions"):
    st.session_state.step = 2
    st.rerun()
if st.session_state.assessment_id and st.session_state.get('ofac_result') and st.session_state.get('os_result') and st.sidebar.button("Go to Step 3: Report"):
    st.session_state.step = 3
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
                # Check for existing assessment for this company
                existing_assessment = db.get_assessment_by_company(company_name)  # Query by company_name, return latest
                if existing_assessment:
                    assessment_id = existing_assessment['id']
                    st.session_state.assessment_id = assessment_id
                    st.session_state.company_name = company_name
                    st.session_state.step = existing_assessment.get('last_step', 2)  # Resume from last step
                    st.session_state.total_cost = existing_assessment.get('total_cost', 0.0)
                    
                    # Load cached data
                    api_responses = db.get_api_responses(assessment_id)
                    st.session_state.ofac_result = next((r["response_data"] for r in api_responses if r["api_name"] == "OFAC_SDN"), {})
                    st.session_state.os_result = next((r["response_data"] for r in api_responses if r["api_name"] == "OpenSanctions"), {})
                    st.session_state.ofac_summary = next((r["response_data"].get("summary", "") for r in api_responses if r["api_name"] == "OFAC_Summary"), "")
                    st.session_state.os_summary = next((r["response_data"].get("summary", "") for r in api_responses if r["api_name"] == "OpenSanctions_Summary"), "")
                    st.session_state.combined_summary = next((r["response_data"].get("combined", "") for r in api_responses if r["api_name"] == "Combined_Summary"), {})
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
                    st.success("New assessment created! Proceeding to Step 2.")
                
                st.rerun()
            except Exception as e:
                st.error(f"Error with assessment: {str(e)}")

# -----------------------------------------------------------------------------
# Step 2: Sanctions Check
# -----------------------------------------------------------------------------
elif st.session_state.step == 2:
    if not st.session_state.assessment_id:
        st.error("Please complete Step 1 first.")
        st.stop()
        
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
    except Exception as e:
        st.error(f"OpenSanctions client import error: {e}")
        opensanctions_available = False
    
    # Define columns at the top of the block to ensure scope
    col1, col2 = st.columns(2)
    
    # --- OFAC Section ---
    with col1:
        # Initialize pagination if not set (done in state_defaults, but kept here for clarity)
        if 'ofac_page' not in st.session_state:
            st.session_state.ofac_page = 1
        
        ofac_res = st.session_state.get('ofac_result', {})
        match_count = ofac_res.get('match_count', 0)
        current_page = st.session_state.ofac_page
        batch_size = 10
        remaining = max(0, match_count - (current_page * batch_size))
        
        # Persistent OFAC summary (initial + batches)
        if st.session_state.get('ofac_summary'):
            st.subheader("OFAC Summary")
            st.code(st.session_state.ofac_summary, language="markdown") # Using st.code to preserve formatting
        
        # Pagination button (dynamic label)
        if match_count > 0 and AI_SUMMARY_ENABLED:
            if remaining > 0:
                if st.button(f"Display More OFAC ({remaining} left)", key="more_ofac"):
                    with st.spinner("Generating next batch summary…"):
                        # NOTE: The implementation of explain_batch must handle the data slicing
                        batch_summary = explain_batch(st.session_state.company_name, ofac_res, (current_page - 1) * batch_size, batch_size, "OFAC")
                        st.session_state.ofac_summary += f"\n\n--- Next Batch Summary ---\n{batch_summary}"
                        st.session_state.ofac_page += 1
                        st.session_state.total_cost += 0.002 # Example cost
                        db.update_assessment_cost(st.session_state.assessment_id, st.session_state.total_cost)
                        st.rerun()
            elif current_page > 1:
                st.info("All OFAC results summarized.")
        elif match_count > 0 and not AI_SUMMARY_ENABLED:
            st.warning("AI Summary disabled. Cannot paginate/summarize results.")

        # --- Initial OFAC Button ---
        if st.button("🔍 Run OFAC SDN Check", key="ofac_check"):
            with st.spinner("Checking OFAC…"):
                if ofac_available:
                    try:
                        client = OFACClient()
                        ofac_res = client.search_company(st.session_state.company_name)
                        
                        # CRITICAL FIX: Store result in session state
                        st.session_state.ofac_result = ofac_res
                        
                        # Save raw result to DB
                        db.save_api_response(st.session_state.assessment_id, "OFAC_SDN", ofac_res)
                        
                        if AI_SUMMARY_ENABLED:
                            with st.spinner("Generating initial OFAC summary…"):
                                # Generate initial summary (for the first batch or all if small)
                                summary = explain_ofac(st.session_state.company_name, ofac_res)
                                st.session_state.ofac_summary = summary
                                st.session_state.total_cost += 0.005 # Example cost for initial summary
                                db.save_api_response(st.session_state.assessment_id, "OFAC_Summary", {"summary": summary})
                                db.update_assessment_cost(st.session_state.assessment_id, st.session_state.total_cost)
                        else:
                            st.session_state.ofac_summary = f"OFAC Check Complete. Match count: {ofac_res.get('match_count', 0)}. AI Summary is disabled."
                            
                        st.session_state.ofac_page = 1 # Reset page for fresh display
                        st.rerun()
                    except Exception as e:
                        st.error(f"OFAC search error: {str(e)}")
                else:
                    st.warning("OFAC client is not available. Please check dependencies.")

    # --- OpenSanctions Section ---
    with col2:
        # Initialize pagination if not set (done in state_defaults, but kept here for clarity)
        if 'os_page' not in st.session_state:
            st.session_state.os_page = 1
            
        os_res = st.session_state.get('os_result', {})
        match_count = os_res.get('match_count', 0)
        current_page = st.session_state.os_page
        
        # Persistent OS summary (initial + batches)
        if st.session_state.get('os_summary'):
            st.subheader("OpenSanctions Summary")
            st.code(st.session_state.os_summary, language="markdown")
            
        # Pagination button (dynamic label)
        remaining = max(0, match_count - (current_page * batch_size))
        if match_count > 0 and AI_SUMMARY_ENABLED:
            if remaining > 0:
                if st.button(f"Display More OpenSanctions ({remaining} left)", key="more_os"):
                    with st.spinner("Generating next batch summary…"):
                        batch_summary = explain_batch(st.session_state.company_name, os_res, (current_page - 1) * batch_size, batch_size, "OpenSanctions")
                        st.session_state.os_summary += f"\n\n--- Next Batch Summary ---\n{batch_summary}"
                        st.session_state.os_page += 1
                        st.session_state.total_cost += 0.002 # Example cost
                        db.update_assessment_cost(st.session_state.assessment_id, st.session_state.total_cost)
                        st.rerun()
            elif current_page > 1:
                st.info("All OpenSanctions results summarized.")
        elif match_count > 0 and not AI_SUMMARY_ENABLED:
            st.warning("AI Summary disabled. Cannot paginate/summarize results.")
            
        # --- Initial OpenSanctions Button ---
        if st.button("🌍 Run OpenSanctions Check", key="os_check"):
            with st.spinner("Checking OpenSanctions…"):
                if opensanctions_available:
                    try:
                        client = OpenSanctionsClient()
                        os_res = client.search_company(st.session_state.company_name)
                        
                        st.session_state.os_result = os_res
                        db.save_api_response(st.session_state.assessment_id, "OpenSanctions", os_res)
                        
                        if AI_SUMMARY_ENABLED:
                            with st.spinner("Generating initial OpenSanctions summary…"):
                                summary = explain_os(st.session_state.company_name, os_res)
                                st.session_state.os_summary = summary
                                st.session_state.total_cost += 0.005 # Example cost for initial summary
                                db.save_api_response(st.session_state.assessment_id, "OpenSanctions_Summary", {"summary": summary})
                                db.update_assessment_cost(st.session_state.assessment_id, st.session_state.total_cost)
                        else:
                            st.session_state.os_summary = f"OpenSanctions Check Complete. Match count: {os_res.get('match_count', 0)}. AI Summary is disabled."

                        st.session_state.os_page = 1 # Reset page for fresh display
                        st.rerun()
                    except Exception as e:
                        st.error(f"OpenSanctions search error: {str(e)}")
                else:
                    st.warning("OpenSanctions client is not available. Please check dependencies.")

    st.markdown("---")
    # Move to next step only if both checks have results
    if st.session_state.get('ofac_result', {}) and st.session_state.get('os_result', {}):
        if st.button("✅ Proceed to Step 3: Report Generation", type="primary"):
            # Update last step in DB (optional, but good practice for resuming)
            db.update_assessment_step(st.session_state.assessment_id, 3) 
            st.session_state.step = 3
            st.rerun()
    elif st.session_state.get('ofac_result') or st.session_state.get('os_result'):
        st.info("Please run both Sanctions checks before proceeding to the Report.")


# -----------------------------------------------------------------------------
# Step 3: Report Generation
# -----------------------------------------------------------------------------
elif st.session_state.step == 3:
    st.header("Step 3: Comprehensive Risk Report")
    st.subheader(f"Final Report for: {st.session_state.company_name}")
    
    if not AI_SUMMARY_ENABLED:
        st.error("AI Summary is disabled. Cannot generate comprehensive report.")
        st.info("To generate the final report, please set the `OPENAI_API_KEY` environment variable.")
        st.stop()
        
    if st.button("⚡ Generate Comprehensive M&A Report", type="primary"):
        with st.spinner("Generating final report and combined summary (This may take a minute)…"):
            try:
                # 1. Combine all current results
                full_data = {
                    "company_name": st.session_state.company_name,
                    "ofac": st.session_state.ofac_result,
                    "opensanctions": st.session_state.os_result,
                    "ofac_summary": st.session_state.ofac_summary,
                    "os_summary": st.session_state.os_summary
                    # Add other data sources as needed (e.g., reputational, financial checks)
                }
                
                # 2. Call the master explainer/reporter
                combined_report, cost = explain_sanctions(full_data) # Assuming explain_sanctions generates the full report and returns its cost
                
                # 3. Store result
                st.session_state.combined_summary = combined_report
                db.save_api_response(st.session_state.assessment_id, "Combined_Summary", {"combined": combined_report})
                
                # 4. Update cost
                st.session_state.total_cost += cost
                db.update_assessment_cost(st.session_state.assessment_id, st.session_state.total_cost)

                st.success("Report successfully generated!")
                st.rerun()

            except Exception as e:
                st.error(f"Error generating final report: {str(e)}")
                
    if st.session_state.get('combined_summary'):
        st.markdown("---")
        st.subheader("Report Summary")
        st.markdown(st.session_state.combined_summary)
        
        # Optionally provide a download button for the report
        st.download_button(
            label="Download Full M&A Risk Report",
            data=st.session_state.combined_summary,
            file_name=f"MA_Risk_Report_{st.session_state.company_name}_{datetime.now().strftime('%Y%m%d')}.md",
            mime="text/markdown"
        )
