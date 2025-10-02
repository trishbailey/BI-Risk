# app_components/sanctions_render.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple
from datetime import datetime
import streamlit as st
import html

def esc(x: Any) -> str:
    """HTML-escape helper."""
    return html.escape("" if x is None else str(x))

def _chip(text: str) -> str:
    return f"""<span style="
        display:inline-block; padding:4px 8px; margin:2px 6px 2px 0;
        border-radius:999px; font-size:12px; line-height:12px;
        border:1px solid rgba(0,0,0,0.15)
    ">{esc(text)}</span>"""

def _clean_list(values: List[str]) -> List[str]:
    seen, out = set(), []
    for v in values or []:
        v = (v or "").strip()
        if v and v not in seen:
            seen.add(v); out.append(v)
    return out

def _clean_addresses(addrs: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out = []
    for a in addrs or []:
        a = {k: (a.get(k) or "").strip() for k in ["address1","address2","city","state","postal_code","country"]}
        if any(a.values()):
            out.append(a)
    return out

def _extract_warnings_from_ids(ids: List[Dict[str, str]]) -> Tuple[List[str], List[Dict[str, str]]]:
    warnings, clean = [], []
    for i in ids or []:
        t = (i.get("type") or "").lower()
        v = (i.get("value") or "").strip()
        if "secondary sanctions risk" in t or v.lower().startswith("secondary sanctions risk"):
            if v: warnings.append(v)
        elif v:
            clean.append({"type": i.get("type") or "", "value": v})
    return _clean_list(warnings), clean

def _risk_badge(score: float, programs: List[str]) -> str:
    p = {p.upper() for p in programs or []}
    severe = {"SDGT","SDNTK","TCO","IRAN","IRAN-EO13224","RUSSIA-EO14024","DPRK"}
    base, color = "Low", "#0E7C66"
    if score >= 0.95 or (p & severe):
        base, color = "High", "#B00020"
    elif score >= 0.85:
        base, color = "Elevated", "#C77D00"
    return f"""<span style="
        background:{color}1A; color:{color}; border:1px solid {color}66;
        padding:4px 8px; border-radius:6px; font-weight:600; font-size:12px;
    ">{base} match</span>"""

def _fmt_date(dt: str) -> str:
    if not dt:
        return ""
    try:
        return datetime.fromisoformat(dt.replace("Z","")).strftime("%d %b %Y")
    except Exception:
        return dt

def _open_card():
    st.markdown(
        """
        <div style="
            border:1px solid #ddd; border-radius:10px;
            padding:14px 16px; margin:14px 0; background:#fff;
        ">""",
        unsafe_allow_html=True,
    )

def _close_card():
    st.markdown("</div>", unsafe_allow_html=True)

def render_sanctions_result(source_label: str, result: Dict[str, Any]) -> None:
    st.subheader(f"Sanctions Check — {esc(source_label)}")

    status = result.get("status")
    name = result.get("searched_name", "")
    ts = result.get("search_timestamp", "")
    if name or ts:
        st.caption(f"Searched: **{esc(name)}** • {esc(ts)}")

    if status == "error":
        st.error(f"Error: {esc(result.get('error','Unknown error'))}")
        return

    matches = result.get("matches", [])
    if status == "clear" or not matches:
        st.success("No matches were found.")
        return

    st.warning(f"Found {result.get('match_count', len(matches))} potential match(es).")

    for m in matches:
        _open_card()

        title = m.get("name") or "(no name)"
        st.markdown(f"### {esc(title)}")

        score = float(m.get("match_score") or 0.0)
        programs = _clean_list(m.get("programs") or [])

        header_cols = st.columns([1, 1, 1, 1])
        with header_cols[0]:
            st.markdown(_risk_badge(score, programs), unsafe_allow_html=True)
        with header_cols[1]:
            st.metric("Match score", f"{score:.2f}")
        with header_cols[2]:
            st.write("Type"); st.code(m.get("type",""), language=None)
        with header_cols[3]:
            ref = m.get("sdn_number") or m.get("eu_reference") or ""
            st.write("Ref/ID"); st.code(ref, language=None)

        if programs:
            st.write("Programs")
            st.markdown("".join(_chip(p) for p in programs), unsafe_allow_html=True)

        warnings, clean_ids = _extract_warnings_from_ids(m.get("ids") or [])
        if warnings:
            st.info("**Secondary sanctions risk**\n\n- " + "\n- ".join(esc(w) for w in warnings))

        aliases = _clean_list(m.get("aliases") or [])
        if aliases:
            with st.expander(f"Aliases ({len(aliases)})"):
                st.write("\n".join(f"- {esc(a)}" for a in aliases))

        addrs = _clean_addresses(m.get("addresses") or [])
        if addrs:
            with st.expander(f"Addresses ({len(addrs)})"):
                for a in addrs:
                    line = ", ".join([x for x in [
                        a.get("address1"), a.get("address2"), a.get("city"),
                        a.get("state"), a.get("postal_code"), a.get("country")
                    ] if x])
                    st.write(f"- {esc(line)}")

        if clean_ids:
            with st.expander(f"Identifiers ({len(clean_ids)})"):
                for i in clean_ids:
                    t = (i.get("type") or "").strip() or "ID"
                    v = i.get("value","")
                    st.write(f"- **{esc(t)}:** {esc(v)}")

        remarks = (m.get("remarks") or m.get("remark") or "").strip()
        pub = _fmt_date(m.get("publishDate","") or m.get("listing_date",""))
        foot = []
        if pub: foot.append(f"Published/Listed: {esc(pub)}")
        if remarks: foot.append(f"Remarks: {esc(remarks)}")
        if foot:
            st.caption(" • ".join(foot))

        _close_card()
