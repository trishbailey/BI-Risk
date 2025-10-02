import os
from src.llm.openai_client import OpenAIClient  # Reuse your existing LLM client

def explain_ofac(company_name: str, ofac_res: dict) -> str:
    """
    Generates a detailed plain-text summary for OFAC results only.
    Facts only, extracts all relevant info into sensible paragraphs/bullets.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "Summary unavailable—review results manually."

    try:
        llm = OpenAIClient(api_key)
        
        # Build detailed factual context (deep dive into all matches, no scores)
        ofac_facts = f"OFAC results for '{company_name}': {ofac_res.get('match_count', 0)} matches. {ofac_res.get('summary', 'No details.')}"
        if ofac_res.get('matches'):
            for i, m in enumerate(ofac_res['matches'], 1):  # All matches
                name = m.get('name', 'Unknown')
                aliases = ', '.join(m.get('altnames', m.get('aliases', []))) if m.get('altnames') or m.get('aliases') else 'No aliases'
                sanction_date = m.get('sanction_date', m.get('listing_date', 'Unknown date'))
                addresses = m.get('addresses', [])  # List of dicts
                address_str = '; '.join([f"{a.get('street', '')}, {a.get('city', '')}, {a.get('country', '')}" for a in addresses[:2]]) if addresses else 'No address'
                identifiers = m.get('identifiers', [])  # Business type
                structure = ', '.join([f"{id_.get('type', '')}: {id_.get('id', '')}" for id_ in identifiers]) if identifiers else 'No structure info'
                associates = m.get('associated_persons', m.get('related_entities', []))  # Individuals
                assoc_str = ', '.join([f"{p.get('name', '')} ({p.get('role', '')})" for p in associates]) if associates else 'No associates'
                desc = m.get('description', '')
                id_ = m.get('id', '')
                url = m.get('url', '')
                ofac_facts += f" Match {i}: {name} (aliases: {aliases}; sanction date: {sanction_date}; addresses: {address_str}; structure: {structure}; associates: {assoc_str}). {desc} ID: {id_}. {url if url else ''}."
        
        prompt = f"""
        Turn the following OFAC data for '{company_name}' into a detailed, plain-text summary in simple English. Just the facts—no opinions.
        
        Data:
        {ofac_facts}
        
        Output: 4-8 bullets or short paragraphs with all relevant info: Names/aliases, sanction dates, addresses, business structures/ownership, associated individuals (with roles), descriptions, IDs, URLs. Make it readable and sensible, like a briefing note. Under 300 words.
        """
        
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        return f"Error summarizing OFAC: {str(e)}"

def explain_os(company_name: str, os_res: dict) -> str:
    """
    Generates a detailed plain-text summary for OpenSanctions results only.
    Facts only, extracts all relevant info into sensible paragraphs/bullets.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "Summary unavailable—review results manually."

    try:
        llm = OpenAIClient(api_key)
        
        # Build detailed factual context (deep dive into all matches, no scores)
        os_facts = f"OpenSanctions results for '{company_name}': {os_res.get('match_count', 0)} matches. {os_res.get('summary', 'No details.')}"
        if os_res.get('matches'):
            for i, m in enumerate(os_res['matches'], 1):  # All matches
                name = m.get('name', 'Unknown')
                aliases = ', '.join(m.get('aliases', [])) if m.get('aliases') else 'No aliases'
                sanction_date = m.get('sanction_date', m.get('first_listed', 'Unknown date'))
                address = m.get('address', {})  # Dict
                address_str = f"{address.get('street', '')}, {address.get('city', '')}, {address.get('country', '')}" if address else 'No address'
                related = m.get('related_entities', m.get('weakly_related', []))  # Associates
                related_str = ', '.join([f"{r.get('name', '')} ({r.get('role', '')})" for r in related]) if related else 'No associates'
                structure = m.get('type', 'Unknown') + ' (ownership: ' + ', '.join(m.get('ownership', [])) + ')' if m.get('ownership') else m.get('type', 'Unknown structure')
                programs = ', '.join(m.get('programs', []))
                desc = m.get('description', '')
                id_ = m.get('id', '')
                url = m.get('url', '')
                os_facts += f" Match {i}: {name} (aliases: {aliases}; sanction date: {sanction_date}; address: {address_str}; structure: {structure}; associates: {related_str}; programs: {programs}). {desc} ID: {id_}. {url if url else ''}."
        
        prompt = f"""
        Turn the following OpenSanctions data for '{company_name}' into a detailed, plain-text summary in simple English. Just the facts—no opinions.
        
        Data:
        {os_facts}
        
        Output: 4-8 bullets or short paragraphs with all relevant info: Names/aliases, sanction dates, addresses, business structures/ownership, associated individuals (with roles), programs, descriptions, IDs, URLs. Make it readable and sensible, like a briefing note. Under 300 words.
        """
        
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        return f"Error summarizing OpenSanctions: {str(e)}"

