import requests
import json
from typing import Dict, List, Any
from datetime import datetime
import os

class OpenSanctionsClient:
    """Client for OpenSanctions API - Global sanctions/PEP search (paid tier)."""
    
    BASE_URL = "https://api.opensanctions.org"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENSANCTIONS_API_KEY")
        if not self.api_key:
            raise ValueError("OpenSanctions API key required for paid access.")
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "M&A-Risk-Tool/1.0",
            "Content-Type": "application/json",
            "Authorization": f"ApiKey {self.api_key}"  # Auth header per docs
        })
    
    def search_company(self, company_name: str) -> Dict[str, Any]:
        """
        Searches for company using paid matching endpoint.
        Returns: Dict with status, matches (with confidence), cost=0 (track via billing).
        """
        try:
            # Use /match for paid tier: Better for entity resolution
            url = f"{self.BASE_URL}/match/default"
            payload = {
                "queries": {
                    "company_query": {
                        "schema": "LegalEntity",  # Focus on companies
                        "properties": {
                            "name": [company_name],
                            "country": []  # Optional: Add known countries
                        }
                    }
                }
            }
            
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            # Parse responses (paid returns structured matches with confidence)
            responses = data.get("responses", {})
            query_results = responses.get("company_query", {}).get("results", [])
            
            matches = []
            for result in query_results:
                match = {
                    "name": result.get("label", company_name),
                    "match_score": result.get("confidence", 0.0),  # Paid confidence score (0-1)
                    "country": result.get("country", ""),
                    "programs": result.get("topics", []),  # e.g., ["sanction.linked", "ru-ukraine"]
                    "id": result.get("id", ""),
                    "description": result.get("caption", "Matched sanctioned entity"),
                    "url": f"https://www.opensanctions.org/entities/{result.get('id', '')}/"
                }
                if any("sanction" in topic for topic in match["programs"]):
                    match["sanctioned"] = True
                matches.append(match)
            
            status = "found_matches" if matches else "clear"
            summary = f"Paid match query: {len(matches)} high-confidence results for '{company_name}' (avg score: {sum(m['match_score'] for m in matches)/len(matches):.2f} if matches else 0)."
            
            return {
                "status": status,
                "matches": matches,
                "match_count": len(matches),
                "search_timestamp": datetime.now().isoformat(),
                "summary": summary,
                "api_cost": 0.10,  # €0.10 per call; adjust based on your plan or response metadata
                "raw_results": query_results[:5]  # Truncate
            }
            
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                return {"status": "error", "error": "Invalid API key—check your OpenSanctions key.", "matches": [], "api_cost": 0.0}
            else:
                return {"status": "error", "error": f"HTTP {response.status_code}: {e}", "matches": [], "api_cost": 0.0}
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "matches": [],
                "api_cost": 0.0
            }
