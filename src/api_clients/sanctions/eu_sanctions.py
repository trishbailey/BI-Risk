# src/api_clients/sanctions/eu_sanctions.py
import requests
import xml.etree.ElementTree as ET
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import time

class EUSanctionsClient:
    """
    Client for searching the EU Consolidated Financial Sanctions List.
    Uses the official XML v1.1 file published by the EU FSF (no API key).
    """

    def __init__(self):
        # Canonical v1.1 XML endpoint for the consolidated list (no token required)
        self.xml_v11_url = (
            "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content"
        )
        # Always send a UA; some EC services reject botless requests
        self.headers = {
            "Accept": "application/xml,text/xml,*/*",
            "User-Agent": "M-A-Risk-Assessment-Tool/1.0 (+contact@example.com)"
        }
        # Simple in-memory cache so batch checks don't refetch every time
        self._cache: Optional[Tuple[datetime, List[Dict[str, Any]]]] = None
        self._cache_ttl = timedelta(hours=6)

    # ----------------------- Public API -----------------------

    def search_company(self, company_name: str, threshold: float = 0.7) -> Dict[str, Any]:
        """
        Search for a company (entities only) in the EU consolidated list.

        Args:
            company_name: Name of the company to search
            threshold: Minimum match score (0-1) to keep a match

        Returns:
            Structured search result with matches (if any)
        """
        try:
            cleaned_name = self._clean_company_name(company_name)
            entities = self._load_entities()  # cached fetch + parse

            matches = []
            for ent in entities:
                score = self._calculate_match_score(cleaned_name, ent.get("name", ""))
                if score >= threshold:
                    matches.append({
                        "name": ent.get("name", ""),
                        "match_score": round(score, 2),
                        "eu_reference_number": ent.get("eu_reference_number", ""),
                        "entity_type": ent.get("entity_type", "Entity"),
                        "aliases": ent.get("aliases", []),
                        "addresses": ent.get("addresses", []),
                        "listing_date": ent.get("listing_date", ""),
                        "programme": ent.get("programme", ""),
                        "legal_basis": ent.get("legal_basis", ""),
                        "identifiers": ent.get("identifiers", []),
                        "source": "EU Consolidated List",
                        "remarks": ent.get("remark", "")
                    })

            return {
                "searched_name": company_name,
                "status": "found_matches" if matches else "clear",
                "matches": matches,
                "match_count": len(matches),
                "search_timestamp": datetime.utcnow().isoformat() + "Z",
                "api_cost": 0.0
            }

        except Exception as e:
            return {
                "searched_name": company_name,
                "status": "error",
                "error": str(e),
                "matches": [],
                "match_count": 0,
                "search_timestamp": datetime.utcnow().isoformat() + "Z",
                "api_cost": 0.0
            }

    def check_multiple_companies(self, company_names: List[str]) -> List[Dict[str, Any]]:
        """
        Batch check multiple companies (uses the cached list).
        """
        results = []
        for company in company_names:
            time.sleep(0.25)  # be polite
            results.append(self.search_company(company))
        return results

    # ----------------------- Fetch & Parse -----------------------

    def _load_entities(self) -> List[Dict[str, Any]]:
        """
        Fetch and parse the EU XML list, with basic caching.
        Returns normalized 'entity' records only (no individuals).
        """
        # Serve cache if fresh
        if self._cache and (datetime.utcnow() - self._cache[0]) < self._cache_ttl:
            return self._cache[1]

        # Fetch
        r = requests.get(self.xml_v11_url, headers=self.headers, timeout=90)
        r.raise_for_status()

        # Parse
        root = ET.fromstring(r.content)

        # Build normalized entity list
        entities: List[Dict[str, Any]] = []
        for subj in self._iter_subjects(root):
            ent = self._parse_subject(subj)
            if not ent:
                continue
            # Only keep non-individuals (Entity/Vessel/Aircraft). EU primarily distinguishes entity vs. person.
            if ent.get("entity_type", "").lower() in {"entity", "vessel", "aircraft", "group", "undertaking"}:
                # Ensure we have a primary name; if not, skip to avoid junk matches
                if ent.get("name"):
                    entities.append(ent)

        # Cache and return
        self._cache = (datetime.utcnow(), entities)
        return entities

    # ----------------------- XML Helpers -----------------------

    @staticmethod
    def _localname(tag: str) -> str:
        """
        Return the local name of an XML tag (strip namespace).
        """
        return tag.split("}", 1)[-1] if "}" in tag else tag

    def _iter_subjects(self, root: ET.Element):
        """
        Iterate all 'subject' nodes, regardless of namespace or specific schema flavor.
        v1.1 commonly uses 'sanctionEntity' / 'sanctionPerson', but we fall back to any 'subject'.
        """
        # Prefer explicit nodes if present
        candidates = []
        for el in root.iter():
            ln = self._localname(el.tag).lower()
            if ln in {"sanctionentity", "sanctionperson", "subject", "entity"}:
                candidates.append(el)
        return candidates

    def _parse_subject(self, node: ET.Element) -> Optional[Dict[str, Any]]:
        """
        Parse a single subject (entity/person) node into a normalized dict.
        Robust to namespace and minor schema variations by matching on local tag names.
        """
        # Determine subject type (entity vs person)
        entity_type = self._first_text(node, {"subjecttype", "sdntype", "type"})
        if not entity_type:
            # Infer from tag name if missing
            tag_ln = self._localname(node.tag).lower()
            if "person" in tag_ln:
                entity_type = "Individual"
            elif "entity" in tag_ln or "undertaking" in tag_ln or "group" in tag_ln:
                entity_type = "Entity"
            else:
                # Default to Entity to avoid missing orgs when the tag is generic 'subject'
                entity_type = "Entity"

        # EU reference number
        eu_ref = self._first_text(node, {"eureferencenumber", "referenceNumber", "euReferenceNumber"})

        # Names & aliases
        name, aliases = self._extract_names(node)

        # Addresses
        addresses = self._extract_addresses(node)

        # Identifiers
        identifiers = self._extract_identifiers(node)

        # Programme(s) and legal basis/regulation
        programme = self._first_text(node, {"programme", "program"})
        legal_basis = self._first_text(node, {"regulation", "legalbasis", "legalBasis"})

        # Listing date (entry into force)
        listing_date = self._first_text(node, {"regulationentryintoforcedate", "entryintoforcedate", "listingdate"})

        # Remarks
        remark = self._first_text(node, {"remark", "remarks"})

        # If we failed to get a main name, bail out
        if not name and not aliases:
            return None

        # Choose a name if the "strong" one wasn't found
        primary_name = name or (aliases[0] if aliases else "")

        return {
            "name": primary_name,
            "eu_reference_number": eu_ref,
            "entity_type": entity_type,
            "aliases": aliases,
            "addresses": addresses,
            "listing_date": listing_date,
            "programme": programme,
            "legal_basis": legal_basis,
            "identifiers": identifiers,
            "remark": remark
        }

    def _extract_names(self, node: ET.Element) -> Tuple[str, List[str]]:
        """
        Extract name aliases; prefer 'strong=true' as the primary name.
        """
        primary = ""
        aliases: List[str] = []

        for child in node.iter():
            if self._localname(child.tag).lower() == "namealias":
                whole = self._first_text(child, {"wholename", "wholeName", "name"})
                strong = self._first_text(child, {"strong"})  # often "true"/"false"
                if whole:
                    if (strong or "").strip().lower() == "true":
                        primary = whole.strip()
                    else:
                        aliases.append(whole.strip())

        # Fallback: some schemas put a direct <name> or <wholeName> under the subject
        if not primary:
            direct = self._first_text(node, {"name", "wholename", "lastName"})
            if direct:
                primary = direct.strip()

        return primary, aliases

    def _extract_addresses(self, node: ET.Element) -> List[Dict[str, str]]:
        """
        Extract addresses from a subject.
        """
        addresses: List[Dict[str, str]] = []
        for child in node.iter():
            if self._localname(child.tag).lower() == "address":
                address = {
                    "street": self._first_text(child, {"street"}),
                    "city": self._first_text(child, {"city", "town"}),
                    "zip_code": self._first_text(child, {"zipcode", "zip", "postCode"}),
                    "country": self._first_text(child, {"countrydescription", "country", "countryCode"}),
                    "full_address": self._first_text(child, {"asatlistingtime", "fulladdress"})
                }
                if any(v for v in address.values()):
                    addresses.append(address)
        return addresses

    def _extract_identifiers(self, node: ET.Element) -> List[Dict[str, str]]:
        """
        Extract identification numbers (e.g., reg#, tax#, passport) from a subject.
        """
        identifiers: List[Dict[str, str]] = []
        for child in node.iter():
            if self._localname(child.tag).lower() in {"identification", "id", "identifier"}:
                id_type = self._first_text(child, {"identificationtypedescription", "identificationtypecode", "type"})
                number = self._first_text(child, {"number", "value", "idNumber"})
                if number:
                    identifiers.append({"type": (id_type or "").strip(), "value": number.strip()})
        return identifiers

    def _first_text(self, node: ET.Element, local_names: set) -> str:
        """
        Return the first matching descendant's text where the tag's local name is in `local_names`.
        Case-insensitive on local names.
        """
        targets = {ln.lower() for ln in local_names}
        # Check node itself first
        if self._localname(node.tag).lower() in targets:
            return (node.text or "").strip()

        # Then any descendants
        for el in node.iter():
            if self._localname(el.tag).lower() in targets:
                if el.text:
                    return el.text.strip()
        return ""

    # ----------------------- Matching -----------------------

    def _clean_company_name(self, name: str) -> str:
        """
        Normalize company names to improve fuzzy matching.
        """
        suffixes = {
            "inc", "llc", "ltd", "limited", "corp", "corporation",
            "company", "co", "plc", "sa", "ag", "gmbh", "bv",
            "nv", "spa", "srl", "sarl", "ab", "as", "oy", "se",
            "pte", "pt", "kft", "oyj", "aps", "kk", "kabushiki", "kaisha"
        }
        s = name.lower().strip()
        s = re.sub(r"[^\w\s]", " ", s)
        words = [w for w in s.split() if w]
        while words and words[-1] in suffixes:
            words.pop()
        return " ".join(words)

    def _calculate_match_score(self, search_name: str, found_name: str) -> float:
        """
        Simple Jaccard word-overlap with bonuses for containment/exact.
        """
        s = self._clean_company_name(search_name)
        f = self._clean_company_name(found_name)

        if not s or not f:
            return 0.0
        if s == f:
            return 1.0
        if s in f or f in s:
            return 0.9

        sw, fw = set(s.split()), set(f.split())
        if not sw or not fw:
            return 0.0
        return len(sw & fw) / len(sw | fw)

    def _is_potential_match(self, search_name: str, entry_name: str) -> bool:
        """
        Quick prefilter: any overlapping 'significant' word (len>3).
        """
        s = self._clean_company_name(search_name)
        e = self._clean_company_name(entry_name)
        sw = {w for w in s.split() if len(w) > 3}
        ew = {w for w in e.split() if len(w) > 3}
        return bool(sw & ew)


# ----------------------- Example usage -----------------------
if __name__ == "__main__":
    client = EUSanctionsClient()
    test_companies = [
        "Your Company Name",   # Replace with actual company
        "Gazprom",             # Likely to return matches on EU list
        "Apple Inc"            # Should be clear
    ]
    for company in test_companies:
        print(f"\nSearching for: {company}")
        result = client.search_company(company)
        if result["status"] == "clear":
            print(f"✅ {company} - CLEAR (no EU matches)")
        elif result["status"] == "found_matches":
            print(f"⚠️  {company} - FOUND {result['match_count']} potential matches:")
            for m in result["matches"]:
                print(f"   - {m['name']} (score: {m['match_score']}) | EU Ref: {m.get('eu_reference_number','')}")
                print(f"     Programme: {m.get('programme','N/A')}; Listed: {m.get('listing_date','N/A')}")
        else:
            print(f"❌ {company} - ERROR: {result.get('error')}")
