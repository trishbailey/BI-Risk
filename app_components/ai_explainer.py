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
        
        # Build simple context
        ofac_status = ofac_res.get("status", "clear")
        eu_status = eu_res.get("status", "clear")
        os_status = os_res.get("status", "clear")
        matches_summary = []
        if ofac_res.get("matches"):
            matches_summary.append(f"OFAC: {len(ofac_res['matches'])} potential matches")
        if eu_res.get("matches"):
            matches_summary.append(f"EU: {len(eu_res['matches'])} potential matches")
        if os_res.get("matches"):
            matches_summary.append(f"OpenSanctions: {len(os_res['matches'])} potential matches")
        
        findings_text = "; ".join(matches_summary) if matches_summary else "No matches across all lists."
        
        prompt = f"""
        Summarize sanctions risk for "{company_name}":
        - OFAC: {ofac_status}
        - EU: {eu_status}
        - OpenSanctions: {os_status}
        - Matches: {findings_text}
        
        Provide:
        - overall_assessment: 1-2 sentences on risk.
        - risk_level: LOW/MEDIUM/HIGH/CRITICAL.
        Keep under 200 words.
        """
        
        # Use a lightweight call (adapt from your client's summarize_risks if preferred)
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3
        )
        
        content = response.choices[0].message.content.strip()
        risk_level = "LOW"  # Default; parse or infer
        if any("high" in content.lower() or "critical" in content.lower() for status in [ofac_status, eu_status, os_status] if "match" in status):
            risk_level = "HIGH"
        elif matches_summary:
            risk_level = "MEDIUM"
        
        return {
            "overall_assessment": content,
            "risk_level": risk_level,
            "details": {"ofac": ofac_res, "eu": eu_res, "os": os_res}
        }
        
    except Exception as e:
        return {
            "overall_assessment": f"Error: {str(e)}",
            "risk_level": "ERROR",
            "details": {"ofac": ofac_res, "eu": eu_res, "os": os_res}
        }
