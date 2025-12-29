"""
Scraper for encheres-publiques.com
"""
import re
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup
from loguru import logger

from .base_scraper import BaseScraper
from src.storage.models import Auction, Lawyer, PropertyType, AuctionStatus, PVStatus


class EncherePubliquesScraper(BaseScraper):
    """Scraper for encheres-publiques.com"""

    # Cities to monitor with their URL slugs - Paris et petite couronne
    CITIES = {
        "paris-75": "Paris",
        "boulogne-billancourt-92": "Boulogne-Billancourt",
        "nanterre-92": "Nanterre",
        "montreuil-93": "Montreuil",
        "saint-denis-93": "Saint-Denis",
        "bobigny-93": "Bobigny",
        "creteil-94": "Créteil",
        "vitry-sur-seine-94": "Vitry-sur-Seine",
        "champigny-sur-marne-94": "Champigny-sur-Marne",
    }

    def __init__(self):
        super().__init__(
            name="EnchèresPubliques",
            base_url="https://www.encheres-publiques.com"
        )

    def get_auction_list_url(self, page: int = 1) -> str:
        """Build URL for auction listing"""
        return f"{self.base_url}/encheres/immobilier?page={page}"

    def get_city_url(self, city_slug: str, page: int = 1) -> str:
        """Get URL for specific city"""
        # Try regional search for departments 13 and 83
        return f"{self.base_url}/encheres/immobilier?localisation={city_slug}&page={page}"

    def get_department_url(self, department: str, page: int = 1) -> str:
        """Get URL for department search"""
        return f"{self.base_url}/encheres/immobilier?departement={department}&page={page}"

    def parse_auction_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse auction listing page"""
        auctions = []
        seen_urls = set()

        # Find property links with pattern: /encheres/immobilier/[type]/[city]/[description]_[id]
        # Property types: appartements, maisons, immeubles, terrains, parkings, locaux-commerciaux
        property_types = ["appartements", "maisons", "immeubles", "terrains", "parkings", "locaux-commerciaux", "biens-exception"]

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")

            # Check if it's a property page (contains type and ends with _[id])
            if "/encheres/immobilier/" in href and "_" in href:
                # Verify it's a property type, not an event
                if any(f"/encheres/immobilier/{ptype}/" in href for ptype in property_types):
                    full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        auctions.append({"url": full_url})

        # Fallback: try old selectors
        if not auctions:
            cards = soup.select(".card-vente, .vente-card, article.vente, .annonce-item")
            for card in cards:
                try:
                    auction_data = self._parse_card(card)
                    if auction_data and auction_data.get("url"):
                        auctions.append(auction_data)
                except Exception as e:
                    logger.warning(f"[EnchèresPubliques] Error parsing card: {e}")

        return auctions

    def _parse_card(self, card) -> Optional[Dict[str, Any]]:
        """Parse individual auction card"""
        data = {}

        # Get URL
        link = card.find("a", href=True)
        if link:
            href = link.get("href", "")
            if not href.startswith("http"):
                href = f"{self.base_url}{href}"
            data["url"] = href

        # Extract title/description
        title = card.select_one(".titre, .title, h3, h4")
        if title:
            data["title"] = title.get_text(strip=True)

        # Location
        location = card.select_one(".lieu, .location, .adresse")
        if location:
            data["location"] = location.get_text(strip=True)
            # Extract postal code
            cp_match = re.search(r"\b(13\d{3}|83\d{3})\b", data["location"])
            if cp_match:
                data["code_postal"] = cp_match.group(1)

        # Price
        price_elem = card.select_one(".prix, .price, .mise-a-prix")
        if price_elem:
            data["price_text"] = price_elem.get_text(strip=True)

        # Date
        date_elem = card.select_one(".date, .date-vente")
        if date_elem:
            data["date_text"] = date_elem.get_text(strip=True)

        # Status (upcoming, ongoing, etc.)
        status_elem = card.select_one(".statut, .status, .badge")
        if status_elem:
            data["status"] = status_elem.get_text(strip=True).lower()

        # Image
        img = card.find("img")
        if img:
            data["image_url"] = img.get("src", "")

        return data if data.get("url") else None

    def parse_auction_detail(self, url: str) -> Optional[Auction]:
        """Parse individual auction page with full details"""
        soup = self.fetch_page(url)
        if not soup:
            return None

        # Check if this is a judicial auction (not notarial)
        if not self._is_judicial_auction(soup):
            logger.info(f"[EnchèresPubliques] Skipping notarial auction: {url}")
            return None

        auction = Auction()
        auction.source = "encheres_publiques"
        auction.url = url

        # Extract source ID from URL
        match = re.search(r"_(\d+)$|/(\d+)(?:\?|$)", url)
        if match:
            auction.source_id = match.group(1) or match.group(2)

        # Parse all content
        self._parse_header(soup, auction)
        self._parse_details(soup, auction)
        self._parse_detailed_description(soup, auction)
        self._parse_dates_times(soup, auction)
        self._parse_pricing(soup, auction)
        self._parse_photos(soup, auction)
        self._parse_all_documents(soup, auction)
        self._parse_occupation(soup, auction)
        self._parse_cadastre(soup, auction)
        self._parse_lawyer_details(soup, auction)

        return auction

    def _is_judicial_auction(self, soup: BeautifulSoup) -> bool:
        """Check if this is a judicial auction (not notarial/voluntary sale)"""
        text = soup.get_text().lower()

        # Indicators of NOTARIAL/VOLUNTARY sales (to EXCLUDE)
        notarial_indicators = [
            "vente volontaire",
            "notaire",
            "notaires",
            "étude notariale",
            "office notarial",
            "vente aux enchères notariale",
            "organisée par me ",  # "organisée par Me Dupont" (notaire)
            "organisé par me ",
        ]

        # Indicators of JUDICIAL sales (to INCLUDE)
        judicial_indicators = [
            "tribunal judiciaire",
            "tribunal de grande instance",
            "vente judiciaire",
            "vente sur saisie",
            "adjudication judiciaire",
            "avocat poursuivant",
            "saisie immobilière",
            "liquidation judiciaire",
        ]

        # Check for notarial indicators
        has_notarial = any(indicator in text for indicator in notarial_indicators)

        # Check for judicial indicators
        has_judicial = any(indicator in text for indicator in judicial_indicators)

        # If clearly notarial and NOT judicial, exclude
        if has_notarial and not has_judicial:
            return False

        # If clearly judicial, include
        if has_judicial:
            return True

        # Default: include if we can't determine (might be judicial)
        # But be more strict - if "notaire" appears, exclude
        if "notaire" in text:
            return False

        return True

    def _parse_header(self, soup: BeautifulSoup, auction: Auction):
        """Parse header section with title and location"""
        # Title
        title = soup.select_one("h1, .titre-vente, .page-title")
        if title:
            auction.description = title.get_text(strip=True)

        # Address
        address_elem = soup.select_one(".adresse, .localisation, [itemprop='address']")
        if address_elem:
            auction.adresse = address_elem.get_text(strip=True)

        # If no specific address, try to extract from title
        if not auction.adresse and auction.description:
            auction.adresse = auction.description

        # Get full page text for extraction
        full_text = soup.get_text()

        # Postal code - look in full page text
        cp_match = re.search(r"\b(13\d{3}|83\d{3})\b", full_text)
        if cp_match:
            auction.code_postal = cp_match.group(1)
            auction.department = auction.code_postal[:2]

        # Try to extract from URL (e.g., marseille-13, toulon-83)
        url = auction.url or ""
        url_city_match = re.search(r'/([a-z\-]+)-(\d{2})/', url)
        if url_city_match:
            city_from_url = url_city_match.group(1).replace("-", " ").title()
            dept_from_url = url_city_match.group(2)

            # Set department if not already set
            if not auction.department:
                auction.department = dept_from_url

            # Set default postal code based on department
            if not auction.code_postal:
                auction.code_postal = f"{dept_from_url}000"

        # City extraction - improved patterns
        city_patterns = [
            # "à Marseille 14ème" or "à Marseille"
            r"à\s+(Marseille(?:\s+\d+[eè]me)?)",
            r"à\s+(Toulon(?:\s+\d+[eè]me)?)",
            r"à\s+(Aix-en-Provence)",
            # Generic city after "à"
            r"à\s+([A-ZÀ-Ü][a-zà-ü\-]+(?:\s+\d+[eè]me)?)",
            # After postal code
            r"(?:13\d{3}|83\d{3})\s+([A-ZÀ-Ü][a-zà-ü\-]+(?:\s+[A-ZÀ-Ü][a-zà-ü\-]+)*)",
        ]

        for pattern in city_patterns:
            match = re.search(pattern, full_text)
            if match:
                city = match.group(1).strip()
                # Clean up common issues
                if city and len(city) > 2:
                    auction.ville = city
                    break

        # Fallback: extract from URL
        if not auction.ville and url_city_match:
            auction.ville = url_city_match.group(1).replace("-", " ").title()

        # Handle Marseille arrondissements
        if auction.ville and "marseille" in auction.ville.lower():
            # Extract arrondissement from description
            arr_match = re.search(r"Marseille\s*(\d+)[eè]?(?:me)?", full_text, re.IGNORECASE)
            if arr_match:
                arr = arr_match.group(1)
                auction.ville = f"Marseille {arr}ème"
                # Set postal code for arrondissement
                if not auction.code_postal or auction.code_postal == "13000":
                    auction.code_postal = f"130{arr.zfill(2)}"

    def _parse_details(self, soup: BeautifulSoup, auction: Auction):
        """Parse property details"""
        text = soup.get_text().lower()

        # Property type
        type_map = {
            PropertyType.APPARTEMENT: ["appartement", "studio", "duplex", "loft"],
            PropertyType.MAISON: ["maison", "villa", "pavillon", "propriété"],
            PropertyType.LOCAL_COMMERCIAL: ["local", "commerce", "bureau", "boutique"],
            PropertyType.TERRAIN: ["terrain", "parcelle", "foncier"],
            PropertyType.PARKING: ["parking", "garage", "box", "stationnement"],
        }

        for prop_type, keywords in type_map.items():
            if any(kw in text for kw in keywords):
                auction.type_bien = prop_type
                break

        # Surface area
        surface_patterns = [
            r"surface\s*(?:de\s*)?(\d+(?:[.,]\d+)?)\s*m[²2]",
            r"(\d+(?:[.,]\d+)?)\s*m[²2]",
        ]
        for pattern in surface_patterns:
            match = re.search(pattern, text)
            if match:
                auction.surface = float(match.group(1).replace(",", "."))
                break

        # Rooms
        pieces_match = re.search(r"(\d+)\s*(?:pièces?|p\.)", text)
        if pieces_match:
            auction.nb_pieces = int(pieces_match.group(1))

        chambres_match = re.search(r"(\d+)\s*(?:chambres?|ch\.)", text)
        if chambres_match:
            auction.nb_chambres = int(chambres_match.group(1))

        # Floor
        etage_match = re.search(r"(\d+)(?:e|ème|er)?\s*étage", text)
        if etage_match:
            auction.etage = int(etage_match.group(1))

    def _parse_dates_times(self, soup: BeautifulSoup, auction: Auction):
        """Parse dates and times"""
        text = soup.get_text()

        # Sale date
        date_patterns = [
            r"(?:vente|adjudication)\s+(?:le\s+)?(\d{1,2}/\d{1,2}/\d{4})",
            r"(\d{1,2}/\d{1,2}/\d{4})\s+à\s+\d{1,2}h",
            r"(\d{1,2}\s+\w+\s+\d{4})"
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                parsed = self._parse_date(date_str)
                if parsed:
                    auction.date_vente = parsed
                    break

        # Time
        time_match = re.search(r"à\s+(\d{1,2})[hH:](\d{0,2})", text)
        if time_match:
            h = time_match.group(1)
            m = time_match.group(2) or "00"
            auction.heure_vente = f"{h}h{m}"

        # Visit dates
        visit_section = soup.select_one(".visites, .dates-visite")
        if visit_section:
            visit_text = visit_section.get_text()
            date_matches = re.findall(r"(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\s+\w+\s+\d{4})", visit_text)
            for date_str in date_matches:
                parsed = self._parse_date(date_str)
                if parsed:
                    auction.dates_visite.append(datetime.combine(parsed, datetime.min.time()))

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date string"""
        months = {
            "janvier": 1, "février": 2, "mars": 3, "avril": 4,
            "mai": 5, "juin": 6, "juillet": 7, "août": 8,
            "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
        }

        # DD/MM/YYYY
        match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
        if match:
            try:
                return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            except ValueError:
                pass

        # "15 janvier 2024"
        match = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", date_str)
        if match:
            day = int(match.group(1))
            month = months.get(match.group(2).lower())
            year = int(match.group(3))
            if month:
                try:
                    return date(year, month, day)
                except ValueError:
                    pass

        return None

    def _parse_pricing(self, soup: BeautifulSoup, auction: Auction):
        """Parse pricing information"""
        # Mise à prix from HTML elements
        price_elem = soup.select_one(".mise-a-prix, .prix, .price")
        if price_elem:
            price_text = price_elem.get_text()
            auction.mise_a_prix = self._extract_price(price_text)

        if not auction.mise_a_prix:
            text = soup.get_text()
            match = re.search(r"mise\s+[àa]\s+prix\s*:?\s*([\d\s,\.]+)\s*€?", text, re.IGNORECASE)
            if match:
                auction.mise_a_prix = self._extract_price(match.group(1))

        # Try to extract from Next.js script data
        if not auction.mise_a_prix:
            for script in soup.find_all("script"):
                script_text = script.string or ""
                if len(script_text) > 1000:
                    # Look for prix_plancher or mise_a_prix in script
                    patterns = [
                        r'"prix_plancher"\s*:\s*(\d+)',
                        r'"mise_a_prix"\s*:\s*(\d+)',
                        r'prix_plancher[":]+\s*(\d+)',
                        r'mise[_]?a[_]?prix[":]+\s*(\d+)',
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, script_text, re.IGNORECASE)
                        if match:
                            try:
                                auction.mise_a_prix = float(match.group(1))
                                break
                            except ValueError:
                                pass
                    if auction.mise_a_prix:
                        break

        # Tribunal
        tribunal_map = {
            "marseille": "Tribunal Judiciaire de Marseille",
            "aix": "Tribunal Judiciaire d'Aix-en-Provence",
            "toulon": "Tribunal Judiciaire de Toulon"
        }

        for city, tribunal in tribunal_map.items():
            if city in soup.get_text().lower():
                auction.tribunal = tribunal
                break

    def _extract_price(self, text: str) -> Optional[float]:
        """Extract price from text"""
        cleaned = re.sub(r"[^\d,.]", "", text.replace(" ", ""))
        cleaned = cleaned.replace(",", ".")

        if cleaned.count(".") > 1:
            parts = cleaned.rsplit(".", 1)
            cleaned = parts[0].replace(".", "") + ("." + parts[1] if len(parts) > 1 else "")

        try:
            return float(cleaned)
        except ValueError:
            return None

    def _parse_detailed_description(self, soup: BeautifulSoup, auction: Auction):
        """Parse detailed property description/composition"""
        # Look for description in various sections
        desc_selectors = [
            ".description-bien", ".detail-bien", ".composition",
            "[data-description]", ".content-description", ".bloc-description"
        ]

        for selector in desc_selectors:
            desc_elem = soup.select_one(selector)
            if desc_elem:
                auction.description_detaillee = desc_elem.get_text(separator="\n", strip=True)
                return

        # Try to extract from JSON data in script tags
        for script in soup.find_all("script"):
            script_text = script.string or ""
            if "description" in script_text.lower():
                # Look for JSON patterns
                desc_match = re.search(r'"description"\s*:\s*"([^"]+)"', script_text)
                if desc_match:
                    desc = desc_match.group(1)
                    # Unescape JSON string
                    desc = desc.replace("\\n", "\n").replace("\\r", "").replace('\\"', '"')
                    auction.description_detaillee = desc
                    return

        # Fallback: look for detailed text in main content
        main_content = soup.select_one("main, .main-content, article, .fiche-lot")
        if main_content:
            # Find paragraphs with composition details
            for p in main_content.find_all(["p", "div"]):
                text = p.get_text(strip=True)
                if any(kw in text.lower() for kw in ["rez-de-chaussée", "étage", "comprenant", "composé"]):
                    auction.description_detaillee = text
                    break

    def _parse_photos(self, soup: BeautifulSoup, auction: Auction):
        """Parse photo gallery URLs including Street View"""
        photos = []

        # Look for gallery images
        gallery_selectors = [
            ".gallery img", ".photos img", ".carousel img",
            ".slider img", "[data-gallery] img", ".photo-lot img",
            ".swiper-slide img", ".fotorama img"
        ]

        for selector in gallery_selectors:
            for img in soup.select(selector):
                src = img.get("src") or img.get("data-src") or img.get("data-lazy")
                if src:
                    if not src.startswith("http"):
                        src = f"{self.base_url}{src}"
                    if src not in photos and "placeholder" not in src.lower():
                        photos.append(src)

        # Look for images with class "photo" (Next.js format)
        for img in soup.select("img.photo, .photos img, [class*='photo'] img"):
            # Check srcset for best quality image
            srcset = img.get("srcset", "")
            if srcset:
                # Get the largest image from srcset
                srcset_parts = srcset.split(",")
                for part in reversed(srcset_parts):
                    part = part.strip()
                    if part:
                        url = part.split(" ")[0]
                        # Decode Next.js image URL
                        if "/_next/image" in url:
                            # Extract original URL from Next.js wrapper
                            url_match = re.search(r'url=([^&]+)', url)
                            if url_match:
                                from urllib.parse import unquote
                                original_url = unquote(url_match.group(1))
                                if original_url not in photos:
                                    photos.append(original_url)
                                break
                        elif url.startswith("http") and url not in photos:
                            photos.append(url)
                            break

            # Also check src
            src = img.get("src", "")
            if src and "/_next/image" in src:
                url_match = re.search(r'url=([^&]+)', src)
                if url_match:
                    from urllib.parse import unquote
                    original_url = unquote(url_match.group(1))
                    if original_url not in photos:
                        photos.append(original_url)
            elif src and src.startswith("http") and src not in photos and "placeholder" not in src.lower():
                photos.append(src)

        # Try JSON data for photos
        for script in soup.find_all("script"):
            script_text = script.string or ""
            # Look for photo arrays
            photo_matches = re.findall(r'/static/lot/photo/[^"\']+\.jpg', script_text)
            for photo in photo_matches:
                full_url = f"{self.base_url}{photo}"
                if full_url not in photos:
                    photos.append(full_url)

            # Look for Street View URLs
            streetview_matches = re.findall(r'streetview\?adresse_id=\d+[^"\']*', script_text)
            for sv in streetview_matches:
                full_url = f"{self.base_url}/back/services/{sv}"
                if full_url not in photos:
                    photos.append(full_url)

        # Also check data attributes
        for elem in soup.select("[data-photos], [data-images]"):
            data = elem.get("data-photos") or elem.get("data-images")
            if data:
                try:
                    import json
                    photo_list = json.loads(data)
                    for p in photo_list:
                        url = p if isinstance(p, str) else p.get("url", p.get("src", ""))
                        if url and url not in photos:
                            if not url.startswith("http"):
                                url = f"{self.base_url}{url}"
                            photos.append(url)
                except:
                    pass

        auction.photos = photos[:20]  # Limit to 20 photos

    def _parse_all_documents(self, soup: BeautifulSoup, auction: Auction):
        """Parse all document links (cahier des charges, PV, diagnostics, etc.)"""
        documents = []
        doc_type_map = {
            "cahier": "Cahier des conditions de vente",
            "pv": "Procès-verbal de description",
            "procès": "Procès-verbal de description",
            "diagnostic": "Diagnostics immobiliers",
            "avis": "Avis de vente",
            "jugement": "Jugement",
            "expertise": "Rapport d'expertise",
            "urbanisme": "Certificat d'urbanisme",
            "spanc": "Rapport SPANC",
        }

        # Extract from JSON data in script tags (encheres-publiques format)
        # Pattern: "file":"filename.pdf","nom":"Document Name"
        for script in soup.find_all("script"):
            script_text = script.string or ""
            if "LotDocument" in script_text:
                # Find all LotDocument entries
                doc_matches = re.findall(
                    r'"file"\s*:\s*"([^"]+\.pdf)"\s*,\s*"nom"\s*:\s*"([^"]+)"',
                    script_text
                )
                for filename, nom in doc_matches:
                    # Build full URL
                    full_url = f"{self.base_url}/static/lot/document/{filename}"

                    # Determine document type
                    doc_type = nom  # Use the actual name from the site
                    nom_lower = nom.lower()

                    doc_entry = {
                        "nom": nom,
                        "url": full_url,
                        "type": doc_type
                    }

                    if doc_entry not in documents:
                        documents.append(doc_entry)

                        # Set PV status if we found the PV
                        if "procès" in nom_lower or "pv" in nom_lower:
                            auction.pv_url = full_url
                            auction.pv_status = PVStatus.A_TELECHARGER

        # Fallback: Find PDF links in HTML
        if not documents:
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True)

                if ".pdf" in href.lower():
                    full_url = href if href.startswith("http") else f"{self.base_url}{href}"

                    # Determine document type
                    doc_type = "Autre document"
                    for pattern, name in doc_type_map.items():
                        if pattern in text.lower() or pattern in href.lower():
                            doc_type = name
                            break

                    doc_entry = {
                        "nom": text or doc_type,
                        "url": full_url,
                        "type": doc_type
                    }

                    if doc_entry not in documents:
                        documents.append(doc_entry)

        auction.documents = documents

        if not auction.pv_url and not documents:
            auction.pv_status = PVStatus.A_DEMANDER
        elif auction.pv_url:
            auction.pv_status = PVStatus.A_TELECHARGER

    def _parse_occupation(self, soup: BeautifulSoup, auction: Auction):
        """Parse occupation status (libre/occupé)"""
        text = soup.get_text().lower()

        # Check for explicit occupation fields
        occupation_patterns = [
            (r"occupation[^\n]*?:\s*([^\n,]+)", None),
            (r"(libre\s+de\s+toute\s+occupation)", "Libre"),
            (r"(occupé|occupée)", "Occupé"),
            (r"bien\s+(libre|vacant)", "Libre"),
            (r"(locataire|bail|location)", "Occupé"),
        ]

        for pattern, default_value in occupation_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                auction.occupation = default_value or match.group(1).strip().capitalize()
                return

        # Check JSON data
        for script in soup.find_all("script"):
            script_text = script.string or ""
            occ_match = re.search(r'"critere_occupation[^"]*"\s*:\s*"([^"]+)"', script_text)
            if occ_match:
                auction.occupation = occ_match.group(1)
                return

    def _parse_cadastre(self, soup: BeautifulSoup, auction: Auction):
        """Parse cadastral reference"""
        text = soup.get_text()

        # Various cadastral patterns
        cadastre_patterns = [
            r"[Ss]ection\s+([A-Z]{1,2})\s*n[°º]?\s*(\d+)",
            r"[Cc]adastr[ée]\s*:?\s*([A-Z]{1,2}\s*\d+)",
            r"[Pp]arcelle\s+([A-Z]{1,2}\s*\d+)",
            r"[Rr]éférence\s+cadastrale\s*:?\s*([A-Z0-9\s]+)",
        ]

        for pattern in cadastre_patterns:
            match = re.search(pattern, text)
            if match:
                if len(match.groups()) >= 2:
                    auction.cadastre = f"Section {match.group(1)} n°{match.group(2)}"
                else:
                    auction.cadastre = match.group(1).strip()
                return

    def _parse_lawyer_details(self, soup: BeautifulSoup, auction: Auction):
        """Parse lawyer/avocat information"""
        # Look for lawyer section
        lawyer_selectors = [
            ".avocat", ".vendeur", ".professionnel", ".contact-avocat",
            ".poursuivant", "[data-avocat]", ".bloc-avocat"
        ]

        for selector in lawyer_selectors:
            section = soup.select_one(selector)
            if section:
                # Name
                name_elem = section.select_one(".nom, .name, h3, h4, strong, .titre")
                if name_elem:
                    auction.avocat_nom = name_elem.get_text(strip=True)

                # Cabinet
                cabinet_elem = section.select_one(".cabinet, .societe")
                if cabinet_elem:
                    auction.avocat_cabinet = cabinet_elem.get_text(strip=True)

                # Phone
                phone_elem = section.select_one("a[href^='tel:'], .tel, .telephone, .phone")
                if phone_elem:
                    phone = phone_elem.get("href", "").replace("tel:", "") or phone_elem.get_text(strip=True)
                    auction.avocat_telephone = phone

                # Email
                email_elem = section.select_one("a[href^='mailto:']")
                if email_elem:
                    auction.avocat_email = email_elem.get("href", "").replace("mailto:", "")

                # Website
                web_elem = section.select_one("a.site, a.website, a[href*='avocat']")
                if web_elem:
                    auction.avocat_site_web = web_elem.get("href", "")

                # Address
                addr_elem = section.select_one(".adresse, .address")
                if addr_elem:
                    auction.avocat_adresse = addr_elem.get_text(strip=True)

                return

        # Try extracting from JSON data
        for script in soup.find_all("script"):
            script_text = script.string or ""
            if "avocat" in script_text.lower() or "poursuivant" in script_text.lower():
                # Look for phone numbers
                phone_match = re.search(r'"(?:phone|telephone|tel)"\s*:\s*"([^"]+)"', script_text)
                if phone_match:
                    auction.avocat_telephone = phone_match.group(1)

                # Look for names
                name_match = re.search(r'"(?:nom|name|cabinet)"\s*:\s*"([^"]+)"', script_text)
                if name_match:
                    auction.avocat_nom = name_match.group(1)

    def _parse_documents(self, soup: BeautifulSoup, auction: Auction):
        """Parse document links (PV, cahier des charges) - legacy method"""
        # Now handled by _parse_all_documents
        self._parse_all_documents(soup, auction)

    def extract_lawyer_info(self, soup: BeautifulSoup) -> Optional[Lawyer]:
        """Extract lawyer information"""
        lawyer = Lawyer()

        # Find lawyer section
        lawyer_section = soup.select_one(".avocat, .vendeur, .professionnel, .contact")

        if lawyer_section:
            name = lawyer_section.select_one(".nom, .name, h3, h4, strong")
            if name:
                lawyer.nom = name.get_text(strip=True)

            phone = lawyer_section.select_one("a[href^='tel:'], .tel, .telephone")
            if phone:
                lawyer.telephone = phone.get_text(strip=True)

            email = lawyer_section.select_one("a[href^='mailto:']")
            if email:
                lawyer.email = email.get("href", "").replace("mailto:", "")

            website = lawyer_section.select_one("a.site, a.website")
            if website:
                lawyer.site_web = website.get("href", "")

        return lawyer if lawyer.nom else None

    def scrape_all_cities(self, max_pages: int = 10) -> List[Auction]:
        """Scrape auctions from Paris region (75, 92, 93, 94)"""
        all_auctions = []
        seen_urls = set()

        # Scan all listings and filter for Paris region departments
        logger.info(f"[EnchèresPubliques] Scanning all listings for departments 75/92/93/94...")

        for page in range(1, max_pages + 1):
            url = f"{self.base_url}/encheres/immobilier?page={page}"
            soup = self.fetch_page(url)

            if not soup:
                break

            auctions = self.parse_auction_list(soup)
            if not auctions:
                break

            # Filter for Paris region departments (75, 92, 93, 94)
            local_auctions = [
                a for a in auctions
                if "-75/" in a.get("url", "") or "-92/" in a.get("url", "")
                or "-93/" in a.get("url", "") or "-94/" in a.get("url", "")
            ]

            for data in local_auctions:
                auction_url = data.get("url", "")
                if auction_url and auction_url not in seen_urls:
                    seen_urls.add(auction_url)
                    auction = self.parse_auction_detail(auction_url)
                    if auction:
                        all_auctions.append(auction)
                        logger.info(f"[EnchèresPubliques] Found: {auction.ville} - {auction.type_bien.value if auction.type_bien else 'bien'}")

            logger.debug(f"[EnchèresPubliques] Page {page}: {len(auctions)} total, {len(local_auctions)} in Paris region")

            # Stop if no more pages
            if len(auctions) < 10:
                break

        logger.info(f"[EnchèresPubliques] Total: {len(all_auctions)} auctions in Paris region")
        return all_auctions
