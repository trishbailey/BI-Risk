# src/api_clients/sanctions/ofac.py
import requests
import csv
import io
import re
from typing import Dict, List, Any
from datetime import datetime
from xml.etree import ElementTree as ET

class OFACClient:
    """
    Client for searching OFAC's Specially Designated Nationals (SDN) list.
    Uses OFAC's Sanctions List Service (SLS) endpoints.
    This is FREE and requires no API key.
    """
    
    def __init__(self):
        # OFAC's Sanctions List Service (SLS) base URL
        self.sls_base = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports"
        # Supported, stable formats
        self.sdn_csv_url = f"{self.sls_base}/SDN.CSV"
        self.sdn_xml_url = f"{self.sls_base}/SDN.XML"
        self.sdn_adv_xml_url = f"{self.sls_base}/SDN_ADVANCED.XML"
        
        # Required headers - OFAC requires User-Agent
        self.headers = {
            "Accept": "*/*",
            "User-Agent": "M&A-Risk-Assessment/1.0"
        }
    
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
            
            # Download and search the SDN list
            matches = self._search_downloaded_list(cleaned_name, threshold)
            
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
    
    def _search_downloaded_list(self, search_name: str, threshold: float) -> List[Dict]:
        """
        Download and search the OFAC SDN list
        """
        # Try CSV first (simpler and complete)
        try:
            response = requests.get(self.sdn_csv_url, headers=self.headers, timeout=60)
            response.raise_for_status()
            
            matches = []
            
            # Parse CSV properly using csv module
            csv_buffer = io.StringIO(response.text)
            reader = csv.DictReader(csv_buffer)
            
            for row in reader:
                # OFAC CSV headers: ent_num, sdnName, sdnType, programList, title, callSign, 
                # vesselType, tonnage, grossRegisteredTonnage, vesselFlag, vesselOwner, remarks
                
                sdn_type = (row.get('sdnType') or '').strip()
                sdn_name = (row.get('sdnName') or '').strip()
                
                # Only look at entities and vessels, not individuals
                if sdn_type in ['Entity', 'Vessel']:
                    # Calculate match score
                    score = self._calculate_match_score(search_name, sdn_name)
                    
                    if score >= threshold:
                        matches.append({
                            'name': sdn_name,
                            'match_score': round(score, 2),
                            'type': sdn_type,
                            'programs': [p.strip() for p in (row.get('programList') or '').split(';') if p.strip()],
                            'remarks': row.get('remarks', '').strip(),
                            'source': 'OFAC SDN',
                            'sdn_number': row.get('ent_num', '').strip(),
                            'vessel_details': {
                                'call_sign': row.get('callSign', '').strip(),
                                'vessel_type': row.get('vesselType', '').strip(),
                                'flag': row.get('vesselFlag', '').strip()
                            } if sdn_type == 'Vessel' else None
                        })
            
            return matches
            
        except Exception as csv_error:
            print(f"CSV download failed: {csv_error}, trying XML...")
            
            # Fallback to XML
            try:
                response = requests.get(self.sdn_xml_url, headers=self.headers, timeout=60)
                response.raise_for_status()
                
                return self._parse_xml_response(response.content, search_name, threshold)
                
            except Exception as xml_error:
                print(f"XML download also failed: {xml_error}")
                return []
    
    def _parse_xml_response(self, xml_content: bytes, search_name: str, threshold: float) -> List[Dict]:
        """
        Parse SDN XML format
        """
        matches = []
        
        try:
            root = ET.fromstring(xml_content)
            
            # Determine namespace from root
            ns = {'x': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
            
            # Find all SDN entries
            for entry in root.findall('.//sdnEntry', ns) or root.findall('.//x:sdnEntry', ns):
                # Get SDN type
                sdn_type_elem = entry.find('sdnType', ns) or entry.find('x:sdnType', ns)
                sdn_type = sdn_type_elem.text.strip() if sdn_type_elem is not None else ''
                
                if sdn_type in ['Entity', 'Vessel']:
                    # Get name - could be in different places
                    name_elem = (entry.find('.//lastName', ns) or 
                               entry.find('.//x:lastName', ns) or
                               entry.find('lastName') or
                               entry.find('x:lastName'))
                    
                    sdn_name = name_elem.text.strip() if name_elem is not None else ''
                    
                    if sdn_name:
                        score = self._calculate_match_score(search_name, sdn_name)
                        
                        if score >= threshold:
                            # Get programs
                            programs = []
                            for prog in entry.findall('.//program', ns) or entry.findall('.//x:program', ns):
                                if prog.text:
                                    programs.append(prog.text.strip())
                            
                            # Get remarks
                            remarks_elem = entry.find('remarks', ns) or entry.find('x:remarks', ns)
                            remarks = remarks_elem.text.strip() if remarks_elem is not None else ''
                            
                            matches.append({
                                'name': sdn_name,
                                'match_score': round(score, 2),
                                'type': sdn_type,
                                'programs': programs,
                                'remarks': remarks,
                                'source': 'OFAC SDN'
                            })
            
        except Exception as e:
            print(f"XML parsing error: {e}")
            
        return matches
    
    def _clean_company_name(self, name: str) -> str:
        """
        Clean and normalize company name for searching
        """
        # Convert to uppercase (OFAC format is uppercase)
        name = name.upper()
        
        # Remove common suffixes
        suffixes = [
            ' INC', ' LLC', ' LTD', ' LIMITED', ' CORP', ' CORPORATION',
            ' COMPANY', ' CO', ' PLC', ' SA', ' AG', ' GMBH', ' BV',
            ' OOO', ' OAO', ' PAO', ' ZAO', ' JSC', ' PJSC', ' OJSC'  # Russian entities
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
        search_clean = self._clean_company_name(search_name)
        found_clean = self._clean_company_name(found_name)
        
        # Exact match
        if search_clean == found_clean:
            return 1.0
        
        # One contains the other
        if search_clean in found_clean or found_clean in search_clean:
            return 0.9
        
        # Word overlap
        search_words = set(search_clean.split())
        found_words = set(found_clean.split())
        
        if not search_words or not found_words:
            return 0.0
        
        # Calculate Jaccard similarity
        overlap = len(search_words & found_words)
        total = len(search_words | found_words)
        
        return overlap / total if total > 0 else 0.0
