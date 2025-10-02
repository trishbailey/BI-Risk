# src/database.py
import os
from supabase import create_client, Client
from datetime import datetime
import streamlit as st
from typing import Dict, List, Optional, Any
import json

class SupabaseManager:
    def __init__(self):
        """Initialize Supabase client using Streamlit secrets or environment variables"""
        try:
            # Try Streamlit secrets first (for deployed app)
            url = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL"))
            key = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY"))
        except:
            # Fall back to environment variables (for local development)
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_KEY")
        
        if not url or not key:
            raise ValueError("Supabase credentials not found. Please set SUPABASE_URL and SUPABASE_KEY")
        
        self.client: Client = create_client(url, key)
    
    def create_assessment(self, company_name: str, industry: str = None, created_by: str = None) -> str:
        """Create a new assessment and return its ID"""
        data = {
            "company_name": company_name,
            "industry": industry,
            "created_by": created_by,
            "status": "started"
        }
        
        response = self.client.table("assessments").insert(data).execute()
        return response.data[0]["id"]
    
    def update_assessment_status(self, assessment_id: str, status: str, total_cost: float = None):
        """Update assessment status and optionally the total cost"""
        data = {"status": status}
        if total_cost is not None:
            data["total_cost"] = total_cost
        
        self.client.table("assessments").update(data).eq("id", assessment_id).execute()
    
    def save_api_response(self, assessment_id: str, api_name: str, response_data: Any, api_cost: float = 0.0):
        """Save raw API response data"""
        # Convert response data to JSON-serializable format
        if not isinstance(response_data, (dict, list)):
            response_data = {"raw_response": str(response_data)}
        
        data = {
            "assessment_id": assessment_id,
            "api_name": api_name,
            "response_data": response_data,
            "api_cost": api_cost
        }
        
        self.client.table("api_responses").insert(data).execute()
    
    def add_risk_finding(self, assessment_id: str, risk_category: str, severity: str, 
                        description: str, source_api: str, raw_data: Dict = None):
        """Add a risk finding from API analysis"""
        data = {
            "assessment_id": assessment_id,
            "risk_category": risk_category,
            "severity": severity,
            "description": description,
            "source_api": source_api,
            "raw_data": raw_data or {}
        }
        
        self.client.table("risk_findings").insert(data).execute()
    
    def save_report_section(self, assessment_id: str, section_name: str, content: str):
        """Save a generated report section"""
        data = {
            "assessment_id": assessment_id,
            "section_name": section_name,
            "content": content
        }
        
        self.client.table("report_sections").insert(data).execute()
    
    def get_assessment(self, assessment_id: str) -> Dict:
        """Get assessment details"""
        response = self.client.table("assessments").select("*").eq("id", assessment_id).execute()
        return response.data[0] if response.data else None
    
    def get_assessment_findings(self, assessment_id: str) -> List[Dict]:
        """Get all risk findings for an assessment"""
        response = self.client.table("risk_findings").select("*").eq("assessment_id", assessment_id).execute()
        return response.data
    
    def get_api_responses(self, assessment_id: str, api_name: str = None) -> List[Dict]:
        """Get API responses for an assessment, optionally filtered by API name"""
        query = self.client.table("api_responses").select("*").eq("assessment_id", assessment_id)
        if api_name:
            query = query.eq("api_name", api_name)
        
        response = query.execute()
        return response.data
    
    def get_report_sections(self, assessment_id: str) -> List[Dict]:
        """Get all report sections for an assessment"""
        response = self.client.table("report_sections").select("*").eq("assessment_id", assessment_id).order("generated_at").execute()
        return response.data
    
    def check_rate_limit(self, api_name: str, limit_type: str = "monthly") -> Dict:
        """Check API usage against rate limits"""
        # Get current month's usage
        from datetime import datetime, timedelta
        
        if limit_type == "monthly":
            start_date = datetime.now().replace(day=1, hour=0, minute=0, second=0)
        else:  # daily
            start_date = datetime.now().replace(hour=0, minute=0, second=0)
        
        response = self.client.table("api_responses")\
            .select("id")\
            .eq("api_name", api_name)\
            .gte("fetched_at", start_date.isoformat())\
            .execute()
        
        usage_count = len(response.data)
        
        # Define rate limits
        rate_limits = {
            'opencorporates': {'monthly': 50},
            'acled': {'monthly': 500},
            'pacer': {'daily': 100}
        }
        
        limit = rate_limits.get(api_name, {}).get(limit_type, float('inf'))
        
        return {
            "usage": usage_count,
            "limit": limit,
            "remaining": max(0, limit - usage_count),
            "exceeded": usage_count >= limit
        }
    
    def get_assessment_cost(self, assessment_id: str) -> float:
        """Calculate total cost for an assessment"""
        response = self.client.table("api_responses")\
            .select("api_cost")\
            .eq("assessment_id", assessment_id)\
            .execute()
        
        total_cost = sum(row.get("api_cost", 0) for row in response.data)
        return total_cost
