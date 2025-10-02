import os
from src.llm.openai_client import OpenAIClient  # Reuse your existing LLM client

def explain_sanctions(company_name: str, ofac_res: dict, os_res: dict) -> dict:
    """
    Generates a quick factual summary of sanctions data using OpenAI.
    Facts only, plain language—no risk assessments. Drills into match details.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "overall_assessment": "Summary unavailable—review results manually.",
            "details": {"ofac": ofac_res, "os": os_res}
        }

    try:
        llm = OpenAIClient(api_key)
        
        # Build detailed factual context (drill into matches)
        ofac_facts = f"OFAC: {ofac_res.get('match_count', 0)} matches. {ofac_res.get('summary', 'No details.')}"
        if ofac_res.get('matches'):
            top_ofac = ', '.join([m.get('name', 'Unknown') for m in ofac_res['matches'][:3]])
            ofac_facts += f" Top: {top_ofac}."
        
        # For OpenSanctions: Extract top 3 matches
        os_matches = os_res.get("matches", [])
        os_details = ""
        if os_matches:
            avg_score = sum(m.get("match_score", 0) for m in os_matches) / len(os_matches)
            top_names = ', '.join([m.get('name', 'Unknown') for m in os_matches[:3]])
            programs = ', '.join(set([p for m in os_matches[:3] for p in m.get('programs', [])]))
            countries = ', '.join(set([m.get('country', 'Unknown') for m in os_matches[:3]]))
            descriptions = [m.get('description', '') for m in os_matches[:3] if m.get('description')]
            desc_str = f" Descriptions: {', '.join(descriptions[:2])}." if descriptions else ""
            os_details = f"Top matches: {top_names}. Average confidence: {avg_score:.2f}. Countries: {countries}. Programs: {programs}.{desc_str}"
        else:
            os_details = "No matches found."
        os_facts = f"OpenSanctions: {os_res.get('match_count', 0)} results. {os_details}"
        
        findings_text = f"{ofac_facts}. {os_facts}."
        
        # Prompt to drill down
        prompt = f"""
        Summarize sanctions check facts for "{company_name}" in plain English. Just the details—no risk opinions or assessments.
        
        Data:
        {findings_text}
        
        Output: 4-6 short bullets with key facts. Drill into top matches: Include names, countries, programs, descriptions, and dates if available. Under 250 words. Neutral list format.
        Example: "- OFAC: 2 matches. Top: Wagner Group, Evgeny Prigozhin. - OpenSanctions: 5 results. Top: PMC Wagner (Russia, ru-ukraine: Private military entity, est. 2014)."
        """
        
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1
        )
        
        content = response.choices[0].message.content.strip()
        
        return {
            "overall_assessment": content,
            "details": {"ofac": ofac_res, "os": os_res}
        }
        
    except Exception as e:
        return {
            "overall_assessment": f"Error: {str(e)}",
            "details": {"ofac": ofac_res, "os": os_res}
        }
