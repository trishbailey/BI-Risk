# src/api_clients/regulatory/epa.py
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import time

class EPAEchoClient:
    """
    Client for EPA's Enforcement and Compliance History Online (ECHO) system.
    This is FREE and requires no API key.
    Documentation: https://echo.epa.gov/tools/web-services
    """
    
    def __init__(self):
        # EPA ECHO API endpoints
        self.base_url = "https://echodata.epa.gov/echo"
        self.facilities_search = f"{self.base_url}/facility_search"
        self.detailed_facility = f"{self.base_url}/detailed_facility_report"
        self.enforcement = f"{self.base_url}/enforcement_case_search"
        
    def search_company(self, company_name: str) -> Dict[str, Any]:
        """
        Search for a company's environmental compliance history.
        
        Args:
            company_name: Name of the company to search
            
        Returns:
            Dictionary with search results and compliance summary
        """
        try:
            # Search for facilities
            facilities = self._search_facilities(company_name)
            
            if not facilities:
                return {
                    'searched_name': company_name,
                    'status': 'clear',
                    'facility_count': 0,
                    'facilities': [],
                    'violations_summary': {
                        'total_violations': 0,
                        'serious_violations': 0,
                        'enforcement_actions': 0,
                        'total_penalties': 0
                    },
                    'search_timestamp': datetime.now().isoformat(),
                    'api_cost': 0.0
                }
            
            # Get detailed compliance data for each facility
            detailed_facilities = []
            total_violations = 0
            serious_violations = 0
            enforcement_actions = 0
            total_penalties = 0.0
            
            for facility in facilities[:10]:  # Limit to first 10 facilities
                details = self._get_facility_details(facility.get('RegistryId'))
                if details:
                    detailed_facilities.append(details)
                    
                    # Aggregate violations
                    violations = details.get('violations', {})
                    total_violations += violations.get('total_count', 0)
                    serious_violations += violations.get('serious_count', 0)
                    
                    # Aggregate enforcement
                    enforcement = details.get('enforcement', {})
                    enforcement_actions += enforcement.get('action_count', 0)
                    total_penalties += enforcement.get('total_penalties', 0)
            
            # Determine overall status
            if serious_violations > 0 or enforcement_actions > 0:
                status = 'violations_found'
            elif total_violations > 0:
                status = 'minor_issues'
            else:
                status = 'clear'
            
            return {
                'searched_name': company_name,
                'status': status,
                'facility_count': len(facilities),
                'facilities': detailed_facilities,
                'violations_summary': {
                    'total_violations': total_violations,
                    'serious_violations': serious_violations,
                    'enforcement_actions': enforcement_actions,
                    'total_penalties': total_penalties
                },
                'search_timestamp': datetime.now().isoformat(),
                'api_cost': 0.0
            }
            
        except Exception as e:
            return {
                'searched_name': company_name,
                'status': 'error',
                'error': str(e),
                'facility_count': 0,
                'facilities': [],
                'search_timestamp': datetime.now().isoformat(),
                'api_cost': 0.0
            }
    
    def _search_facilities(self, company_name: str) -> List[Dict]:
        """
        Search for facilities owned by the company
        """
        # EPA ECHO facility search parameters
        params = {
            'output': 'json',
            'qfacilityname': company_name,  # Search by facility name
            'tablelist': 'Y',
            'responseset': 'Default'
        }
        
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'M&A-Risk-Assessment/1.0'
        }
        
        try:
            response = requests.get(
                self.facilities_search,
                params=params,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Results are in the 'Results' key
                facilities = data.get('Results', {}).get('Facilities', [])
                
                # Filter to ensure name match
                matched_facilities = []
                for facility in facilities:
                    facility_name = facility.get('FacilityName', '').lower()
                    if self._is_name_match(company_name.lower(), facility_name):
                        matched_facilities.append({
                            'RegistryId': facility.get('RegistryId'),
                            'FacilityName': facility.get('FacilityName'),
                            'LocationAddress': facility.get('LocationAddress'),
                            'City': facility.get('CityName'),
                            'State': facility.get('StateCode'),
                            'Programs': self._parse_programs(facility),
                            'ComplianceStatus': facility.get('EPASystemFlag', '')
                        })
                
                return matched_facilities
                
        except Exception as e:
            print(f"Facility search error: {e}")
            return []
        
        return []
    
    def _get_facility_details(self, registry_id: str) -> Optional[Dict]:
        """
        Get detailed compliance information for a specific facility
        """
        if not registry_id:
            return None
        
        params = {
            'output': 'json',
            'p_id': registry_id
        }
        
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'M&A-Risk-Assessment/1.0'
        }
        
        try:
            response = requests.get(
                self.detailed_facility,
                params=params,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract key compliance information
                facility_info = self._extract_facility_info(data)
                violations = self._extract_violations(data)
                enforcement = self._extract_enforcement(data)
                
                return {
                    'registry_id': registry_id,
                    'facility_info': facility_info,
                    'violations': violations,
                    'enforcement': enforcement,
                    'last_inspection': self._extract_last_inspection(data)
                }
                
        except Exception as e:
            print(f"Facility details error for {registry_id}: {e}")
            
        return None
    
    def _extract_facility_info(self, data: Dict) -> Dict:
        """
        Extract basic facility information
        """
        # Navigate the nested structure - EPA data can be deeply nested
        facility = data.get('Results', {})
        
        return {
            'name': facility.get('FacilityName', ''),
            'address': facility.get('FacilityAddress', ''),
            'city': facility.get('FacilityCity', ''),
            'state': facility.get('FacilityState', ''),
            'zip': facility.get('FacilityZip', ''),
            'programs': facility.get('ProgramsAtFacility', [])
        }
    
    def _extract_violations(self, data: Dict) -> Dict:
        """
        Extract violation summary
        """
        results = data.get('Results', {})
        
        # Look for violation counts in various program areas
        total_violations = 0
        serious_violations = 0
        
        # Check CAA (Clean Air Act) violations
        caa_violations = results.get('CAAComplianceHistory', {})
        if caa_violations:
            total_violations += int(caa_violations.get('ViolationCount', 0))
            serious_violations += int(caa_violations.get('HPVCount', 0))  # High Priority Violations
        
        # Check CWA (Clean Water Act) violations
        cwa_violations = results.get('CWAComplianceHistory', {})
        if cwa_violations:
            total_violations += int(cwa_violations.get('ViolationCount', 0))
            serious_violations += int(cwa_violations.get('SNCSNCCount', 0))  # Significant Non-Compliance
        
        # Check RCRA (Resource Conservation and Recovery Act) violations
        rcra_violations = results.get('RCRAComplianceHistory', {})
        if rcra_violations:
            total_violations += int(rcra_violations.get('ViolationCount', 0))
            serious_violations += int(rcra_violations.get('SNYCount', 0))  # Significant Non-Compliers
        
        return {
            'total_count': total_violations,
            'serious_count': serious_violations,
            'recent_violations': self._check_recent_violations(results)
        }
    
    def _extract_enforcement(self, data: Dict) -> Dict:
        """
        Extract enforcement action information
        """
        results = data.get('Results', {})
        
        total_actions = 0
        total_penalties = 0.0
        
        # Check for formal enforcement actions
        enforcement_data = results.get('EnforcementActions', [])
        if isinstance(enforcement_data, list):
            total_actions = len(enforcement_data)
            
            for action in enforcement_data:
                penalty = action.get('EnforcementActionPenalty', 0)
                if penalty:
                    try:
                        total_penalties += float(penalty)
                    except:
                        pass
        
        return {
            'action_count': total_actions,
            'total_penalties': total_penalties,
            'recent_actions': total_actions > 0
        }
    
    def _extract_last_inspection(self, data: Dict) -> Optional[str]:
        """
        Extract the most recent inspection date
        """
        results = data.get('Results', {})
        
        # Look for inspection dates across programs
        inspection_dates = []
        
        # CAA inspections
        if results.get('CAALastInspectionDate'):
            inspection_dates.append(results.get('CAALastInspectionDate'))
        
        # CWA inspections  
        if results.get('CWALastInspectionDate'):
            inspection_dates.append(results.get('CWALastInspectionDate'))
        
        # RCRA inspections
        if results.get('RCRALastInspectionDate'):
            inspection_dates.append(results.get('RCRALastInspectionDate'))
        
        # Return the most recent
        if inspection_dates:
            return max(inspection_dates)
        
        return None
    
    def _check_recent_violations(self, results: Dict) -> bool:
        """
        Check if there are violations in the past 3 years
        """
        # Look for quarters in non-compliance in recent history
        # EPA tracks compliance by quarter
        
        # Check CAA
        caa_qtrs = results.get('CAAQtrsInNC', 0)
        if caa_qtrs and int(caa_qtrs) > 0:
            return True
        
        # Check CWA
        cwa_qtrs = results.get('CWAQtrsInNC', 0)
        if cwa_qtrs and int(cwa_qtrs) > 0:
            return True
        
        # Check RCRA
        rcra_qtrs = results.get('RCRAQtrsInNC', 0)
        if rcra_qtrs and int(rcra_qtrs) > 0:
            return True
        
        return False
    
    def _parse_programs(self, facility: Dict) -> List[str]:
        """
        Parse which environmental programs the facility is subject to
        """
        programs = []
        
        # Check various program flags
        if facility.get('CAAFlag') == 'Y':
            programs.append('CAA')  # Clean Air Act
        if facility.get('CWAFlag') == 'Y':
            programs.append('CWA')  # Clean Water Act
        if facility.get('RCRAFlag') == 'Y':
            programs.append('RCRA')  # Resource Conservation and Recovery Act
        if facility.get('TRIFlag') == 'Y':
            programs.append('TRI')  # Toxics Release Inventory
        
        return programs
    
    def _is_name_match(self, search_name: str, facility_name: str) -> bool:
        """
        Check if facility name matches the company name
        """
        # Simple matching - could be enhanced
        search_words = search_name.lower().split()
        
        # Check if any significant word from search appears in facility name
        for word in search_words:
            if len(word) > 3 and word in facility_name:
                return True
        
        return False
