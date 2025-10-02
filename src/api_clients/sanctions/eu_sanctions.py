# src/api_clients/sanctions/eu_sanctions.py
import requests
import xml.etree.ElementTree as ET
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
import time

class EUSanctionsClient:
    """
    Client for searching EU Consolidated Sanctions List.
    The EU provides their sanctions data in XML format.
    This is FREE and requires no API key.
    """
    
    def __init__(self):
        # EU Sanctions list endpoints
        self.xml_url = "https://data.europa.eu/data/datasets/consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions/resource/3a1d5dd6-244e-4118-82d3-db3be0554112"
        # Direct download URL for the XML file
        self.download_url = "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token="
        # Alternative JSON endpoint
        self.api_base = "https://webgate.ec.europa.eu/fsd/fsf"
        
    def search_company(self, company_name: str, threshold: float = 0.7) -> Dict[str, Any]:
        """
        Search for a company in the EU Sanctions list.
        
        Args:
            company_name: Name of the company to search
            threshold: Minimum match score (0-1) to consider a match
            
        Returns:
            Dictionary with search results and any matches
        """
        try:
            # Clean the company name
            cleaned_name = self._clean_company_name(company_name)
            
            # Try API search first, fallback to XML if needed
            results = self._search_api(cleaned_name)
            
            # Process results
            matches = []
            for result in results:
                score = self._calculate_match_score(cleaned_name, result.get('name', ''))
                
                if score >= threshold:
                    matches.append({
                        'name': result.get('name'),
                        'match_score': round(score, 2),
                        'eu_reference': result.get('eu_reference_number'),
                        'entity_type': result.get('entity_type', 'Entity'),
                        'aliases': result.get('aliases', []),
                        'addresses': result.get('addresses', []),
                        'listing_date': result.get('listing_date'),
                        'programme': result.get('programme'),
                        'legal_basis': result.get('legal_basis'),
                        'identifiers': result.get('identifiers', []),
                        'source': 'EU Consolidated List',
                        'remarks': result.get('remark', '')
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
        Search using EU FSF API endpoint
        """
        # Try the REST API endpoint first
        api_url = f"{self.api_base}/public/api/search"
        
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'M&A-Risk-Assessment-Tool'
        }
        
        # API parameters
        params = {
            'fullName': name,
            'isAdvancedSearch': 'false',
            'limit': 50
        }
        
        try:
            response = requests.get(
                api_url,
                params=params,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                # Process the JSON response
                entities = []
                for item in data.get('results', []):
                    entities.append(self._parse_api_entity(item))
                return entities
            else:
                # Fallback to XML parsing
                return self._search_xml(name)
                
        except Exception:
            # Fallback to XML parsing
            return self._search_xml(name)
    
    def _search_xml(self, name: str) -> List[Dict]:
        """
        Fallback: Download and parse the XML sanctions list
        """
        try:
            # Download the XML file
            response = requests.get(
                "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList/content",
                timeout=60,
                headers={'User-Agent': 'M&A-Risk-Assessment-Tool'}
            )
            
            if response.status_code == 200:
                # Parse XML
                root = ET.fromstring(response.content)
                
                entities = []
                
                # Find all entities (not individuals)
                for entity in root.findall('.//entity'):
                    entity_data = self._parse_xml_entity(entity)
                    
                    # Check if name matches
                    if self._is_potential_match(name, entity_data.get('name', '')):
                        entities.append(entity_data)
                
                return entities
                
        except Exception:
            return []
        
        return []
    
    def _parse_api_entity(self, item: Dict) -> Dict:
        """
        Parse entity data from API response
        """
        return {
            'name': item.get('fullName', ''),
            'eu_reference_number': item.get('euReferenceNumber'),
            'entity_type': 'Entity' if item.get('subjectType') == 'entity' else 'Individual',
            'aliases': self._extract_aliases(item),
            'addresses': self._extract_addresses(item),
            'listing_date': item.get('regulationEntryIntoForceDate'),
            'programme': item.get('programme', {}).get('value'),
            'legal_basis': item.get('regulation', {}).get('value'),
            'identifiers': self._extract_identifiers(item),
            'remark': item.get('remark')
        }
    
    def _parse_xml_entity(self, entity_elem) -> Dict:
        """
        Parse entity data from XML element
        """
        entity_data = {
            'name': '',
            'eu_reference_number': self._get_xml_text(entity_elem, 'euReferenceNumber'),
            'entity_type': 'Entity',
            'aliases': [],
            'addresses': [],
            'listing_date': self._get_xml_text(entity_elem, 'regulationEntryIntoForceDate'),
            'programme': self._get_xml_text(entity_elem, 'programme'),
            'legal_basis': self._get_xml_text(entity_elem, 'regulation'),
            'identifiers': [],
            'remark': self._get_xml_text(entity_elem, 'remark')
        }
        
        # Extract names and aliases
        for name_elem in entity_elem.findall('.//nameAlias'):
            name_value = self._get_xml_text(name_elem, 'wholeName')
            if name_value:
                if self._get_xml_text(name_elem, 'strong') == 'true':
                    entity_data['name'] = name_value
                else:
                    entity_data['aliases'].append(name_value)
        
        # Extract addresses
        for addr_elem in entity_elem.findall('.//address'):
            address = self._parse_xml_address(addr_elem)
            if address:
                entity_data['addresses'].append(address)
        
        # Extract identifiers
        for id_elem in entity_elem.findall('.//identification'):
            identifier = {
                'type': self._get_xml_text(id_elem, 'identificationTypeCode'),
                'value': self._get_xml_text(id_elem, 'number')
            }
            if identifier['value']:
                entity_data['identifiers'].append(identifier)
        
        return entity_data
    
    def _extract_aliases(self, item: Dict) -> List[str]:
        """
        Extract aliases from API response
        """
        aliases = []
        for alias_item in item.get('nameAliasList', []):
            if alias_item.get('wholeName'):
                aliases.append(alias_item['wholeName'])
        return aliases
    
    def _extract_addresses(self, item: Dict) -> List[Dict]:
        """
        Extract addresses from API response
        """
        addresses = []
        for addr in item.get('addressList', []):
            address = {
                'street': addr.get('street'),
                'city': addr.get('city'),
                'zip_code': addr.get('zipCode'),
                'country': addr.get('countryDescription'),
                'full_address': addr.get('asAtListingTime')
            }
            addresses.append(address)
        return addresses
    
    def _extract_identifiers(self, item: Dict) -> List[Dict]:
        """
        Extract identifiers from API response
        """
        identifiers = []
        for id_item in item.get('identificationList', []):
            identifier = {
                'type': id_item.get('identificationTypeDescription'),
                'value': id_item.get('number')
            }
            identifiers.append(identifier)
        return identifiers
    
    def _parse_xml_address(self, addr_elem) -> Optional[Dict]:
        """
        Parse address from XML element
        """
        address = {
            'street': self._get_xml_text(addr_elem, 'street'),
            'city': self._get_xml_text(addr_elem, 'city'),
            'zip_code': self._get_xml_text(addr_elem, 'zipCode'),
            'country': self._get_xml_text(addr_elem, 'countryDescription'),
            'full_address': self._get_xml_text(addr_elem, 'asAtListingTime')
        }
        
        # Only return if at least one field is present
        if any(address.values()):
            return address
        return None
    
    def _get_xml_text(self, element, tag: str) -> str:
        """
        Safely get text from XML element
        """
        elem = element.find('.//' + tag)
        return elem.text.strip() if elem is not None and elem.text else ''
    
    def _clean_company_name(self, name: str) -> str:
        """
        Clean and normalize company name for searching
        """
        # Remove common suffixes
        suffixes = [
            'inc', 'llc', 'ltd', 'limited', 'corp', 'corporation',
            'company', 'co', 'plc', 'sa', 'ag', 'gmbh', 'bv',
            'nv', 'spa', 'srl', 'sarl', 'ab', 'as', 'oy', 'se'
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
    
    def _calculate_match_score(self, search_name: str, found_name: str) -> float:
        """
        Calculate similarity score between two company names
        """
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
        Quick check if names might match
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
            # Add small delay to be respectful
            time.sleep(0.5)
            result = self.search_company(company)
            results.append(result)
        
        return results


# Example usage and testing
if __name__ == "__main__":
    # Test the EU Sanctions client
    client = EUSanctionsClient()
    
    # Test with sample companies
    test_companies = [
        "Your Company Name",  # Replace with actual company
        "Gazprom",  # Known sanctioned entity
        "Apple Inc"  # Clean company
    ]
    
    for company in test_companies:
        print(f"\nSearching for: {company}")
        result = client.search_company(company)
        
        if result['status'] == 'clear':
            print(f"✅ {company} - CLEAR (no EU Sanctions matches)")
        elif result['status'] == 'found_matches':
            print(f"⚠️  {company} - FOUND {result['match_count']} potential matches:")
            for match in result['matches']:
                print(f"   - {match['name']} (score: {match['match_score']})")
                print(f"     Programme: {match.get('programme', 'N/A')}")
                print(f"     Listed: {match.get('listing_date', 'N/A')}")
        else:
            print(f"❌ {company} - ERROR: {result.get('error')}")
