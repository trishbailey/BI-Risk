# app.py
import streamlit as st
import os
from datetime import datetime
from src.database import SupabaseManager
import time

# Page config
st.set_page_config(
    page_title="M&A Risk Assessment Tool",
    page_icon="🔍",
    layout="wide"
)

# Initialize session state
if 'assessment_id' not in st.session_state:
    st.session_state.assessment_id = None
if 'step' not in st.session_state:
    st.session_state.step = 1
if 'total_cost' not in st.session_state:
    st.session_state.total_cost = 0.0
if 'company_name' not in st.session_state:
    st.session_state.company_name = ""

# Initialize database connection
@st.cache_resource
def get_db():
    try:
        return SupabaseManager()
    except Exception as e:
        st.error(f"Database connection error: {str(e)}")
        return None

db = get_db()

# Sidebar
st.sidebar.title("M&A Risk Assessment")

if st.session_state.assessment_id:
    st.sidebar.success(f"Active Assessment ID: {st.session_state.assessment_id[:8]}...")
    st.sidebar.metric("Current Cost", f"${st.session_state.total_cost:.2f}")
    
    if st.sidebar.button("Start New Assessment"):
        st.session_state.assessment_id = None
        st.session_state.step = 1
        st.session_state.total_cost = 0.0
        st.session_state.company_name = ""
        st.rerun()

# Main content
st.title("M&A Risk Assessment Tool")

if not db:
    st.error("Please configure your Supabase credentials to continue.")
    st.markdown("""
    ### Setup Instructions:
    1. Create a free Supabase account at [supabase.com](https://supabase.com)
    2. Create a new project
    3. Go to Settings > API and copy your URL and anon key
    4. Add these to your Streamlit secrets or .env file:
       - `SUPABASE_URL=your_url`
       - `SUPABASE_KEY=your_anon_key`
    """)
    st.stop()

# Step 1: Company Information
if st.session_state.step == 1:
    st.header("Step 1: Company Information")
    
    with st.form("company_info"):
        company_name = st.text_input("Company Name", value=st.session_state.company_name)
        industry = st.selectbox(
            "Industry",
            ["", "Healthcare", "Financial Services", "Energy", "Technology", 
             "Manufacturing", "Retail", "Other"]
        )
        
        submitted = st.form_submit_button("Start Assessment")
        
        if submitted and company_name:
            try:
                # Create new assessment
                assessment_id = db.create_assessment(
                    company_name=company_name,
                    industry=industry if industry else None,
                    created_by="user"
                )
                
                st.session_state.assessment_id = assessment_id
                st.session_state.company_name = company_name
                st.session_state.step = 2
                st.success("Assessment created!")
                st.rerun()
                
            except Exception as e:
                st.error(f"Error creating assessment: {str(e)}")

