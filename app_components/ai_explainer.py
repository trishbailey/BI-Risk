import os
from src.llm.openai_client import OpenAIClient  # Reuse your existing LLM client

def explain_ofac(company_name: str, ofac_res: dict) -> str:
    """
    Generates a detailed plain-text summary for OFAC results only.
    Facts only, extracts all relevant info into sensible paragraphs/bullets. Limits to top 10 matches.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "Summary unavailable—review results manually."

    try:
        llm = OpenAIClient(api_key)
        
        # Build detailed factual context (limit to top 10 matches to avoid timeout)
        match_count = ofac_res.get('match_count', 0)
        ofac_facts = f"OFAC results for '{company_name}': {match_count} matches. {ofac_res.get('summary', 'No details.')}"
        if ofac_res.get('matches'):
            # Sort by score if available, else take first 10
            matches = sorted(ofac_res['matches'], key=lambda m: m.get('match_score', 0), reverse=True)[:10]
            for i, m in enumerate(matches, 1):
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
            
            if match_count > 10:
                ofac_facts += f" And {match_count - 10} more similar Gazprom-related entities."
        
        prompt = f"""
        Turn the following OFAC data for '{company_name}' into a detailed, plain-text summary in simple English. Just the facts—no opinions.
        
        Data:
        {ofac_facts}
        
        Output: 6-12 bullets or short paragraphs with all relevant info: Names/aliases, sanction dates, addresses, business structures/ownership, associated individuals (with roles), descriptions, IDs, URLs. Make it readable and sensible, like a briefing note. Under 400 words.
        """
        
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.1
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        return f"Error summarizing OFAC: {str(e)}"

def explain_os(company_name: str, os_res: dict) -> str:
    """
    Generates a detailed plain-text summary for OpenSanctions results only.
    Facts only, extracts all relevant info into sensible paragraphs/bullets. Limits to top 10 matches.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "Summary unavailable—review results manually."

    try:
        llm = OpenAIClient(api_key)
        
        # Build detailed factual context (limit to top 10 matches to avoid timeout)
        match_count = os_res.get('match_count', 0)
        os_facts = f"OpenSanctions results for '{company_name}': {match_count} matches. {os_res.get('summary', 'No details.')}"
        if os_res.get('matches'):
            # Sort by score if available, else take first 10
            matches = sorted(os_res['matches'], key=lambda m: m.get('match_score', 0), reverse=True)[:10]
            for i, m in enumerate(matches, 1):
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
            
            if match_count > 10:
                os_facts += f" And {match_count - 10} more similar entities."
        
        prompt = f"""
        Turn the following OpenSanctions data for '{company_name}' into a detailed, plain-text summary in simple English. Just the facts—no opinions.
        
        Data:
        {os_facts}
        
        Output: 6-12 bullets or short paragraphs with all relevant info: Names/aliases, sanction dates, addresses, business structures/ownership, associated individuals (with roles), programs, descriptions, IDs, URLs. Make it readable and sensible, like a briefing note. Under 400 words.
        """
        
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.1
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        return f"Error summarizing OpenSanctions: {str(e)}"

