# app_components/ai_explainer.py
from __future__ import annotations
import os, json
from typing import Dict, Any, Tuple

try:
    from openai import OpenAI
    _HAS_OPENAI = True
except Exception:
    _HAS_OPENAI = False

# ---- tiny helper ------------------------------------------------------------

def _safe_client():
    if not _HAS_OPENAI:
        return None
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)

def _truncate(obj: Any, max_chars: int = 180000) -> str:
    s = json.dumps(obj, ensure_ascii=False)
    return s[:max_chars]

# ---- per-source explainers (return markdown strings) ------------------------

def explain_ofac(query_name: str, ofac_result: Dict[str, Any]) -> str:
    """
    Summarize OFAC result into short Markdown. If no OpenAI key, return a basic summary.
    """
    client = _safe_client()
    if not client:
        mc = ofac_result.get("match_count", 0)
        status = ofac_result.get("status", "unknown")
        return f"**OFAC Summary** — {query_name}\n\nStatus: `{status}`; matches: **{mc}**."
    prompt = (
        "You are an OSINT compliance analyst. Summarize the OFAC screening output concisely. "
        "Use ONLY the provided JSON. "
        "Output: 5–8 bullet points with entity names, match scores, and key programs. "
        "If there are no matches, say 'Clear'.\n\n"
        f"Data:\n{_truncate(ofac_result)}"
    )
    resp = client.responses.create(model="gpt-4o-mini", temperature=0, input=prompt)
    return resp.output_text

def explain_os(query_name: str, os_result: Dict[str, Any]) -> str:
    client = _safe_client()
    if not client:
        mc = os_result.get("match_count", 0)
        status = os_result.get("status", "unknown")
        return f"**OpenSanctions Summary** — {query_name}\n\nStatus: `{status}`; matches: **{mc}**."
    prompt = (
        "Summarize OpenSanctions screening concisely using ONLY the provided JSON. "
        "Output: 5–8 bullets with entity names, scores, sources (e.g., EU/UN/UK), and programs."
        f"\n\nData:\n{_truncate(os_result)}"
    )
    resp = client.responses.create(model="gpt-4o-mini", temperature=0, input=prompt)
    return resp.output_text

def explain_batch(query_name: str, source_result: Dict[str, Any], offset: int, limit: int, source_name: str) -> str:
    """
    Summarize a slice of matches [offset:offset+limit] from a given source result.
    """
    client = _safe_client()
    matches = (source_result or {}).get("matches", [])
    batch = matches[offset: offset + limit]
    if not client:
        return f"**{source_name} batch** {offset}-{offset+len(batch)}: {len(batch)} item(s)."
    prompt = (
        f"Summarize these {source_name} matches concisely using ONLY the provided JSON. "
        "Output: 3–6 bullets with entity names, scores, and key evidence."
        f"\n\nData:\n{_truncate(batch)}"
    )
    resp = client.responses.create(model="gpt-4o-mini", temperature=0, input=prompt)
    return resp.output_text

# ---- combined report --------------------------------------------------------

def explain_sanctions(full_data: Dict[str, Any]) -> Tuple[str, float]:
    """
    Produce a combined Markdown report for the app's Step 3. Returns (report_md, approximate_cost).
    If no OpenAI key, return a deterministic summary and zero cost.
    """
    client = _safe_client()
    if not client:
        cn = full_data.get("company_name", "N/A")
        ofac = full_data.get("ofac", {})
        os_ = full_data.get("opensanctions", {})
        md = (
            f"# M&A Risk Report — {cn}\n\n"
            f"**OFAC:** status `{ofac.get('status','unknown')}`, matches {ofac.get('match_count',0)}.\n\n"
            f"**OpenSanctions:** status `{os_.get('status','unknown')}`, matches {os_.get('match_count',0)}.\n\n"
            "_AI disabled — enable OPENAI_API_KEY for full narrative._"
        )
        return md, 0.0

    prompt = (
        "You are an OSINT compliance analyst writing a concise M&A sanctions screening section. "
        "Use ONLY the provided JSON. Be direct, evidence-based, and avoid speculation. "
        "Output markdown with sections: Executive Summary, OFAC, OpenSanctions, Consolidated Assessment, Caveats."
        f"\n\nData:\n{_truncate(full_data)}"
    )
    resp = client.responses.create(model="gpt-4o-mini", temperature=0, input=prompt)
    return resp.output_text, 0.01  # simple fixed cost estimate; replace with your own accounting