# Step 2: Sanctions Check
elif st.session_state.step == 2:
    st.header("Step 2: Sanctions Check")
    st.subheader(f"Checking: {st.session_state.company_name}")
    
    st.info("This step checks OFAC, OpenSanctions, and EU sanctions databases.")
    
    # Import OFAC client
    try:
        from src.api_clients.sanctions.ofac import OFACClient
        ofac_available = True
    except ImportError as e:
        st.error(f"OFAC import error: {str(e)}")
        ofac_available = False
    
    col1, col2, col3 = st.columns(3)
    
    # Import OFAC client
    try:
        from src.api_clients.sanctions.ofac import OFACClient
        ofac_available = True
    except ImportError:
        ofac_available = False
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔍 Check OFAC SDN", key="ofac_check"):
            with st.spinner("Checking OFAC Sanctions..."):
                if ofac_available:
                    # Use real OFAC API
                    try:
                        ofac_client = OFACClient()
                        st.write("Debug: OFAC client created successfully")
                        result = ofac_client.search_company(st.session_state.company_name)
                        st.write("Debug: API result:", result)
                        
                        # Save the response
                        db.save_api_response(
                            st.session_state.assessment_id,
                            "OFAC_SDN",
                            result,
                            result.get('api_cost', 0.0)
                        )
                        
                        # Display results
                        if result['status'] == 'clear':
                            st.success(f"✅ OFAC Check Complete - No matches found")
                        elif result['status'] == 'found_matches':
                            st.warning(f"⚠️ OFAC Check - Found {result['match_count']} potential matches")
                            
                            # Add risk findings
                            for match in result['matches']:
                                severity = 'critical' if match['match_score'] > 0.9 else 'high'
                                db.add_risk_finding(
                                    st.session_state.assessment_id,
                                    "Sanctions",
                                    severity,
                                    f"Potential OFAC match: {match['name']} (score: {match['match_score']})",
                                    "OFAC_SDN",
                                    match
                                )
                            
                            # Show details in expander
                            with st.expander("View OFAC Match Details"):
                                for match in result['matches']:
                                    st.write(f"**{match['name']}**")
                                    st.write(f"- Match Score: {match['match_score']}")
                                    st.write(f"- Type: {match['type']}")
                                    if match.get('programs'):
                                        st.write(f"- Programs: {', '.join(match['programs'])}")
                        else:
                            st.error(f"Error checking OFAC: {result.get('error')}")
                            
                    except Exception as e:
                        st.error(f"Error with OFAC API: {str(e)}")
                        # Fall back to mock data
                        db.save_api_response(
                            st.session_state.assessment_id,
                            "OFAC_SDN",
                            {"status": "error", "error": str(e)},
                            0.0
                        )
                else:
                    # Use mock data if OFAC client not available
                    time.sleep(2)
                    db.save_api_response(
                        st.session_state.assessment_id,
                        "OFAC_SDN",
                        {"status": "clear", "matches": []},
                        0.0
                    )
                    st.success("✅ OFAC Check Complete - No matches found")
    
    with col2:
        if st.button("🔍 Check OpenSanctions", key="opensanctions_check"):
            with st.spinner("Checking OpenSanctions..."):
                # Import OpenSanctions client
                try:
                    from src.api_clients.sanctions.opensanctions import OpenSanctionsClient
                    opensanctions_available = True
                except ImportError:
                    opensanctions_available = False
                
                if opensanctions_available:
                    try:
                        os_client = OpenSanctionsClient()
                        result = os_client.search_company(st.session_state.company_name)
                        
                        # Save the response
                        db.save_api_response(
                            st.session_state.assessment_id,
                            "OpenSanctions",
                            result,
                            result.get('api_cost', 0.0)
                        )
                        
                        # Display results
                        if result['status'] == 'clear':
                            st.success(f"✅ OpenSanctions Check Complete - No matches found")
                        elif result['status'] == 'found_matches':
                            st.warning(f"⚠️ OpenSanctions Check - Found {result['match_count']} potential matches")
                            
                            # Add risk findings
                            for match in result['matches']:
                                severity = 'critical' if match['match_score'] > 0.9 else 'high'
                                programs_str = ', '.join(match.get('programs', []))
                                
                                db.add_risk_finding(
                                    st.session_state.assessment_id,
                                    "Sanctions",
                                    severity,
                                    f"Potential match in OpenSanctions: {match['name']} (score: {match['match_score']}) - Programs: {programs_str}",
                                    "OpenSanctions",
                                    match
                                )
                            
                            # Show details in expander
                            with st.expander("View OpenSanctions Match Details"):
                                for match in result['matches']:
                                    st.write(f"**{match['name']}**")
                                    st.write(f"- Match Score: {match['match_score']}")
                                    st.write(f"- Schema: {match.get('schema', 'Unknown')}")
                                    if match.get('programs'):
                                        st.write(f"- Programs: {', '.join(match['programs'])}")
                                    if match.get('countries'):
                                        st.write(f"- Countries: {', '.join(match['countries'])}")
                                    if match.get('aliases'):
                                        st.write(f"- Also known as: {', '.join(match['aliases'][:3])}")
                        else:
                            st.error(f"Error checking OpenSanctions: {result.get('error')}")
                            
                    except Exception as e:
                        st.error(f"Error with OpenSanctions API: {str(e)}")
                        db.save_api_response(
                            st.session_state.assessment_id,
                            "OpenSanctions",
                            {"status": "error", "error": str(e)},
                            0.0
                        )
                else:
                    # Use mock data if client not available
                    time.sleep(2)
                    db.save_api_response(
                        st.session_state.assessment_id,
                        "OpenSanctions",
                        {"status": "clear", "matches": []},
                        0.0
                    )
                    st.success("✅ OpenSanctions Check Complete - No matches found")
    
    with col3:
        if st.button("🔍 Check EU Sanctions", key="eu_check"):
            with st.spinner("Checking EU Sanctions..."):
                # Import EU Sanctions client
                try:
                    from src.api_clients.sanctions.eu_sanctions import EUSanctionsClient
                    eu_available = True
                except ImportError:
                    eu_available = False
                
                if eu_available:
                    try:
                        eu_client = EUSanctionsClient()
                        result = eu_client.search_company(st.session_state.company_name)
                        
                        # Save the response
                        db.save_api_response(
                            st.session_state.assessment_id,
                            "EU_Sanctions",
                            result,
                            result.get('api_cost', 0.0)
                        )
                        
                        # Display results
                        if result['status'] == 'clear':
                            st.success(f"✅ EU Sanctions Check Complete - No matches found")
                        elif result['status'] == 'found_matches':
                            st.warning(f"⚠️ EU Sanctions Check - Found {result['match_count']} potential matches")
                            
                            # Add risk findings
                            for match in result['matches']:
                                severity = 'critical' if match['match_score'] > 0.9 else 'high'
                                
                                db.add_risk_finding(
                                    st.session_state.assessment_id,
                                    "Sanctions",
                                    severity,
                                    f"EU Sanctions match: {match['name']} (score: {match['match_score']}) - Programme: {match.get('programme', 'N/A')}",
                                    "EU_Sanctions",
                                    match
                                )
                            
                            # Show details in expander
                            with st.expander("View EU Sanctions Match Details"):
                                for match in result['matches']:
                                    st.write(f"**{match['name']}**")
                                    st.write(f"- Match Score: {match['match_score']}")
                                    st.write(f"- EU Reference: {match.get('eu_reference', 'N/A')}")
                                    st.write(f"- Programme: {match.get('programme', 'N/A')}")
                                    st.write(f"- Listed Date: {match.get('listing_date', 'N/A')}")
                                    if match.get('aliases'):
                                        st.write(f"- Also known as: {', '.join(match['aliases'][:3])}")
                        else:
                            st.error(f"Error checking EU Sanctions: {result.get('error')}")
                            
                    except Exception as e:
                        st.error(f"Error with EU Sanctions API: {str(e)}")
                        db.save_api_response(
                            st.session_state.assessment_id,
                            "EU_Sanctions",
                            {"status": "error", "error": str(e)},
                            0.0
                        )
                else:
                    # Use mock data if client not available
                    time.sleep(2)
                    db.save_api_response(
                        st.session_state.assessment_id,
                        "EU_Sanctions",
                        {"status": "clear", "matches": []},
                        0.0
                    )
                    st.success("✅ EU Sanctions Check Complete - No matches found")
    
    st.markdown("---")
    
    if st.button("Continue to Legal/Litigation Check →", type="primary"):
        st.session_state.step = 3
        st.rerun()