def explain_sanctions(company_name: str, ofac_res: dict, os_res: dict) -> str:
    """
    Generates a combined plain-text summary for both OFAC and OpenSanctions.
    Facts only, merges into one cohesive briefing. Limits to top 10 per API.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "Summary unavailable—review results manually."

    try:
        llm = OpenAIClient(api_key)
        
        # Build combined factual context (top 10 per API)
        combined_facts = f"Sanctions results for '{company_name}': OFAC: {ofac_res.get('match_count', 0)} matches. {ofac_res.get('summary', 'No details.')}. OpenSanctions: {os_res.get('match_count', 0)} matches. {os_res.get('summary', 'No details.')}"
        
        # OFAC top 10
        if ofac_res.get('matches'):
            matches = sorted(ofac_res['matches'], key=lambda m: m.get('match_score', 0), reverse=True)[:10]
            for i, m in enumerate(matches, 1):
                name = m.get('name', 'Unknown')
                aliases = ', '.join(m.get('altnames', m.get('aliases', []))) if m.get('altnames') or m.get('aliases') else 'No aliases'
                sanction_date = m.get('sanction_date', m.get('listing_date', 'Unknown date'))
                address_str = '; '.join([f"{a.get('street', '')}, {a.get('city', '')}, {a.get('country', '')}" for a in m.get('addresses', [])[:2]]) if m.get('addresses') else 'No address'
                structure = ', '.join([f"{id_.get('type', '')}: {id_.get('id', '')}" for id_ in m.get('identifiers', [])]) if m.get('identifiers') else 'No structure info'
                assoc_str = ', '.join([f"{p.get('name', '')} ({p.get('role', '')})" for p in m.get('associated_persons', m.get('related_entities', []))]) if m.get('associated_persons') or m.get('related_entities') else 'No associates'
                desc = m.get('description', '')
                id_ = m.get('id', '')
                url = m.get('url', '')
                combined_facts += f" OFAC Match {i}: {name} (aliases: {aliases}; sanction date: {sanction_date}; {address_str}; structure: {structure}; associates: {assoc_str}). {desc} ID: {id_}. {url if url else ''}."
        
        # OpenSanctions top 10
        if os_res.get('matches'):
            matches = sorted(os_res['matches'], key=lambda m: m.get('match_score', 0), reverse=True)[:10]
            for i, m in enumerate(matches, 1):
                name = m.get('name', 'Unknown')
                aliases = ', '.join(m.get('aliases', [])) if m.get('aliases') else 'No aliases'
                sanction_date = m.get('sanction_date', m.get('first_listed', 'Unknown date'))
                address_str = f"{m.get('address', {}).get('street', '')}, {m.get('address', {}).get('city', '')}, {m.get('address', {}).get('country', '')}" if m.get('address') else 'No address'
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
        
        Output: 8-15 bullets or short paragraphs merging both sources. Include all relevant info: Names/aliases, sanction dates, addresses, business structures/ownership, associated individuals (with roles), programs, descriptions, IDs, URLs. Make it readable and sensible, like a briefing note. Under 500 words.
        """
        
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.1
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        return f"Error summarizing both: {str(e)}"
def explain_batch(company_name: str, res: dict, start_idx: int, batch_size: int = 10, api_name: str = "OFAC") -> str:
    """
    Generates a plain-text summary for a batch of matches (e.g., 11-20).
    For pagination in large result sets.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return f"{api_name} batch summary unavailable."

    try:
        llm = OpenAIClient(api_key)
        
        matches = res.get("matches", [])
        end_idx = min(start_idx + batch_size, len(matches))
        batch_matches = matches[start_idx:end_idx]
        
        if not batch_matches:
            return f"No more {api_name} matches to summarize."
        
        batch_facts = f"{api_name} batch for '{company_name}' (matches {start_idx+1}-{end_idx}):"
        for i, m in enumerate(batch_matches, start_idx + 1):
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
            batch_facts += f" Match {i}: {name} (aliases: {aliases}; sanction date: {sanction_date}; addresses: {address_str}; structure: {structure}; associates: {assoc_str}). {desc} ID: {id_}. {url if url else ''}."
        
        prompt = f"""
        Turn this batch of {api_name} data for '{company_name}' into a detailed, plain-text summary in simple English. Just the facts—no opinions.
        
        Data:
        {batch_facts}
        
        Output: 4-8 bullets or short paragraphs with all relevant info: Names/aliases, sanction dates, addresses, business structures/ownership, associated individuals (with roles), descriptions, IDs, URLs. Make it readable, like a briefing note. Under 300 words.
        """
        
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        return f"Error summarizing {api_name} batch: {str(e)}"
