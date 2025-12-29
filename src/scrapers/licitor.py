"""
Scraper for Licitor.com - Judicial real estate auctions
"""
import re
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup
from loguru import logger

from .base_scraper import BaseScraper
from src.storage.models import Auction, Lawyer, PropertyType, AuctionStatus, PVStatus


class LicitorScraper(BaseScraper):
    """Scraper for licitor.com"""

    # Tribunaux to monitor - Paris et petite couronne
    TRIBUNAUX = {
        "tj-paris": "Tribunal Judiciaire de Paris",
        "tj-bobigny": "Tribunal Judiciaire de Bobigny",
        "tj-nanterre": "Tribunal Judiciaire de Nanterre",
        "tj-creteil": "Tribunal Judiciaire de Créteil",
    }

    def __init__(self):
        super().__init__(
            name="Licitor",
            base_url="https://www.licitor.com"
        )

    def get_auction_list_url(self, page: int = 1) -> str:
        """Build URL for auction listing - returns base URL as Licitor is organized by tribunal"""
        return f"{self.base_url}/ventes-judiciaires-immobilieres"

    def get_tribunal_url(self, tribunal_slug: str) -> str:
        """Get URL for specific tribunal - deprecated, use find_tribunal_auction_urls instead"""
        return f"{self.base_url}/ventes-judiciaires-immobilieres/{tribunal_slug}.html"

    def find_tribunal_auction_urls(self, tribunal_slug: str) -> List[str]:
        """Find all auction date URLs for a tribunal by checking all weekdays"""
        from datetime import timedelta

        # French day and month names for URL generation
        days_fr = {0: "lundi", 1: "mardi", 2: "mercredi", 3: "jeudi", 4: "vendredi", 5: "samedi", 6: "dimanche"}
        months_fr = {
            1: "janvier", 2: "fevrier", 3: "mars", 4: "avril",
            5: "mai", 6: "juin", 7: "juillet", 8: "aout",
            9: "septembre", 10: "octobre", 11: "novembre", 12: "decembre"
        }

        # Each tribunal has different auction days:
        # - Marseille: mercredi (Wednesday)
        # - Aix-en-Provence: lundi (Monday)
        # - Toulon: jeudi (Thursday)
        # We'll check all weekdays to be safe

        today = date.today()
        urls_to_check = []

        # Generate URLs for the next 60 days (all weekdays)
        for day_offset in range(60):
            check_date = today + timedelta(days=day_offset)

            # Skip weekends
            if check_date.weekday() >= 5:
                continue

            day_name = days_fr[check_date.weekday()]
            month_name = months_fr[check_date.month]

            # Build URL: lundi-12-janvier-2026.html
            url = f"{self.base_url}/ventes-judiciaires-immobilieres/{tribunal_slug}/{day_name}-{check_date.day}-{month_name}-{check_date.year}.html"
            urls_to_check.append(url)

        # Verify which URLs actually exist (in parallel for speed)
        valid_urls = []
        for url in urls_to_check:
            try:
                response = self.session.head(url, timeout=3, allow_redirects=True)
                if response.status_code == 200:
                    valid_urls.append(url)
                    logger.info(f"[Licitor] Found auction date: {url.split('/')[-1]}")
            except:
                pass

        logger.info(f"[Licitor] Found {len(valid_urls)} valid auction dates for {tribunal_slug}")
        return valid_urls

    def parse_auction_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse auction listing page"""
        auctions = []

        # Find auction cards - typical structure on Licitor
        cards = soup.select(".annonce-card, .vente-item, article.annonce")

        if not cards:
            # Try alternative selectors
            cards = soup.select("[data-annonce-id], .liste-ventes a")

        for card in cards:
            try:
                auction_data = self._parse_card(card)
                if auction_data:
                    auctions.append(auction_data)
            except Exception as e:
                logger.warning(f"[Licitor] Error parsing card: {e}")

        return auctions

    def _parse_card(self, card) -> Optional[Dict[str, Any]]:
        """Parse individual auction card from list"""
        data = {}

        # Get URL
        link = card.find("a", href=True)
        if link:
            href = link.get("href", "")
            if not href.startswith("http"):
                href = f"{self.base_url}{href}"
            data["url"] = href

        # Extract address/location
        location = card.select_one(".localisation, .adresse, .ville")
        if location:
            data["location_text"] = location.get_text(strip=True)

        # Extract price
        price_elem = card.select_one(".mise-a-prix, .prix, .price")
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            data["mise_a_prix"] = self._parse_price(price_text)

        # Extract date
        date_elem = card.select_one(".date-vente, .date, .auction-date")
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            data["date_vente_text"] = date_text

        # Extract type
        type_elem = card.select_one(".type-bien, .nature")
        if type_elem:
            data["type_text"] = type_elem.get_text(strip=True)

        return data if data.get("url") else None

    def parse_auction_detail(self, url: str) -> Optional[Auction]:
        """Parse individual auction page"""
        soup = self.fetch_page(url)
        if not soup:
            return None

        auction = Auction()
        auction.source = "licitor"
        auction.url = url

        # Extract source ID from URL
        match = re.search(r"/annonce/(\d+)/", url)
        if match:
            auction.source_id = match.group(1)

        # Parse main content
        self._parse_location(soup, auction)
        self._parse_property_details(soup, auction)
        self._parse_dates(soup, auction)
        self._parse_price(soup, auction)
        self._parse_tribunal(soup, auction)
        self._parse_pv_link(soup, auction)
        self._parse_lawyer(soup, auction)

        return auction

    def _parse_location(self, soup: BeautifulSoup, auction: Auction):
        """Extract location information - IMPORTANT: avoid confusing with lawyer's address"""
        text = soup.get_text()

        # Split text to get only the property section (BEFORE lawyer section)
        # Lawyer section typically starts with "Maître", "Avocat", "Cabinet"
        lawyer_markers = ["Maître ", "Maitre ", "Avocat", "Cabinet ", "AARPI ", "SCP ", "SELARL "]
        property_text = text
        for marker in lawyer_markers:
            if marker in text:
                idx = text.find(marker)
                property_text = text[:idx]
                break

        # Look for property address in property section only
        # Pattern 1: "X, chemin/rue de Y" format (common on Licitor)
        # Include abbreviations: av., bd., ch., all., imp.
        address_patterns = [
            # Specific patterns for property addresses (with "à" or "situé")
            r"(\d+[,\s]+(?:chemin|ch\.|rue|avenue|av\.|boulevard|bd\.|allée|all\.|impasse|imp\.|cours|route|rte\.)\s+[^,\n]{5,80})\s*(?:à|,)",
            # Address with street name (exclude "place" which causes false positives with "Visite sur place")
            r"(\d+[,\s]+(?:chemin|ch\.|rue|avenue|av\.|boulevard|bd\.|allée|all\.|impasse|imp\.|cours|route|rte\.)[^,\n\d]{5,60})",
            # Place with proper name (e.g., "place Ronde", "place de la Liberté")
            r"(\d+[,\s]+place\s+(?:de\s+(?:la\s+)?)?[A-ZÀ-Ü][a-zà-ü]+[^,\n]{0,40})",
            # Street name without number
            r"((?:chemin|ch\.|rue|avenue|av\.|boulevard|bd\.|allée|all\.|impasse|imp\.|cours|route|rte\.)\s+(?:de\s+|du\s+|des\s+)?[A-ZÀ-Ü][^,\n]{5,60})",
        ]

        auction.adresse = None
        for pattern in address_patterns:
            match = re.search(pattern, property_text, re.IGNORECASE)
            if match:
                addr = match.group(1).strip()
                # Verify this is NOT a lawyer address or a visit date
                invalid_patterns = [
                    r"Tél|Tel|Fax",  # Phone/fax
                    r"\d{2}[\s\.]\d{2}[\s\.]\d{2}[\s\.]\d{2}",  # Phone number
                    r"lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche",  # Day names
                    r"janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre",  # Month names
                    r"\d{1,2}h\d{0,2}\s*à",  # Time patterns
                ]
                if not any(re.search(p, addr, re.IGNORECASE) for p in invalid_patterns):
                    # Clean up the address
                    addr = re.sub(r"\s+", " ", addr).strip()
                    # Don't take very short addresses
                    if len(addr) > 10:
                        auction.adresse = addr
                        break

        # If still no address, try to extract location from description
        if not auction.adresse:
            # Look for patterns like "Un appartement" followed by location info
            loc_match = re.search(r"(?:Un|Une|Le|La)\s+(?:appartement|maison|local|terrain|parking)[^.]*?(?:à|situé|sis)\s+([^,\n.]{10,80})", property_text, re.IGNORECASE)
            if loc_match:
                loc_text = loc_match.group(1).strip()
                # Don't use page titles or generic text
                if not re.search(r"Licitor|n°\d+|mise à prix|Bouches-du-Rhône|Var", loc_text, re.IGNORECASE):
                    auction.adresse = loc_text

        # If STILL no address and we have ville, just leave adresse as None
        # This is better than using wrong data - the map can use city-level geocoding

        # Known cities in our regions with their postal codes
        CITIES_POSTAL = {
            # Bouches-du-Rhône (13)
            "marseille": "13000", "aix-en-provence": "13100", "aix en provence": "13100",
            "aubagne": "13400", "martigues": "13500", "arles": "13200", "istres": "13800",
            "salon-de-provence": "13300", "salon de provence": "13300", "vitrolles": "13127",
            "la ciotat": "13600", "gardanne": "13120", "miramas": "13140", "tarascon": "13150",
            "marignane": "13700", "cassis": "13260", "port-de-bouc": "13110",
            # Var (83)
            "toulon": "83000", "la seyne-sur-mer": "83500", "la seyne sur mer": "83500",
            "hyères": "83400", "hyeres": "83400", "fréjus": "83600", "frejus": "83600",
            "draguignan": "83300", "six-fours-les-plages": "83140", "six fours les plages": "83140",
            "la garde": "83130", "sanary-sur-mer": "83110", "sanary sur mer": "83110",
            "bandol": "83150", "ollioules": "83190", "la valette-du-var": "83160",
            "saint-raphaël": "83700", "saint raphael": "83700", "brignoles": "83170",
            "le pradet": "83220", "carqueiranne": "83320", "la crau": "83260",
            "solliès-pont": "83210", "sollies pont": "83210", "cogolin": "83310",
            "sainte-maxime": "83120", "le lavandou": "83980", "bormes-les-mimosas": "83230",
            "carcès": "83570", "carces": "83570",
        }

        # Extract city from URL (more patterns)
        url_city_match = re.search(r"/([a-z\-]+)(?:-(\d+)(?:eme|er)?)?/var/", auction.url, re.IGNORECASE)
        if not url_city_match:
            url_city_match = re.search(r"/([a-z\-]+)(?:-(\d+)(?:eme|er)?)?/bouches-du-rhone/", auction.url, re.IGNORECASE)
        if not url_city_match:
            url_city_match = re.search(r"/(marseille|aix|toulon)[^/]*-(\d+)(?:eme|er)?/", auction.url, re.IGNORECASE)

        if url_city_match:
            city_slug = url_city_match.group(1).lower().replace("-", " ")
            district = url_city_match.group(2) if len(url_city_match.groups()) > 1 else None

            # Check if it's a known city
            if city_slug in CITIES_POSTAL:
                auction.ville = city_slug.replace("-", " ").title()
                auction.code_postal = CITIES_POSTAL[city_slug]
                auction.department = auction.code_postal[:2]
            elif city_slug.replace(" ", "-") in CITIES_POSTAL:
                auction.ville = city_slug.title()
                auction.code_postal = CITIES_POSTAL[city_slug.replace(" ", "-")]
                auction.department = auction.code_postal[:2]
            elif "marseille" in city_slug:
                auction.ville = f"Marseille {district}ème" if district else "Marseille"
                if district:
                    auction.code_postal = f"130{int(district):02d}"
                auction.department = "13"

        # If still no city, try to find in text
        if not auction.ville:
            for city_name, postal in CITIES_POSTAL.items():
                # Search for city name in property text (case insensitive)
                if re.search(rf"\b{re.escape(city_name)}\b", property_text, re.IGNORECASE):
                    auction.ville = city_name.replace("-", " ").title()
                    auction.code_postal = postal
                    auction.department = postal[:2]
                    break

        # Extract postal code from PROPERTY section only (not lawyer's 13006)
        if not auction.code_postal:
            postal_match = re.search(r"\b(13\d{3}|83\d{3})\b", property_text)
            if postal_match:
                auction.code_postal = postal_match.group(1)
                auction.department = auction.code_postal[:2]

    def _parse_property_details(self, soup: BeautifulSoup, auction: Auction):
        """Extract property details (type, surface, rooms)"""
        # Property type
        type_keywords = {
            PropertyType.APPARTEMENT: ["appartement", "appart", "studio", "f1", "f2", "f3", "f4", "f5", "t1", "t2", "t3", "t4", "t5"],
            PropertyType.MAISON: ["maison", "villa", "pavillon"],
            PropertyType.LOCAL_COMMERCIAL: ["local commercial", "commerce", "boutique", "bureau"],
            PropertyType.TERRAIN: ["terrain", "parcelle"],
            PropertyType.PARKING: ["parking", "garage", "box"],
        }

        text = soup.get_text().lower()
        for prop_type, keywords in type_keywords.items():
            if any(kw in text for kw in keywords):
                auction.type_bien = prop_type
                break

        # Surface
        surface_match = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", text)
        if surface_match:
            auction.surface = float(surface_match.group(1).replace(",", "."))

        # Number of rooms
        pieces_match = re.search(r"(\d+)\s*(?:pièces?|p\.)", text)
        if pieces_match:
            auction.nb_pieces = int(pieces_match.group(1))

        # Number of bedrooms
        chambres_match = re.search(r"(\d+)\s*(?:chambres?|ch\.)", text)
        if chambres_match:
            auction.nb_chambres = int(chambres_match.group(1))

        # Description
        desc_elem = soup.select_one(".description, .detail-bien, .annonce-description")
        if desc_elem:
            auction.description = desc_elem.get_text(strip=True)[:2000]

    def _parse_dates(self, soup: BeautifulSoup, auction: Auction):
        """Extract sale date, visit dates, judgment date"""
        text = soup.get_text()

        # Sale date patterns
        date_patterns = [
            r"(?:vente|adjudication|audience)\s+(?:le\s+)?(\d{1,2}(?:er)?\s+\w+\s+\d{4})",
            r"(\d{1,2}(?:er)?\s+\w+\s+\d{4})\s+à\s+\d{1,2}h",
            r"le\s+(\d{1,2}/\d{1,2}/\d{4})"
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                auction.date_vente = self._parse_french_date(date_str)
                if auction.date_vente:
                    break

        # Sale time
        time_match = re.search(r"à\s+(\d{1,2})\s*[hH]\s*(\d{0,2})?", text)
        if time_match:
            hour = time_match.group(1)
            minute = time_match.group(2) or "00"
            auction.heure_vente = f"{hour}h{minute}"

        # Visit dates - Licitor format: "Visite sur place lundi 29 décembre 2025 de 14h à 15h"
        visit_patterns = [
            # Main Licitor format: "Visite sur place [jour] [date] [mois] [année] de [heure] à [heure]"
            r"[Vv]isite\s+(?:sur\s+place\s+)?(?:\w+\s+)?(\d{1,2}(?:er)?\s+\w+\s+\d{4})\s+de\s+(\d{1,2})[hH](?:\d{0,2})?\s*(?:à|-)?\s*(\d{1,2})?[hH]?",
            # Alternative: "Visite le [date]"
            r"[Vv]isite[s]?\s+(?:le[s]?\s+)?(\d{1,2}(?:er)?\s+\w+\s+\d{4})",
            # With time: "Visite le [date] à [heure]"
            r"[Vv]isite[s]?\s+(?:le[s]?\s+)?(\d{1,2}(?:er)?\s+\w+\s+\d{4})\s+à\s+(\d{1,2})[hH]",
            # Date format DD/MM/YYYY
            r"[Vv]isite[s]?\s*:?\s*(\d{1,2}/\d{1,2}/\d{4})",
        ]

        for pattern in visit_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                date_str = match.group(1)
                parsed_date = self._parse_french_date(date_str)
                if parsed_date:
                    # Extract time if available
                    hour = 14  # Default to 14h
                    minute = 0
                    if len(match.groups()) >= 2 and match.group(2):
                        try:
                            hour = int(match.group(2))
                        except:
                            pass

                    visit_datetime = datetime(parsed_date.year, parsed_date.month, parsed_date.day, hour, minute)
                    if visit_datetime not in auction.dates_visite:
                        auction.dates_visite.append(visit_datetime)

            if auction.dates_visite:
                break

    def _parse_french_date(self, date_str: str) -> Optional[date]:
        """Parse French date string to date object"""
        months = {
            "janvier": 1, "février": 2, "mars": 3, "avril": 4,
            "mai": 5, "juin": 6, "juillet": 7, "août": 8,
            "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
        }

        # Try DD/MM/YYYY format
        match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
        if match:
            day, month, year = map(int, match.groups())
            try:
                return date(year, month, day)
            except ValueError:
                pass

        # Try "15 janvier 2024" format
        match = re.match(r"(\d{1,2})(?:er)?\s+(\w+)\s+(\d{4})", date_str)
        if match:
            day = int(match.group(1))
            month_str = match.group(2).lower()
            year = int(match.group(3))
            month = months.get(month_str)
            if month:
                try:
                    return date(year, month, day)
                except ValueError:
                    pass

        return None

    def _parse_price(self, soup: BeautifulSoup, auction: Auction):
        """Extract mise à prix"""
        price_selectors = [
            ".mise-a-prix", ".prix", ".price",
            "[data-price]", ".montant"
        ]

        for selector in price_selectors:
            elem = soup.select_one(selector)
            if elem:
                price = self._extract_price_value(elem.get_text())
                if price:
                    auction.mise_a_prix = price
                    break

        # Try from text
        if not auction.mise_a_prix:
            text = soup.get_text()
            match = re.search(r"mise\s+[àa]\s+prix\s*:?\s*([\d\s]+)\s*(?:€|euros?)", text, re.IGNORECASE)
            if match:
                auction.mise_a_prix = self._extract_price_value(match.group(1))

    def _extract_price_value(self, text: str) -> Optional[float]:
        """Extract numeric price from text"""
        # Remove spaces and non-numeric characters except comma/dot
        cleaned = re.sub(r"[^\d,.]", "", text.replace(" ", ""))
        # Handle French number format (1.000,00 or 1 000,00)
        cleaned = cleaned.replace(",", ".")
        if cleaned.count(".") > 1:
            # Multiple dots = thousand separator
            parts = cleaned.rsplit(".", 1)
            cleaned = parts[0].replace(".", "") + "." + parts[1] if len(parts) > 1 else parts[0].replace(".", "")

        try:
            return float(cleaned)
        except ValueError:
            return None

    def _parse_tribunal(self, soup: BeautifulSoup, auction: Auction):
        """Extract tribunal information"""
        text = soup.get_text()
        for slug, name in self.TRIBUNAUX.items():
            if name.lower() in text.lower() or slug.replace("-", " ") in text.lower():
                auction.tribunal = name
                break

    def _parse_pv_link(self, soup: BeautifulSoup, auction: Auction):
        """Extract link to PV or cahier des charges"""
        pdf_patterns = [
            "cahier", "charge", "pv", "procès", "verbal",
            "document", "telecharger", "pdf"
        ]

        for link in soup.find_all("a", href=True):
            href = link.get("href", "").lower()
            text = link.get_text().lower()

            if any(p in href or p in text for p in pdf_patterns):
                if ".pdf" in href or "pdf" in href:
                    auction.pv_url = href if href.startswith("http") else f"{self.base_url}{href}"
                    auction.pv_status = PVStatus.A_TELECHARGER
                    break

        if not auction.pv_url:
            auction.pv_status = PVStatus.A_DEMANDER

    def _parse_lawyer(self, soup: BeautifulSoup, auction: Auction):
        """Extract lawyer/cabinet name and contact info from the page"""
        text = soup.get_text()

        # Look for "Maître" or "Me" patterns
        lawyer_patterns = [
            r"(?:Maître|Me|Mtre)\s+([A-ZÀ-Ü][a-zà-ü]+(?:[- ][A-ZÀ-Ü][a-zà-ü]+)*)",
            r"(?:Cabinet|SCP|SELARL)\s+([A-ZÀ-Ü][^,\n]{3,50})",
            r"Avocat\s*:\s*([A-ZÀ-Ü][^,\n]{3,50})",
        ]

        for pattern in lawyer_patterns:
            match = re.search(pattern, text)
            if match:
                auction.avocat_nom = match.group(1).strip()
                break

        # Also try from specific HTML elements
        if not auction.avocat_nom:
            lawyer_elem = soup.select_one(".avocat, .cabinet, .vendeur, [class*='avocat'], [class*='lawyer']")
            if lawyer_elem:
                auction.avocat_nom = lawyer_elem.get_text(strip=True)[:100]

        # Extract phone number
        phone_match = re.search(r"(?:Tél\.?|Tel\.?|Téléphone)\s*:?\s*([\d\s\.]+)", text)
        if not phone_match:
            phone_match = re.search(r"(0[1-9][\s\.]?\d{2}[\s\.]?\d{2}[\s\.]?\d{2}[\s\.]?\d{2})", text)
        if phone_match:
            auction.avocat_telephone = phone_match.group(1).strip()

        # Extract email
        email_links = soup.find_all("a", href=re.compile(r"mailto:"))
        if email_links:
            email = email_links[0].get("href", "").replace("mailto:", "").split("?")[0]
            auction.avocat_email = email

        # Extract cabinet/firm name
        cabinet_match = re.search(r"(?:AARPI|SCP|SELARL|Cabinet)\s+([^,\n]+)", text)
        if cabinet_match:
            auction.avocat_cabinet = cabinet_match.group(0).strip()[:100]

        # Extract address
        address_match = re.search(r"(\d+[,\s]+(?:rue|avenue|boulevard|cours|place)[^-\n]{5,80}[-\s]+\d{5}\s+\w+)", text, re.IGNORECASE)
        if address_match:
            auction.avocat_adresse = address_match.group(1).strip()

    def extract_lawyer_info(self, soup: BeautifulSoup) -> Optional[Lawyer]:
        """Extract lawyer/cabinet information"""
        lawyer = Lawyer()

        # Common patterns for lawyer info
        lawyer_section = soup.select_one(".avocat, .cabinet, .vendeur, .contact-avocat")

        if lawyer_section:
            # Name
            name_elem = lawyer_section.select_one(".nom, .name, h3, strong")
            if name_elem:
                lawyer.nom = name_elem.get_text(strip=True)

            # Cabinet name
            cabinet_elem = lawyer_section.select_one(".cabinet, .societe")
            if cabinet_elem:
                lawyer.cabinet = cabinet_elem.get_text(strip=True)

            # Phone
            phone_elem = lawyer_section.select_one("[href^='tel:'], .telephone, .phone")
            if phone_elem:
                lawyer.telephone = phone_elem.get_text(strip=True)

            # Email
            email_elem = lawyer_section.select_one("[href^='mailto:'], .email")
            if email_elem:
                href = email_elem.get("href", "")
                lawyer.email = href.replace("mailto:", "") if href else email_elem.get_text(strip=True)

            # Website
            site_elem = lawyer_section.select_one("a[href*='avocat'], a.site-web")
            if site_elem:
                lawyer.site_web = site_elem.get("href", "")

        # Try extracting from full text if section not found
        if not lawyer.nom:
            text = soup.get_text()
            me_match = re.search(r"(?:Maître|Me)\s+([A-ZÀ-Ü][a-zà-ü]+(?:\s+[A-ZÀ-Ü][a-zà-ü]+)*)", text)
            if me_match:
                lawyer.nom = f"Me {me_match.group(1)}"

        return lawyer if lawyer.nom else None

    def scrape_all_tribunaux(self) -> List[Auction]:
        """Scrape auctions from all monitored tribunaux"""
        all_auctions = []

        for slug, name in self.TRIBUNAUX.items():
            logger.info(f"[Licitor] Scraping {name}...")

            # Find all auction date URLs for this tribunal
            auction_urls = self.find_tribunal_auction_urls(slug)
            logger.info(f"[Licitor] Found {len(auction_urls)} auction dates for {name}")

            for url in auction_urls:
                soup = self.fetch_page(url)
                if soup:
                    # Find individual auction links on the date page
                    auction_links = soup.select("a[href*='/annonce/']")
                    for link in auction_links:
                        href = link.get("href", "")
                        full_url = href if href.startswith("http") else f"{self.base_url}{href}"

                        # Parse the auction detail page
                        auction = self.parse_auction_detail(full_url)
                        if auction:
                            auction.tribunal = name
                            all_auctions.append(auction)

        logger.info(f"[Licitor] Total: {len(all_auctions)} auctions scraped")
        return all_auctions
