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
        # OFAC's new Sanctions List Service (SLS) endpoints
        self.sls_base = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports"
        # Direct download URLs for the SDN list
        self.sdn_json_url = f"{self.sls_base}/SDN_ADVANCED.JSON"
        self.sdn_xml_url = f"{self.sls_base}/SDN_ADVANCED.XML"
        # CSV format is often easier to parse
        self.sdn_csv_url = f"{self.sls_base}/SDN.CSV"
        
    def search_company(self, company_name: str, threshold: float = 0.7) -> Dict[str, Any]:
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
            
            # For now, go straight to downloading the list since the API seems unreliable
            results = self._search_downloaded_list(cleaned_name)
            
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
                # Always use the fallback for now
                print(f"OFAC API returned status {response.status_code}, using fallback")
                return self._search_downloaded_list(name)
                
        except requests.exceptions.RequestException as e:
            # Fallback to downloaded list
            print(f"OFAC API error: {str(e)}, using fallback")
            return self._search_downloaded_list(name)
    
    def _search_downloaded_list(self, name: str) -> List[Dict]:
        """
        Download and search the OFAC SDN list directly
        """
        try:
            # Try JSON format first
            response = requests.get(self.sdn_json_url, timeout=60)
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                # The structure might be different, let's check what we get
                if isinstance(data, dict):
                    # Look for the entries/records
                    entries = data.get('entries', data.get('records', data.get('data', [])))
                elif isinstance(data, list):
                    entries = data
                else:
                    entries = []
                
                # Search through entries
                for entry in entries:
                    # Skip individuals, focus on entities
                    if entry.get('type') in ['Entity', 'Vessel'] or entry.get('sdnType') == 'Entity':
                        entry_name = entry.get('name', entry.get('lastName', ''))
                        if self._is_potential_match(name, entry_name):
                            results.append(entry)
                
                return results
                
        except Exception as e:
            print(f"Error downloading SDN list: {str(e)}")
            
        # If JSON fails, try CSV format
        try:
            response = requests.get(self.sdn_csv_url, timeout=60)
            if response.status_code == 200:
                # Parse CSV manually
                lines = response.text.strip().split('\n')
                results = []
                
                for line in lines[1:]:  # Skip header
                    fields = line.split('","')
                    if len(fields) > 2:
                        # Check if entity (not individual)
                        sdn_type = fields[2].strip('"') if len(fields) > 2 else ''
                        if sdn_type == 'Entity':
                            name_field = fields[1].strip('"') if len(fields) > 1 else ''
                            if self._is_potential_match(name, name_field):
                                results.append({
                                    'name': name_field,
                                    'type': sdn_type,
                                    'programs': [fields[11].strip('"')] if len(fields) > 11 else []
                                })
                
                return results
                
        except Exception as e:
            print(f"Error downloading CSV: {str(e)}")
            
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
