import streamlit as st
from typing import Dict, Any

def render_sanctions_result(api_name: str, result: Dict[str, Any]):
    """
    Renders sanctions API results in a user-friendly format.
    Displays status, matches (if any), and key details.
    """
    status = result.get("status", "unknown")
    matches = result.get("matches", [])
    error = result.get("error")
    cost = result.get("api_cost", 0.0)

    st.caption(f"**{api_name}** — Cost: ${cost:.4f}")

    if status == "clear":
        st.success("✅ No matches found — Clear for this list.")
    elif status == "found_matches":
        st.info(f"⚠️ Found {len(matches)} potential match(es). Review below.")
        for i, match in enumerate(matches[:5], 1):  # Limit to top 5
            with st.expander(f"Match #{i}: {match.get('name', 'Unknown')} (Score: {match.get('match_score', 0):.2f})"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**Details:**")
                    st.write(match.get("description", "No description available."))
                    if match.get("programs"):
                        st.write(f"**Programs:** {', '.join(match.get('programs', []))}")
                    if match.get("country"):
                        st.write(f"**Country:** {match.get('country')}")
                with col2:
                    st.write("**Raw Data:**")
                    st.json({k: v for k, v in match.items() if k not in ["name", "description", "programs", "country"]})
                    if match.get("id") or match.get("url"):
                        st.write("**Source:** [View on Official Site]({})".format(match.get("url", "#")))
        if len(matches) > 5:
            st.caption(f"... and {len(matches) - 5} more matches.")
    elif status == "error":
        st.error(f"❌ Error: {error}")
    else:
        st.warning(f"ℹ️ Status: {status} — {result.get('summary', 'No summary available.')}")

    # Add a small gap
    st.markdown("---")
