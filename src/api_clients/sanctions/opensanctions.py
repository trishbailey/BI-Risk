# src/api_clients/sanctions/opensanctions.py
import requests
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
import time

class OpenSanctionsClient:
    """
    Client for searching OpenSanctions database.
    OpenSanctions aggregates sanctions lists from around the world.
    This is FREE and requires no API key.
    """
    
    def __init__(self):
        # OpenSanctions API endpoint
        self.api_base = "https://api.opensanctions.org/v2"
        self.search_endpoint = f"{self.api_base}/search"
        self.match_endpoint = f"{self.api_base}/match"
        
    def search_company(self, company_name: str, threshold: float = 0.7) -> Dict[str, Any]:
        """
        Search for a company in OpenSanctions.
        
        Args:
            company_name: Name of the company to search
            threshold: Minimum match score (0-1) to consider a match
            
        Returns:
            Dictionary with search results and any matches
        """
        try:
            # Clean the company name
            cleaned_name = self._clean_company_name(company_name)
            
            # Search using the OpenSanctions API
            results = self._search_api(cleaned_name)
            
            # Process results
            matches = []
            for result in results:
                # OpenSanctions provides its own score
                score = result.get('score', 0) / 100  # Convert to 0-1 range
                
                if score >= threshold:
                    # Extract entity details
                    entity = result.get('entity', {})
                    properties = entity.get('properties', {})
                    
                    matches.append({
                        'name': self._get_primary_name(entity),
                        'match_score': round(score, 2),
                        'entity_id': entity.get('id'),
                        'schema': entity.get('schema'),
                        'aliases': self._get_aliases(properties),
                        'countries': properties.get('country', []),
                        'programs': self._get_sanctions_programs(entity),
                        'addresses': self._get_addresses(properties),
                        'identifiers': self._get_identifiers(properties),
                        'source': 'OpenSanctions',
                        'dataset': entity.get('datasets', []),
                        'first_seen': entity.get('first_seen'),
                        'last_seen': entity.get('last_seen'),
                        'topics': entity.get('topics', [])
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
    
    def _search_api(self, name: str) -> List[Dict]:
        """
        Search using OpenSanctions API
        """
        params = {
            'q': name,
            'schema': 'Company',  # Focus on companies, not individuals
            'limit': 20
        }
        
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'M&A-Risk-Assessment-Tool'
        }
        
        try:
            response = requests.get(
                self.search_endpoint,
                params=params,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('results', [])
            else:
                return []
                
        except requests.exceptions.RequestException:
            return []
    
    def get_entity_details(self, entity_id: str) -> Optional[Dict]:
        """
        Get detailed information about a specific entity
        """
        url = f"{self.api_base}/entities/{entity_id}"
        
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        
        return None
    
    def _clean_company_name(self, name: str) -> str:
        """
        Clean and normalize company name for searching
        """
        # Remove common suffixes
        suffixes = [
            'inc', 'llc', 'ltd', 'limited', 'corp', 'corporation',
            'company', 'co', 'plc', 'sa', 'ag', 'gmbh', 'bv',
            'nv', 'spa', 'srl', 'sarl', 'ab', 'as', 'oy'
        ]
        
        # Convert to lowercase for processing
        name_lower = name.lower().strip()
        
        # Remove punctuation
        name_clean = re.sub(r'[^\w\s]', ' ', name_lower)
        
        # Remove suffixes
        words = name_clean.split()
        while words and words[-1] in suffixes:
            words.pop()
        
        return ' '.join(words)
    
    def _get_primary_name(self, entity: Dict) -> str:
        """
        Extract the primary name from an entity
        """
        properties = entity.get('properties', {})
        names = properties.get('name', [])
        
        if names:
            return names[0]
        
        # Fallback to any available name
        for prop in ['alias', 'weakAlias', 'previousName']:
            if prop in properties and properties[prop]:
                return properties[prop][0]
        
        return entity.get('caption', 'Unknown')
    
    def _get_aliases(self, properties: Dict) -> List[str]:
        """
        Extract all aliases and alternative names
        """
        aliases = []
        
        # Collect from various alias fields
        alias_fields = ['alias', 'weakAlias', 'previousName', 'tradeName']
        
        for field in alias_fields:
            if field in properties:
                aliases.extend(properties[field])
        
        # Remove duplicates
        return list(set(aliases))
    
    def _get_sanctions_programs(self, entity: Dict) -> List[str]:
        """
        Extract sanctions programs from datasets
        """
        datasets = entity.get('datasets', [])
        programs = []
        
        # Map dataset codes to readable names
        dataset_mapping = {
            'us_ofac_sdn': 'US OFAC SDN',
            'eu_fsf': 'EU Consolidated',
            'un_sc_sanctions': 'UN Security Council',
            'gb_hmt_sanctions': 'UK Treasury',
            'ca_dfatd_sema_sanctions': 'Canada SEMA',
            'au_dfat_sanctions': 'Australia DFAT',
            'ch_seco_sanctions': 'Switzerland SECO',
            'jp_mof_sanctions': 'Japan MOF'
        }
        
        for dataset in datasets:
            readable_name = dataset_mapping.get(dataset, dataset)
            programs.append(readable_name)
        
        return programs
    
    def _get_addresses(self, properties: Dict) -> List[Dict]:
        """
        Extract and format addresses
        """
        addresses = []
        
        if 'address' in properties:
            for addr in properties['address']:
                addresses.append({'full_address': addr})
        
        # Add country information if no specific addresses
        if not addresses and 'country' in properties:
            for country in properties['country']:
                addresses.append({'country': country})
        
        return addresses
    
    def _get_identifiers(self, properties: Dict) -> List[Dict]:
        """
        Extract various identifiers (registration numbers, etc.)
        """
        identifiers = []
        
        # Common identifier fields
        id_fields = {
            'registrationNumber': 'Registration',
            'taxNumber': 'Tax ID',
            'vatCode': 'VAT',
            'dunsCode': 'DUNS',
            'innCode': 'INN',
            'ogrnCode': 'OGRN',
            'swiftBic': 'SWIFT/BIC',
            'imoNumber': 'IMO',
            'lei': 'LEI'
        }
        
        for field, label in id_fields.items():
            if field in properties and properties[field]:
                for value in properties[field]:
                    identifiers.append({
                        'type': label,
                        'value': value
                    })
        
        return identifiers
    
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
    # Test the OpenSanctions client
    client = OpenSanctionsClient()
    
    # Test with sample companies
    test_companies = [
        "Your Company Name",  # Replace with actual company
        "Rosneft",  # Known sanctioned entity
        "Apple Inc"  # Clean company
    ]
    
    for company in test_companies:
        print(f"\nSearching for: {company}")
        result = client.search_company(company)
        
        if result['status'] == 'clear':
            print(f"✅ {company} - CLEAR (no OpenSanctions matches)")
        elif result['status'] == 'found_matches':
            print(f"⚠️  {company} - FOUND {result['match_count']} potential matches:")
            for match in result['matches']:
                print(f"   - {match['name']} (score: {match['match_score']})")
                print(f"     Programs: {', '.join(match['programs'])}")
        else:
            print(f"❌ {company} - ERROR: {result.get('error')}")