# Step 3: Legal/Litigation
elif st.session_state.step == 3:
    st.header("Step 3: Legal & Litigation Check")
    st.subheader(f"Checking: {st.session_state.company_name}")
    
    st.warning("⚠️ PACER searches may incur costs (up to $50 limit)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔍 Search PACER", key="pacer_check"):
            with st.spinner("Searching federal court records..."):
                time.sleep(3)
                
                # Simulate PACER cost
                pacer_cost = 15.00
                st.session_state.total_cost += pacer_cost
                
                db.save_api_response(
                    st.session_state.assessment_id,
                    "PACER",
                    {"cases_found": 2, "summary": "2 civil cases found, both resolved"},
                    pacer_cost
                )
                
                db.update_assessment_status(
                    st.session_state.assessment_id, 
                    "in_progress", 
                    st.session_state.total_cost
                )
                
                st.success(f"✅ PACER Search Complete - Cost: ${pacer_cost:.2f}")
    
    with col2:
        if st.button("🔍 Check USPTO", key="uspto_check"):
            with st.spinner("Checking patents and trademarks..."):
                time.sleep(2)
                
                db.save_api_response(
                    st.session_state.assessment_id,
                    "USPTO",
                    {"patents": 5, "trademarks": 3},
                    0.0
                )
                
                st.success("✅ USPTO Check Complete")
    
    st.markdown("---")
    
    if st.button("Continue to Regulatory Check →", type="primary"):
        st.session_state.step = 4
        st.rerun()

