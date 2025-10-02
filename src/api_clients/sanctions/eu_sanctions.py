# src/api_clients/sanctions/eu_sanctions.py
import requests
import xml.etree.ElementTree as ET
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import time
from io import StringIO
import csv

try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except Exception:
    HTTPAdapter = None
    Retry = None


class EUSanctionsClient:
    """
    Client for searching the EU Consolidated Financial Sanctions List.
    Fetches official XML v1.1 (preferred) or CSV. Returns Entities only.
    """

    def __init__(self):
        # Primary EU FSF endpoints
        self.xml_v11_primary = "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content"
        self.csv_primary = "https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList/content"

        # Tokenized fallbacks (prevent sporadic 403s on some edges)
        self.xml_v11_token = (
            "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw"
        )
        self.csv_token = (
            "https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList/content?token=dG9rZW4tMjAxNw"
        )

        self.headers = {
            "Accept": "application/xml,text/xml,application/json,text/csv,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": "M-A-Risk-Assessment-Tool/1.0 (+contact@example.com)",
            "Referer": "https://webgate.ec.europa.eu/fsd/fsf/public/",
            "Connection": "keep-alive",
        }

        self.session = requests.Session()
        if HTTPAdapter and Retry:
            retry = Retry(
                total=3,
                backoff_factor=0.5,
                status_forcelist=(403, 429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET"]),
            )
            self.session.mount("https://", HTTPAdapter(max_retries=retry))

        self._cache: Optional[Tuple[datetime, List[Dict[str, Any]]]] = None
        self._cache_ttl = timedelta(hours=6)

    # ---------------- Public API ----------------

    def search_company(self, company_name: str, threshold: float = 0.7) -> Dict[str, Any]:
        try:
            cleaned_name = self._clean_company_name(company_name)
            entities = self._load_entities()

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
        results = []
        for company in company_names:
            time.sleep(0.25)
            results.append(self.search_company(company))
        return results

    # ---------------- Fetch & Parse ----------------

    def _get_first_success(self, urls: List[str]) -> Optional[requests.Response]:
        for url in urls:
            try:
                r = self.session.get(url, headers=self.headers, timeout=90)
                if r.status_code == 200 and r.content:
                    return r
            except requests.RequestException:
                continue
        return None

    def _load_entities(self) -> List[Dict[str, Any]]:
        if self._cache and (datetime.utcnow() - self._cache[0]) < self._cache_ttl:
            return self._cache[1]

        # Prefer XML v1.1 (primary → token)
        xml_resp = self._get_first_success([self.xml_v11_primary, self.xml_v11_token])
        if xml_resp is not None:
            try:
                root = ET.fromstring(xml_resp.content)
                entities = self._parse_xml_entities(root)
                self._cache = (datetime.utcnow(), entities)
                return entities
            except Exception:
                pass  # fall through to CSV

        # Fallback to CSV (primary → token)
        csv_resp = self._get_first_success([self.csv_primary, self.csv_token])
        if csv_resp is not None:
            try:
                entities = self._parse_csv_entities(csv_resp.text)
                self._cache = (datetime.utcnow(), entities)
                return entities
            except Exception:
                pass

        self._cache = (datetime.utcnow(), [])
        return []

    # ---------------- Parse: XML & CSV ----------------

    def _parse_xml_entities(self, root: ET.Element) -> List[Dict[str, Any]]:
        """
        v1.1 exports have top-level or nested <sanctionEntity> elements.
        Select them directly, namespace-agnostic: .//{*}sanctionEntity
        """
        entities: List[Dict[str, Any]] = []
        for node in root.findall(".//{*}sanctionEntity"):
            ent = self._parse_subject(node)
            if not ent:
                continue
            # Entities only (person records are under sanctionPerson)
            if ent.get("entity_type", "").lower() in {"entity", "vessel", "aircraft", "group", "undertaking"}:
                if ent.get("name"):
                    entities.append(ent)
        return entities

    def _parse_csv_entities(self, csv_text: str) -> List[Dict[str, Any]]:
        """
        CSV header names vary; handle common variants.
        """
        out: List[Dict[str, Any]] = []
        rdr = csv.DictReader(StringIO(csv_text))
        for row in rdr:
            # Subject type
            subj_type = (row.get("subjectType") or row.get("subjectTypeCode") or "").strip()
            if subj_type and subj_type.lower() in {"person", "individual"}:
                continue

            # Name variants
            name = (
                row.get("NameAlias_WholeName") or
                row.get("nameAlias.wholeName") or
                row.get("nameAliasWholeName") or
                row.get("wholeName") or
                row.get("name") or
                ""
            ).strip()
            if not name:
                continue

            eu_ref = (row.get("euReferenceNumber") or row.get("referenceNumber") or "").strip()
            programme = (row.get("programme") or row.get("program") or "").strip()
            legal_basis = (row.get("regulation") or row.get("legalBasis") or "").strip()
            listing_date = (row.get("regulationEntryIntoForceDate") or "").strip()
            remark = (row.get("remark") or "").strip()

            out.append({
                "name": name,
                "eu_reference_number": eu_ref,
                "entity_type": "Entity",
                "aliases": [],
                "addresses": [],
                "listing_date": listing_date,
                "programme": programme,
                "legal_basis": legal_basis,
                "identifiers": [],
                "remark": remark
            })
        return out

    # ---------------- XML helpers ----------------

    @staticmethod
    def _localname(tag: str) -> str:
        return tag.split("}", 1)[-1] if "}" in tag else tag

    def _parse_subject(self, node: ET.Element) -> Optional[Dict[str, Any]]:
        # Explicitly an Entity container; default type = Entity
        entity_type = "Entity"

        # EU reference number (direct child or nested)
        eu_ref = self._first_text(node, {"euReferenceNumber", "referenceNumber", "eureferencenumber"})

        # Names & aliases (prefer strong=true)
        name, aliases = self._extract_names(node)

        # Addresses, identifiers, programme, legal basis, listing date, remark
        addresses = self._extract_addresses(node)
        identifiers = self._extract_identifiers(node)
        programme = self._first_text(node, {"programme", "program"})
        legal_basis = self._first_text(node, {"regulation", "legalBasis", "legalbasis"})
        listing_date = self._first_text(node, {"regulationEntryIntoForceDate", "entryIntoForceDate", "listingDate"})
        remark = self._first_text(node, {"remark", "remarks"})

        if not name and not aliases:
            return None
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

    def _first_text(self, node: ET.Element, local_names: set) -> str:
        targets = {ln.lower() for ln in local_names}
        # node itself
        if self._localname(node.tag).lower() in targets:
            return (node.text or "").strip()
        # descendants
        for el in node.iter():
            if self._localname(el.tag).lower() in targets and el.text:
                return el.text.strip()
        return ""

    def _extract_names(self, node: ET.Element) -> Tuple[str, List[str]]:
        """
        EU sets name(s) in <nameAlias><wholeName>. Choose strong='true' as primary.
        """
        primary = ""
        aliases: List[str] = []
        for na in node.findall(".//{*}nameAlias"):
            whole = self._first_text(na, {"wholeName", "wholename", "name"})
            strong = self._first_text(na, {"strong"}).lower()
            if whole:
                if strong == "true":
                    primary = whole.strip()
                else:
                    aliases.append(whole.strip())
        if not primary:
            direct = self._first_text(node, {"name", "wholeName", "wholename"})
            if direct:
                primary = direct.strip()
        return primary, aliases

    def _extract_addresses(self, node: ET.Element) -> List[Dict[str, str]]:
        addrs: List[Dict[str, str]] = []
        for a in node.findall(".//{*}address"):
            addr = {
                "street": self._first_text(a, {"street"}),
                "city": self._first_text(a, {"city", "town"}),
                "zip_code": self._first_text(a, {"zipCode", "zipcode", "zip", "postCode"}),
                "country": self._first_text(a, {"countryDescription", "country", "countryCode"}),
                "full_address": self._first_text(a, {"asAtListingTime", "fullAddress"})
            }
            if any(addr.values()):
                addrs.append(addr)
        return addrs

    def _extract_identifiers(self, node: ET.Element) -> List[Dict[str, str]]:
        ids: List[Dict[str, str]] = []
        for ident in node.findall(".//{*}identification"):
            id_type = self._first_text(ident, {"identificationTypeDescription", "identificationTypeCode", "type"})
            number = self._first_text(ident, {"number", "value", "idNumber"})
            if number:
                ids.append({"type": (id_type or "").strip(), "value": number.strip()})
        return ids

    # ---------------- Matching ----------------

    def _clean_company_name(self, name: str) -> str:
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
        s = self._clean_company_name(search_name)
        e = self._clean_company_name(entry_name)
        sw = {w for w in s.split() if len(w) > 3}
        ew = {w for w in e.split() if len(w) > 3}
        return bool(sw & ew)


# ---------------- Example ----------------
if __name__ == "__main__":
    client = EUSanctionsClient()
    for company in ["Your Company Name", "Gazprom", "Apple Inc"]:
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
