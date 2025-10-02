import os
from src.llm.openai_client import OpenAIClient  # Reuse your existing LLM client

def explain_sanctions(company_name: str, ofac_res: dict, os_res: dict) -> dict:
    """
    Generates a quick factual summary of sanctions data using OpenAI.
    Facts only, plain language—no risk assessments. Drills deeply into match details.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "overall_assessment": "Summary unavailable—review results manually.",
            "details": {"ofac": ofac_res, "os": os_res}
        }

    try:
        llm = OpenAIClient(api_key)
        
        # Build detailed factual context (deep dive into top 2 matches)
        ofac_facts = f"OFAC: {ofac_res.get('match_count', 0)} matches. {ofac_res.get('summary', 'No details.')}"
        if ofac_res.get('matches'):
            for i, m in enumerate(ofac_res['matches'][:2], 1):
                name = m.get('name', 'Unknown')
                desc = m.get('description', '')
                score = m.get('match_score', 0)
                ofac_facts += f" Match {i}: {name} (score: {score:.2f}). {desc}."
        
        # For OpenSanctions: Deep extract top 2
        os_matches = os_res.get("matches", [])
        os_details = ""
        if os_matches:
            avg_score = sum(m.get("match_score", 0) for m in os_matches) / len(os_matches)
            for i, m in enumerate(os_matches[:2], 1):
                name = m.get('name', 'Unknown')
                country = m.get('country', 'Unknown')
                programs = ', '.join(m.get('programs', []))
                desc = m.get('description', '')
                id_ = m.get('id', '')
                url = m.get('url', '')
                os_details += f" Match {i}: {name} (ID: {id_}, country: {country}, programs: {programs}, score: {m.get('match_score', 0):.2f}). {desc} {url if url else ''}."
            os_details += f" Average confidence across all: {avg_score:.2f}."
        else:
            os_details = "No matches found."
        os_facts = f"OpenSanctions: {os_res.get('match_count', 0)} results. {os_details}"
        
        findings_text = f"{ofac_facts}. {os_facts}."
        
        # Prompt to expand on details
        prompt = f"""
        Summarize sanctions check facts for "{company_name}" in plain English. Just the details—no risk opinions or assessments.
        
        Data:
        {findings_text}
        
        Output: 5-8 short bullets, one per key fact or match. Drill deep: Include full names, IDs, countries, programs, descriptions, scores, and URLs/dates if available. Under 300 words. Neutral list format.
        Example: "- OFAC Match 1: Wagner Group (score: 0.95). Description: Armed group in Ukraine. - OpenSanctions Match 1: PMC Wagner (ID: os-wagner-1, Russia, ru-ukraine). Full desc: Private military entity est. 2014. URL: opensanctions.org/entities/os-wagner-1."
        """
        
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=350,  # Higher for depth
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
