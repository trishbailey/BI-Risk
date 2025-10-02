import os
from src.llm.openai_client import OpenAIClient  # Reuse your existing LLM client

def explain_sanctions(company_name: str, ofac_res: dict, os_res: dict) -> dict:
    """
    Generates a quick factual summary of sanctions data using OpenAI.
    Facts only, plain language—no risk assessments.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "overall_assessment": "Summary unavailable—review results manually.",
            "details": {"ofac": ofac_res, "os": os_res}
        }

    try:
        llm = OpenAIClient(api_key)
        
        # Build factual context 
        ofac_facts = f"OFAC: {ofac_res.get('summary', 'No results')}"
        os_facts = f"OpenSanctions: {os_res.get('summary', 'No results')}"
        
        findings_text = f"{ofac_facts}. {os_facts}."
        
        # Reuse client but with sanctions-specific prompt
        prompt = f"""
        Summarize sanctions check facts for "{company_name}" in plain English. Just the details—no risk opinions.
        
        Data:
        {findings_text}
        
        Output: 2-3 short sentences or bullets with key facts (e.g., number of matches, sources). Under 150 words.
        """
        
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
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