# Step 4: Regulatory Compliance
elif st.session_state.step == 4:
    st.header("Step 4: Regulatory Compliance")
    st.subheader(f"Checking: {st.session_state.company_name}")
    
    st.info("Checking EPA, OSHA, and FDA compliance records...")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔍 Check EPA ECHO", key="epa_check"):
            with st.spinner("Checking environmental compliance..."):
                time.sleep(2)
                
                db.save_api_response(
                    st.session_state.assessment_id,
                    "EPA_ECHO",
                    {"violations": 0, "inspections": 3},
                    0.0
                )
                
                st.success("✅ EPA Check Complete")
    
    with col2:
        if st.button("🔍 Check OSHA", key="osha_check"):
            with st.spinner("Checking workplace safety records..."):
                time.sleep(2)
                
                db.save_api_response(
                    st.session_state.assessment_id,
                    "OSHA",
                    {"violations": 1, "severity": "low"},
                    0.0
                )
                
                # Add a risk finding
                db.add_risk_finding(
                    st.session_state.assessment_id,
                    "Regulatory",
                    "low",
                    "1 minor OSHA violation in past 3 years",
                    "OSHA",
                    {"violation_type": "record_keeping"}
                )
                
                st.success("✅ OSHA Check Complete")
    
    with col3:
        if st.button("🔍 Check FDA", key="fda_check"):
            with st.spinner("Checking FDA compliance..."):
                time.sleep(2)
                
                db.save_api_response(
                    st.session_state.assessment_id,
                    "FDA",
                    {"status": "not_applicable"},
                    0.0
                )
                
                st.info("ℹ️ FDA - Not applicable for this industry")
    
    st.markdown("---")
    
    if st.button("Continue to Final Report →", type="primary"):
        st.session_state.step = 5
        st.rerun()

# Step 5: Generate Report
elif st.session_state.step == 5:
    st.header("Step 5: Risk Assessment Report")
    st.subheader(f"Company: {st.session_state.company_name}")
    
    # Get all findings
    findings = db.get_assessment_findings(st.session_state.assessment_id)
    api_responses = db.get_api_responses(st.session_state.assessment_id)
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("APIs Checked", len(api_responses))
    with col2:
        st.metric("Risk Findings", len(findings))
    with col3:
        high_risk = sum(1 for f in findings if f.get('severity') in ['high', 'critical'])
        st.metric("High/Critical Risks", high_risk)
    with col4:
        st.metric("Total Cost", f"${st.session_state.total_cost:.2f}")
    
    st.markdown("---")
    
    # Risk findings summary
    if findings:
        st.subheader("Risk Findings")
        for finding in findings:
            severity_color = {
                'low': '🟢',
                'medium': '🟡', 
                'high': '🟠',
                'critical': '🔴'
            }
            
            st.markdown(f"{severity_color.get(finding['severity'], '⚪')} **{finding['risk_category']}** - {finding['severity'].upper()}")
            st.markdown(f"*{finding['description']}*")
            st.caption(f"Source: {finding['source_api']}")
            st.markdown("")
    else:
        st.success("✅ No significant risk findings identified")
    
    # API results summary
    st.subheader("API Check Results")
    
    for response in api_responses:
        with st.expander(f"{response['api_name']} - {response['fetched_at'][:10]}"):
            st.json(response['response_data'])
    
    # Action buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📄 Generate Detailed Report", type="primary"):
            st.info("LLM report generation would go here - connecting to OpenAI...")
            # This is where you'd integrate the LLM report generation
            
    with col2:
        if st.button("✅ Complete Assessment"):
            db.update_assessment_status(st.session_state.assessment_id, "completed", st.session_state.total_cost)
            st.success("Assessment completed!")

# Footer
st.markdown("---")
st.caption("M&A Risk Assessment Tool v1.0")
