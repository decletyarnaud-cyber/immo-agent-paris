"""
Scraper for adjudication results from various sources (Eklar, Licitor)
Collects historical auction sale prices for market analysis
"""
import re
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup
import requests
from loguru import logger

from src.storage.database import Database


class AdjudicationResultsScraper:
    """Scrapes adjudication results from auction websites"""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })

    def scrape_eklar(self) -> int:
        """Scrape adjudication results from eklar.com/vente"""
        url = "https://www.eklar.com/vente"
        logger.info(f"Scraping adjudication results from {url}")

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            results_count = 0

            # Find all auction cards with "Adjugé" status
            cards = soup.find_all("div", class_=re.compile(r"card|vente|annonce", re.I))
            if not cards:
                cards = soup.find_all("article")
            if not cards:
                cards = soup.find_all("tr")

            for card in cards:
                text = card.get_text(" ", strip=True)

                # Only process sold items (Adjugé)
                if "Adjugé" not in text:
                    continue

                result = self._parse_eklar_card(card, text)
                if result:
                    saved = self.db.save_adjudication_result(**result)
                    if saved:
                        results_count += 1
                        logger.debug(f"Saved: {result['code_postal']} - {result['prix_adjuge']}€")

            logger.info(f"Scraped {results_count} adjudication results from Eklar")
            return results_count

        except Exception as e:
            logger.error(f"Error scraping Eklar: {e}")
            return 0

    def _parse_eklar_card(self, card: BeautifulSoup, text: str) -> Optional[Dict[str, Any]]:
        """Parse an Eklar auction card"""
        result = {
            "source": "Eklar",
            "source_url": "https://www.eklar.com/vente",
        }

        # Extract postal code (13XXX format)
        cp_match = re.search(r"\b(13\d{3}|83\d{3})\b", text)
        if not cp_match:
            return None
        result["code_postal"] = cp_match.group(1)

        # Extract price (Adjugé XXXXX €)
        price_match = re.search(r"Adjugé\s*[:\s]*(\d[\d\s]*)\s*€", text, re.I)
        if not price_match:
            return None
        result["prix_adjuge"] = float(price_match.group(1).replace(" ", ""))

        # Extract surface if available
        surface_match = re.search(r"(\d+[,.]?\d*)\s*m²", text)
        if surface_match:
            surface = float(surface_match.group(1).replace(",", "."))
            # Filter out very small surfaces (parking spots)
            if surface >= 15:
                result["surface"] = surface

        # Extract city name from postal code
        result["ville"] = self._get_ville_from_postal(result["code_postal"])

        # Determine property type from text
        if any(word in text.lower() for word in ["appartement", "studio", "t1", "t2", "t3", "t4", "t5"]):
            result["type_bien"] = "Appartement"
        elif any(word in text.lower() for word in ["maison", "villa", "pavillon"]):
            result["type_bien"] = "Maison"
        elif any(word in text.lower() for word in ["local", "commerce", "bureau"]):
            result["type_bien"] = "Local"
        elif any(word in text.lower() for word in ["parking", "garage", "box"]):
            result["type_bien"] = "Parking"
        else:
            result["type_bien"] = "Autre"

        # Skip parking/garage for neighborhood price analysis
        if result["type_bien"] == "Parking":
            return None

        result["tribunal"] = "Tribunal Judiciaire de Marseille"

        return result

    def scrape_licitor_past_auctions(self, tribunal_slug: str = "tj-marseille", months_back: int = 6) -> int:
        """Scrape past auction results from Licitor"""
        from datetime import timedelta

        base_url = "https://www.licitor.com/ventes-judiciaires-immobilieres"
        days_fr = {0: "lundi", 1: "mardi", 2: "mercredi", 3: "jeudi", 4: "vendredi", 5: "samedi", 6: "dimanche"}
        months_fr = {
            1: "janvier", 2: "fevrier", 3: "mars", 4: "avril",
            5: "mai", 6: "juin", 7: "juillet", 8: "aout",
            9: "septembre", 10: "octobre", 11: "novembre", 12: "decembre"
        }

        # Determine auction day for tribunal
        auction_day = 2  # Wednesday for Marseille
        if "aix" in tribunal_slug:
            auction_day = 0  # Monday
        elif "toulon" in tribunal_slug:
            auction_day = 3  # Thursday

        tribunal_name = {
            "tj-marseille": "Tribunal Judiciaire de Marseille",
            "tj-aix-en-provence": "Tribunal Judiciaire d'Aix-en-Provence",
            "tj-toulon": "Tribunal Judiciaire de Toulon",
        }.get(tribunal_slug, tribunal_slug)

        results_count = 0
        today = date.today()

        # Check past dates
        for days_ago in range(7, months_back * 30, 7):
            check_date = today - timedelta(days=days_ago)

            # Skip if not the right day of week
            if check_date.weekday() != auction_day:
                continue

            # Build URL
            day_name = days_fr[check_date.weekday()]
            month_name = months_fr[check_date.month]
            url = f"{base_url}/{tribunal_slug}/{day_name}-{check_date.day}-{month_name}-{check_date.year}.html"

            try:
                response = self.session.get(url, timeout=15)
                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, "html.parser")
                page_results = self._parse_licitor_page(soup, check_date, tribunal_name, url)
                results_count += page_results

            except Exception as e:
                logger.debug(f"Error fetching {url}: {e}")
                continue

        logger.info(f"Scraped {results_count} results from Licitor {tribunal_slug}")
        return results_count

    def _parse_licitor_page(self, soup: BeautifulSoup, auction_date: date, tribunal: str, url: str) -> int:
        """Parse a Licitor auction page for adjudication results"""
        results_count = 0

        # Find auction cards
        cards = soup.find_all("div", class_=re.compile(r"annonce|card|bien", re.I))
        if not cards:
            cards = soup.find_all("article")

        for card in cards:
            text = card.get_text(" ", strip=True)

            # Skip if no price result
            if "Adjudication inconnue" in text or "inconnue" in text.lower():
                continue

            # Look for adjugé price
            price_match = re.search(r"(?:Adjugé|adjugé)\s*(?:à)?\s*[:\s]*(\d[\d\s]*)\s*€", text, re.I)
            if not price_match:
                continue

            prix_adjuge = float(price_match.group(1).replace(" ", "").replace("\u202f", ""))

            # Extract postal code / arrondissement
            arr_match = re.search(r"Marseille\s*(\d+)(?:ème|er|e)?", text, re.I)
            if arr_match:
                arr = int(arr_match.group(1))
                code_postal = f"130{arr:02d}" if arr < 10 else f"13{arr:03d}"
            else:
                cp_match = re.search(r"\b(13\d{3}|83\d{3})\b", text)
                if not cp_match:
                    continue
                code_postal = cp_match.group(1)

            # Extract surface
            surface = None
            surface_match = re.search(r"(\d+[,.]?\d*)\s*m²", text)
            if surface_match:
                surface = float(surface_match.group(1).replace(",", "."))

            # Determine type
            type_bien = "Appartement"  # Default for Marseille
            if any(word in text.lower() for word in ["maison", "villa", "pavillon"]):
                type_bien = "Maison"
            elif any(word in text.lower() for word in ["local", "commerce"]):
                type_bien = "Local"

            saved = self.db.save_adjudication_result(
                source="Licitor",
                source_url=url,
                date_adjudication=auction_date,
                code_postal=code_postal,
                ville=self._get_ville_from_postal(code_postal),
                type_bien=type_bien,
                surface=surface,
                prix_adjuge=prix_adjuge,
                tribunal=tribunal,
            )
            if saved:
                results_count += 1

        return results_count

    def _get_ville_from_postal(self, code_postal: str) -> str:
        """Get city name from postal code"""
        postal_to_ville = {
            "13001": "Marseille 1er", "13002": "Marseille 2ème", "13003": "Marseille 3ème",
            "13004": "Marseille 4ème", "13005": "Marseille 5ème", "13006": "Marseille 6ème",
            "13007": "Marseille 7ème", "13008": "Marseille 8ème", "13009": "Marseille 9ème",
            "13010": "Marseille 10ème", "13011": "Marseille 11ème", "13012": "Marseille 12ème",
            "13013": "Marseille 13ème", "13014": "Marseille 14ème", "13015": "Marseille 15ème",
            "13016": "Marseille 16ème",
            "13100": "Aix-en-Provence", "13090": "Aix-en-Provence",
            "13400": "Aubagne", "13500": "Martigues", "13600": "La Ciotat",
            "13127": "Vitrolles", "13300": "Salon-de-Provence",
            "83000": "Toulon", "83100": "Toulon", "83200": "Toulon",
            "83400": "Hyères", "83600": "Fréjus", "83700": "Saint-Raphaël",
        }
        return postal_to_ville.get(code_postal, f"CP {code_postal}")

    def scrape_all_sources(self) -> Dict[str, int]:
        """Scrape all available sources"""
        results = {}

        # Eklar
        results["eklar"] = self.scrape_eklar()

        # Licitor - all tribunals
        for tribunal in ["tj-marseille", "tj-aix-en-provence", "tj-toulon"]:
            results[f"licitor_{tribunal}"] = self.scrape_licitor_past_auctions(tribunal)

        total = sum(results.values())
        logger.info(f"Total adjudication results scraped: {total}")
        return results

    def insert_initial_data(self):
        """Insert known adjudication results from manual research"""
        # Data found from web research
        initial_data = [
            # From Licitor - TJ Marseille 16 Oct 2024
            {"source": "Licitor", "date_adjudication": date(2024, 10, 16),
             "code_postal": "13008", "ville": "Marseille 8ème", "type_bien": "Appartement",
             "surface": 27.48, "prix_adjuge": 45000, "tribunal": "TJ Marseille"},
            {"source": "Licitor", "date_adjudication": date(2024, 10, 16),
             "code_postal": "13011", "ville": "Marseille 11ème", "type_bien": "Appartement",
             "surface": 43.71, "prix_adjuge": 81000, "tribunal": "TJ Marseille"},
            # From Eklar (filtered for apartments only, surface > 15m²)
            {"source": "Eklar", "code_postal": "13006", "ville": "Marseille 6ème",
             "type_bien": "Appartement", "prix_adjuge": 177000, "tribunal": "TJ Marseille"},
            {"source": "Eklar", "code_postal": "13010", "ville": "Marseille 10ème",
             "type_bien": "Appartement", "prix_adjuge": 86000, "tribunal": "TJ Marseille"},
            {"source": "Eklar", "code_postal": "13010", "ville": "Marseille 10ème",
             "type_bien": "Appartement", "prix_adjuge": 153000, "tribunal": "TJ Marseille"},
            {"source": "Eklar", "code_postal": "13003", "ville": "Marseille 3ème",
             "type_bien": "Appartement", "prix_adjuge": 92000, "tribunal": "TJ Marseille"},
            {"source": "Eklar", "code_postal": "13003", "ville": "Marseille 3ème",
             "type_bien": "Appartement", "prix_adjuge": 57000, "tribunal": "TJ Marseille"},
            {"source": "Eklar", "code_postal": "13004", "ville": "Marseille 4ème",
             "type_bien": "Appartement", "prix_adjuge": 94000, "tribunal": "TJ Marseille"},
            {"source": "Eklar", "code_postal": "13008", "ville": "Marseille 8ème",
             "type_bien": "Appartement", "prix_adjuge": 201000, "tribunal": "TJ Marseille"},
            {"source": "Eklar", "code_postal": "13008", "ville": "Marseille 8ème",
             "type_bien": "Appartement", "prix_adjuge": 99000, "tribunal": "TJ Marseille"},
            {"source": "Eklar", "code_postal": "13013", "ville": "Marseille 13ème",
             "type_bien": "Appartement", "prix_adjuge": 226000, "tribunal": "TJ Marseille"},
            {"source": "Eklar", "code_postal": "13013", "ville": "Marseille 13ème",
             "type_bien": "Appartement", "prix_adjuge": 92000, "tribunal": "TJ Marseille"},
            {"source": "Eklar", "code_postal": "13014", "ville": "Marseille 14ème",
             "type_bien": "Appartement", "prix_adjuge": 110000, "tribunal": "TJ Marseille"},
            {"source": "Eklar", "code_postal": "13014", "ville": "Marseille 14ème",
             "type_bien": "Appartement", "prix_adjuge": 138000, "tribunal": "TJ Marseille"},
            {"source": "Eklar", "code_postal": "13015", "ville": "Marseille 15ème",
             "type_bien": "Appartement", "prix_adjuge": 67000, "tribunal": "TJ Marseille"},
        ]

        count = 0
        for data in initial_data:
            result = self.db.save_adjudication_result(**data)
            if result:
                count += 1

        logger.info(f"Inserted {count} initial adjudication results")
        return count


if __name__ == "__main__":
    scraper = AdjudicationResultsScraper()
    # Insert initial data first
    scraper.insert_initial_data()
    # Then try to scrape more
    scraper.scrape_all_sources()