def explain_sanctions(company_name: str, ofac_res: dict, os_res: dict) -> str:
    """
    Generates a combined plain-text summary for both OFAC and OpenSanctions.
    Facts only, merges into one cohesive briefing.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "Summary unavailable—review results manually."

    try:
        llm = OpenAIClient(api_key)
        
        # Build combined factual context
        combined_facts = f"Sanctions results for '{company_name}': OFAC: {ofac_res.get('match_count', 0)} matches. {ofac_res.get('summary', 'No details.')}. OpenSanctions: {os_res.get('match_count', 0)} matches. {os_res.get('summary', 'No details.')}"
        
        # Add details from both (top 2 each)
        if ofac_res.get('matches'):
            for i, m in enumerate(ofac_res['matches'][:2], 1):
                name = m.get('name', 'Unknown')
                aliases = ', '.join(m.get('altnames', m.get('aliases', []))) if m.get('altnames') or m.get('aliases') else 'No aliases'
                sanction_date = m.get('sanction_date', m.get('listing_date', 'Unknown date'))
                address_str = f"Address: {m.get('addresses', [{}])[0].get('street', '')}, {m.get('addresses', [{}])[0].get('city', '')}, {m.get('addresses', [{}])[0].get('country', '')}" if m.get('addresses') else 'No address'
                structure = ', '.join([f"{id_.get('type', '')}: {id_.get('id', '')}" for id_ in m.get('identifiers', [])]) if m.get('identifiers') else 'No structure info'
                assoc_str = ', '.join([f"{p.get('name', '')} ({p.get('role', '')})" for p in m.get('associated_persons', m.get('related_entities', []))]) if m.get('associated_persons') or m.get('related_entities') else 'No associates'
                desc = m.get('description', '')
                id_ = m.get('id', '')
                url = m.get('url', '')
                combined_facts += f" OFAC Match {i}: {name} (aliases: {aliases}; sanction date: {sanction_date}; {address_str}; structure: {structure}; associates: {assoc_str}). {desc} ID: {id_}. {url if url else ''}."
        
        if os_res.get('matches'):
            for i, m in enumerate(os_res['matches'][:2], 1):
                name = m.get('name', 'Unknown')
                aliases = ', '.join(m.get('aliases', [])) if m.get('aliases') else 'No aliases'
                sanction_date = m.get('sanction_date', m.get('first_listed', 'Unknown date'))
                address_str = f"Address: {m.get('address', {}).get('street', '')}, {m.get('address', {}).get('city', '')}, {m.get('address', {}).get('country', '')}" if m.get('address') else 'No address'
                related_str = ', '.join([f"{r.get('name', '')} ({r.get('role', '')})" for r in m.get('related_entities', m.get('weakly_related', []))]) if m.get('related_entities') or m.get('weakly_related') else 'No associates'
                structure = m.get('type', 'Unknown') + ' (ownership: ' + ', '.join(m.get('ownership', [])) + ')' if m.get('ownership') else m.get('type', 'Unknown structure')
                programs = ', '.join(m.get('programs', []))
                desc = m.get('description', '')
                id_ = m.get('id', '')
                url = m.get('url', '')
                combined_facts += f" OpenSanctions Match {i}: {name} (aliases: {aliases}; sanction date: {sanction_date}; {address_str}; structure: {structure}; associates: {related_str}; programs: {programs}). {desc} ID: {id_}. {url if url else ''}."
        
        prompt = f"""
        Turn the following combined OFAC and OpenSanctions data for '{company_name}' into a detailed, plain-text summary in simple English. Just the facts—no opinions.
        
        Data:
        {combined_facts}
        
        Output: 6-10 bullets or short paragraphs merging both sources. Include all relevant info: Names/aliases, sanction dates, addresses, business structures/ownership, associated individuals (with roles), programs, descriptions, IDs, URLs. Make it readable and sensible, like a briefing note. Under 400 words.
        """
        
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.1
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        return f"Error summarizing both: {str(e)}"
