# src/api_clients/sanctions/ofac.py
import csv
import io
import re
import requests
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

try:
    # Optional but helpful for robust retries
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except Exception:
    HTTPAdapter = None
    Retry = None


class OFACClient:
    """
    Client for searching OFAC's Specially Designated Nationals (SDN) list.
    Pulls directly from OFAC's Sanctions List Service (SLS). No API key required.
    """

    def __init__(self):
        # SLS base + canonical files
        self.sls_base = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports"
        self.sdn_csv_url = f"{self.sls_base}/SDN.CSV"
        self.sdn_xml_url = f"{self.sls_base}/SDN.XML"
        self.sdn_adv_xml_url = f"{self.sls_base}/SDN_ADVANCED.XML"

        # Headers (SLS rejects botless requests)
        self.headers = {
            "Accept": "*/*",
            "User-Agent": "M-A-Risk-Assessment/1.0 (+contact@example.com)"
        }

        # Session with retries
        self.session = requests.Session()
        if HTTPAdapter and Retry:
            retry = Retry(
                total=3,
                backoff_factor=0.5,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET"])
            )
            self.session.mount("https://", HTTPAdapter(max_retries=retry))

        # Cache parsed entries to avoid refetching for batch checks
        self._cache: Optional[Tuple[datetime, List[Dict[str, Any]]]] = None
        self._cache_ttl = timedelta(hours=6)

    # ---------------- Public API ----------------

    def search_company(self, company_name: str, threshold: float = 0.7) -> Dict[str, Any]:
        """
        Search for company/vessel subjects on OFAC SDN.

        Args:
            company_name: Name to search
            threshold: Jaccard/containment threshold (0..1)

        Returns:
            Dict with status, matches, and metadata
        """
        try:
            cleaned = self._clean_company_name(company_name)
            entries = self._load_sdn_entities()  # cached

            matches: List[Dict[str, Any]] = []
            for e in entries:
                score = self._calculate_match_score(cleaned, e.get("name", ""))
                if score >= threshold:
                    matches.append({
                        "name": e.get("name", ""),
                        "match_score": round(score, 2),
                        "type": e.get("type", ""),
                        "programs": e.get("programs", []),
                        "aliases": e.get("aliases", []),
                        "addresses": e.get("addresses", []),
                        "ids": e.get("ids", []),
                        "remarks": e.get("remarks", ""),
                        "publishDate": e.get("publishDate", ""),
                        "sdn_number": e.get("sdn_number", ""),
                        "source": "OFAC SDN",
                        "vessel_details": e.get("vessel_details", None)
                    })

            return {
                "searched_name": company_name,
                "status": "found_matches" if matches else "clear",
                "matches": matches,
                "match_count": len(matches),
                "search_timestamp": datetime.utcnow().isoformat() + "Z",
                "api_cost": 0.0,
            }

        except Exception as e:
            return {
                "searched_name": company_name,
                "status": "error",
                "error": str(e),
                "matches": [],
                "match_count": 0,
                "search_timestamp": datetime.utcnow().isoformat() + "Z",
                "api_cost": 0.0,
            }

    def check_multiple_companies(self, company_names: List[str]) -> List[Dict[str, Any]]:
        """
        Batch check (uses cached list).
        """
        results = []
        for name in company_names:
            results.append(self.search_company(name))
        return results

    # ---------------- Fetch & Normalize ----------------

    def _load_sdn_entities(self) -> List[Dict[str, Any]]:
        """
        Load and normalize SDN entries (Entity & Vessel only).
        CSV first for speed, then fallback to XML (classic or advanced).
        """
        # Serve from cache if fresh
        if self._cache and (datetime.utcnow() - self._cache[0]) < self._cache_ttl:
            return self._cache[1]

        # Try CSV
        try:
            r = self.session.get(self.sdn_csv_url, headers=self.headers, timeout=90)
            r.raise_for_status()
            csv_buf = io.StringIO(r.text, newline="")
            reader = csv.DictReader(csv_buf)

            entities: List[Dict[str, Any]] = []
            for row in reader:
                sdn_type = (row.get("sdnType") or "").strip()
                if sdn_type not in {"Entity", "Vessel"}:
                    continue

                sdn_name = (row.get("sdnName") or "").strip()
                if not sdn_name:
                    continue

                programs = [p.strip() for p in (row.get("programList") or "").split(";") if p.strip()]
                remarks = (row.get("remarks") or "").strip()

                rec: Dict[str, Any] = {
                    "name": sdn_name,
                    "type": sdn_type,
                    "programs": programs,
                    "remarks": remarks,
                    "publishDate": (row.get("addListDate") or row.get("publicationDate") or "").strip(),
                    "sdn_number": (row.get("ent_num") or "").strip(),
                    "aliases": [],       # CSV doesn't carry AKA list in a structured way
                    "addresses": [],     # CSV minimal — prefer XML for rich fields
                    "ids": []
                }

                if sdn_type == "Vessel":
                    rec["vessel_details"] = {
                        "call_sign": (row.get("callSign") or "").strip(),
                        "vessel_type": (row.get("vesselType") or "").strip(),
                        "flag": (row.get("vesselFlag") or "").strip()
                    }

                entities.append(rec)

            if entities:
                self._cache = (datetime.utcnow(), entities)
                return entities

        except Exception:
            # Fall through to XML
            pass

        # Fallback: parse classic XML first, then advanced XML if needed
        for url in (self.sdn_xml_url, self.sdn_adv_xml_url):
            try:
                r = self.session.get(url, headers=self.headers, timeout=120)
                r.raise_for_status()
                entities = self._parse_sdn_xml(r.content)
                if entities:
                    self._cache = (datetime.utcnow(), entities)
                    return entities
            except Exception:
                continue

        # No data available
        self._cache = (datetime.utcnow(), [])
        return []

    # ---------------- XML Parsing ----------------

    @staticmethod
    def _local(tag: str) -> str:
        """Return tag local name (strip namespace)."""
        return tag.split("}", 1)[-1] if "}" in tag else tag

    def _parse_sdn_xml(self, content: bytes) -> List[Dict[str, Any]]:
        """
        Parse SDN.XML or SDN_ADVANCED.XML into normalized records.
        Keeps Entity & Vessel only.
        """
        out: List[Dict[str, Any]] = []
        root = ET.fromstring(content)

        # The SLS XML uses namespaces; iterate generically on local names
        for entry in root.iter():
            if self._local(entry.tag).lower() == "sdnentry":
                rec = self._parse_sdn_entry(entry)
                if not rec:
                    continue
                if rec.get("type") in {"Entity", "Vessel"}:
                    out.append(rec)

        return out

    def _parse_sdn_entry(self, node: ET.Element) -> Optional[Dict[str, Any]]:
        """
        Parse a single <sdnEntry> node.
        """
        # sdnType
        sdn_type = self._first_text(node, {"sdntype"}) or ""

        # name: OFAC uses lastName for primary name in most org entries
        name = self._first_text(node, {"lastname"}) or ""

        # programs
        programs = [t for t in self._all_texts(node, {"program"}) if t]

        # remarks
        remarks = self._first_text(node, {"remarks"}) or ""

        # publish date
        publish_date = self._first_text(node, {"publishdate"}) or ""

        # ent num (sdn number)
        sdn_number = self._first_text(node, {"uid"}) or ""  # some schemas use <uid>, CSV uses ent_num

        # Aliases (akaList)
        aliases: List[str] = []
        for el in node.iter():
            if self._local(el.tag).lower() in {"aka", "akaentity"}:
                aka_name = self._first_text(el, {"lastname", "firstname", "name", "akaName"})
                # Prefer whole name if provided
                whole = self._first_text(el, {"wholename"})
                alias = whole or aka_name
                if alias:
                    aliases.append(alias.strip())

        # Addresses (addressList)
        addresses: List[Dict[str, str]] = []
        for el in node.iter():
            if self._local(el.tag).lower() == "address":
                addr = {
                    "address1": self._first_text(el, {"address1"}),
                    "address2": self._first_text(el, {"address2"}),
                    "city": self._first_text(el, {"city"}),
                    "state": self._first_text(el, {"state"}),
                    "postal_code": self._first_text(el, {"postalcode", "zip"}),
                    "country": self._first_text(el, {"country"})
                }
                if any(v for v in addr.values()):
                    addresses.append(addr)

        # IDs (idList)
        ids_list: List[Dict[str, str]] = []
        for el in node.iter():
            if self._local(el.tag).lower() in {"id", "idnumber"}:
                id_type = self._first_text(el, {"idtype"})
                id_val = self._first_text(el, {"idnumber", "number", "value"})
                if id_val:
                    ids_list.append({"type": (id_type or "").strip(), "value": id_val.strip()})

        rec: Dict[str, Any] = {
            "name": name,
            "type": sdn_type,
            "programs": programs,
            "remarks": remarks,
            "publishDate": publish_date,
            "s
