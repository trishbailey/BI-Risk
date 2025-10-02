# src/api_clients/sanctions/ofac.py
import requests
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
import time

class OFACClient:
    """
    Client for searching OFAC's Specially Designated Nationals (SDN) list.
    This is FREE and requires no API key.
    """
    
    def __init__(self):
        # OFAC provides multiple formats - we'll use the JSON format
        self.sdn_url = "https://www.treasury.gov/ofac/downloads/sdn_advanced.xml"
        # Alternative: Use their API endpoint (better for our use case)
        self.api_base = "https://sanctionslistservice.ofac.treas.gov/api/PublicSearchAPI"
        
    def search_company(self, company_name: str, threshold: float = 0.8) -> Dict[str, Any]:
        """
        Search for a company in the OFAC SDN list.
        
        Args:
            company_name: Name of the company to search
            threshold: Minimum match score (0-1) to consider a match
            
        Returns:
            Dictionary with search results and any matches
        """
        try:
            # Clean the company name
            cleaned_name = self._clean_company_name(company_name)
            
            # Search using the OFAC API
            results = self._search_sdn_api(cleaned_name)
            
            # Process results
            matches = []
            for result in results:
                score = self._calculate_match_score(cleaned_name, result.get('name', ''))
                if score >= threshold:
                    matches.append({
                        'name': result.get('name'),
                        'match_score': round(score, 2),
                        'type': result.get('type', 'Unknown'),
                        'programs': result.get('programs', []),
                        'addresses': result.get('addressList', []),
                        'aliases': result.get('akaList', []),
                        'ids': result.get('idList', []),
                        'source': 'OFAC SDN',
                        'list_date': result.get('publishDate'),
                        'remarks': result.get('remarks', '')
                    })
            
            return {
                'searched_name': company_name,
                'status': 'found_matches' if matches else 'clear',
                'matches': matches,
                'match_count': len(matches),
                'search_timestamp': datetime.now().isoformat(),
                'api_cost': 0.0  # Free API
            }
            
        except Exception as e:
            return {
                'searched_name': company_name,
                'status': 'error',
                'error': str(e),
                'matches': [],
                'match_count': 0,
                'search_timestamp': datetime.now().isoformat(),
                'api_cost': 0.0
            }
    
    def _search_sdn_api(self, name: str) -> List[Dict]:
        """
        Search using OFAC's public search API
        """
        # OFAC's search endpoint
        search_url = f"{self.api_base}/search"
        
        # Parameters for the search
        params = {
            'name': name,
            'type': 'Entity',  # Focus on entities (companies) not individuals
            'minScore': 80,    # OFAC's internal minimum score
            'limit': 50
        }
        
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'M&A-Risk-Assessment-Tool'
        }
        
        try:
            response = requests.get(
                search_url, 
                params=params, 
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('results', [])
            else:
                # Fallback to downloading the full list if API fails
                return self._search_downloaded_list(name)
                
        except requests.exceptions.RequestException:
            # Fallback to downloaded list
            return self._search_downloaded_list(name)
    
    def _search_downloaded_list(self, name: str) -> List[Dict]:
        """
        Fallback: Download and search the consolidated SDN list
        """
        # Use the JSON format which is easier to parse
        json_url = "https://www.treasury.gov/ofac/downloads/sanctions/1.0/sdn_advanced.json"
        
        try:
            response = requests.get(json_url, timeout=60)
            if response.status_code == 200:
                data = response.json()
                
                results = []
                # Search through the entries
                for entry in data.get('entries', []):
                    if entry.get('type') in ['Entity', 'Vessel']:  # Companies and vessels
                        entry_name = entry.get('name', '')
                        if self._is_potential_match(name, entry_name):
                            results.append(entry)
                
                return results
            
        except Exception:
            return []
        
        return []
    
    def _clean_company_name(self, name: str) -> str:
        """
        Clean and normalize company name for searching
        """
        # Convert to uppercase (OFAC format)
        name = name.upper()
        
        # Remove common suffixes that might not match exactly
        suffixes = [
            ' INC', ' LLC', ' LTD', ' LIMITED', ' CORP', ' CORPORATION',
            ' COMPANY', ' CO', ' PLC', ' SA', ' AG', ' GMBH', ' BV'
        ]
        
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()
        
        # Remove special characters but keep spaces
        name = re.sub(r'[^\w\s]', ' ', name)
        
        # Remove extra spaces
        name = ' '.join(name.split())
        
        return name
    
    def _calculate_match_score(self, search_name: str, found_name: str) -> float:
        """
        Calculate similarity score between two company names
        """
        # Simple approach - can be enhanced with fuzzy matching
        search_clean = self._clean_company_name(search_name)
        found_clean = self._clean_company_name(found_name)
        
        # Exact match
        if search_clean == found_clean:
            return 1.0
        
        # Check if one contains the other
        if search_clean in found_clean or found_clean in search_clean:
            return 0.9
        
        # Word overlap
        search_words = set(search_clean.split())
        found_words = set(found_clean.split())
        
        if not search_words or not found_words:
            return 0.0
        
        overlap = len(search_words & found_words)
        total = len(search_words | found_words)
        
        return overlap / total if total > 0 else 0.0
    
    def _is_potential_match(self, search_name: str, entry_name: str) -> bool:
        """
        Quick check if names might match (for filtering large lists)
        """
        search_clean = self._clean_company_name(search_name)
        entry_clean = self._clean_company_name(entry_name)
        
        # Check if any significant word matches
        search_words = {w for w in search_clean.split() if len(w) > 3}
        entry_words = {w for w in entry_clean.split() if len(w) > 3}
        
        return bool(search_words & entry_words)
    
    def check_multiple_companies(self, company_names: List[str]) -> List[Dict[str, Any]]:
        """
        Check multiple companies (batch processing)
        """
        results = []
        
        for company in company_names:
            # Add small delay to be respectful to free service
            time.sleep(0.5)
            result = self.search_company(company)
            results.append(result)
        
        return results


# Example usage and testing
if __name__ == "__main__":
    # Test the OFAC client
    client = OFACClient()
    
    # Test with a known sanctioned entity (for testing)
    test_companies = [
        "Your Company Name",  # Replace with actual company
        "Rosneft",  # Known sanctioned entity for testing
        "Apple Inc"  # Clean company for testing
    ]
    
    for company in test_companies:
        print(f"\nSearching for: {company}")
        result = client.search_company(company)
        
        if result['status'] == 'clear':
            print(f"✅ {company} - CLEAR (no OFAC matches)")
        elif result['status'] == 'found_matches':
            print(f"⚠️  {company} - FOUND {result['match_count']} potential matches:")
            for match in result['matches']:
                print(f"   - {match['name']} (score: {match['match_score']})")
        else:
            print(f"❌ {company} - ERROR: {result.get('error')}")
