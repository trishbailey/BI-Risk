import os
from src.llm.openai_client import OpenAIClient  # Reuse your existing LLM client

def explain_sanctions(company_name: str, ofac_res: dict, eu_res: dict, os_res: dict) -> dict:
    """
    Generates a quick AI summary of sanctions findings using OpenAI.
    Returns: Dict with 'overall_assessment', 'risk_level', and details.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "overall_assessment": "AI summary unavailable—review results manually.",
            "risk_level": "UNKNOWN",
            "details": {"ofac": ofac_res, "eu": eu_res, "os": os_res}
        }

    try:
        llm = OpenAIClient(api_key)
        
        # Build simple context (mock "findings" and "api_responses" for this mini-summary)
        findings = []  # For sanctions, derive from results
        if ofac_res.get("matches"):
            findings.append({"risk_category": "Sanctions", "severity": "high", "description": f"{len(ofac_res['matches'])} OFAC matches", "source_api": "OFAC"})
        if eu_res.get("matches"):
            findings.append({"risk_category": "Sanctions", "severity": "high", "description": f"{len(eu_res['matches'])} EU matches", "source_api": "EU"})
        if os_res.get("matches"):
            findings.append({"risk_category": "Sanctions", "severity": "high", "description": f"{len(os_res['matches'])} OpenSanctions matches", "source_api": "OpenSanctions"})
        
        api_responses = [
            {"api_name": "OFAC", "response_data": ofac_res},
            {"api_name": "EU", "response_data": eu_res},
            {"api_name": "OpenSanctions", "response_data": os_res}
        ]
        
        # Reuse the full report method but with a sanctions-focused prompt override
        report = llm.generate_full_report(findings, api_responses, company_name, "General")
        
        return {
            "overall_assessment": report["full_report"][:300] + "..." if len(report["full_report"]) > 300 else report["full_report"],  # Truncate for quick view
            "risk_level": report["overall_risk_score"],
            "details": {"ofac": ofac_res, "eu": eu_res, "os": os_res}
        }
        
    except Exception as e:
        return {
            "overall_assessment": f"Error: {str(e)}",
            "risk_level": "ERROR",
            "details": {"ofac": ofac_res, "eu": eu_res, "os": os_res}
        }
