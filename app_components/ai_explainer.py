import os
from src.llm.openai_client import OpenAIClient  # Reuse your existing LLM client

def explain_sanctions(company_name: str, ofac_res: dict, os_res: dict) -> dict:
    """
    Generates a quick factual summary of sanctions data using OpenAI.
    Facts only, plain language—no risk assessments. Collects names, aliases, dates, associates, addresses, structures.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "overall_assessment": "Summary unavailable—review results manually.",
            "details": {"ofac": ofac_res, "os": os_res}
        }

    try:
        llm = OpenAIClient(api_key)
        
        # Build detailed factual context (deep dive into top 2 matches, no scores)
        ofac_facts = f"OFAC: {ofac_res.get('match_count', 0)} matches. {ofac_res.get('summary', 'No details.')}"
        if ofac_res.get('matches'):
            for i, m in enumerate(ofac_res['matches'][:2], 1):
                name = m.get('name', 'Unknown')
                aliases = ', '.join(m.get('altnames', m.get('aliases', []))) if m.get('altnames') or m.get('aliases') else 'No aliases'
                sanction_date = m.get('sanction_date', m.get('listing_date', 'Unknown date'))
                addresses = m.get('addresses', [])  # List of dicts; take first
                address_str = f"Address: {addresses[0].get('street', '')}, {addresses[0].get('city', '')}, {addresses[0].get('country', '')}" if addresses else 'No address'
                identifiers = m.get('identifiers', [])  # e.g., business type
                structure = ', '.join([id_.get('type', '') + ': ' + id_.get('id', '') for id_ in identifiers]) if identifiers else 'No structure info'
                associates = m.get('associated_persons', m.get('related_entities', []))  # Individuals/links
                assoc_str = ', '.join([p.get('name', '') + ' (' + p.get('role', '') + ')' for p in associates[:2]]) if associates else 'No associates'
                desc = m.get('description', '')
                ofac_facts += f" Match {i}: {name} (aliases: {aliases}; sanction date: {sanction_date}; {address_str}; structure: {structure}; associates: {assoc_str}). {desc}."
        
        # For OpenSanctions: Deep extract top 2 (no scores)
        os_matches = os_res.get("matches", [])
        os_details = ""
        if os_matches:
            for i, m in enumerate(os_matches[:2], 1):
                name = m.get('name', 'Unknown')
                aliases = ', '.join(m.get('aliases', [])) if m.get('aliases') else 'No aliases'
                sanction_date = m.get('sanction_date', m.get('first_listed', 'Unknown date'))
                address = m.get('address', {})  # Dict
                address_str = f"Address: {address.get('street', '')}, {address.get('city', '')}, {address.get('country', '')}" if address else 'No address'
                related = m.get('related_entities', m.get('weakly_related', []))  # Associates
                related_str = ', '.join([r.get('name', '') + ' (' + r.get('role', '') + ')' for r in related[:2]]) if related else 'No associates'
                structure = m.get('type', 'Unknown') + ' (ownership: ' + ', '.join(m.get('ownership', [])) + ')' if m.get('ownership') else m.get('type', 'Unknown structure')
                programs = ', '.join(m.get('programs', []))
                desc = m.get('description', '')
                id_ = m.get('id', '')
                url = m.get('url', '')
                os_details += f" Match {i}: {name} (aliases: {aliases}; sanction date: {sanction_date}; {address_str}; structure: {structure}; associates: {related_str}; programs: {programs}). {desc} ID: {id_}. {url if url else ''}."
        else:
            os_details = "No matches found."
        os_facts = f"OpenSanctions: {os_res.get('match_count', 0)} results. {os_details}"
        
        findings_text = f"{ofac_facts}. {os_facts}."
        
        # Prompt focused on aliases, dates, etc.
        prompt = f"""
        Summarize sanctions check facts for "{company_name}" in plain English. Just the details—no risk opinions or assessments.
        
        Data:
        {findings_text}
        
        Output: 7-12 short bullets, one per key detail or match. Focus on: Names/aliases, sanction dates, associated individuals/entities (with roles), addresses, business structures/ownership, programs, descriptions, IDs, URLs. Under 450 words. Neutral list format.
        Example: "- OFAC Match 1: Wagner Group (aliases: PMC Wagner; sanction date: 2022-03-10; address: Moscow, RU; structure: Armed group; associates: Prigozhin (leader); desc: Ukraine conflict involvement. - OpenSanctions Match 1: PMC Wagner (sanction date: 2014; address: St. Petersburg, Russia; structure: Private company (ownership: Prigozhin); associates: Utkin (co-founder); programs: ru-ukraine; ID: os-wagner-1; URL: ...)."
        """
        
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=450,  # Higher for comprehensive details
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
