"""
Scraper pour les sites d'avocats - Récupère les ventes et PV descriptifs
"""
import re
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import urljoin
from loguru import logger

import requests
from bs4 import BeautifulSoup

from src.storage.models import Auction


@dataclass
class LawyerAuction:
    """Vente trouvée sur un site d'avocat"""
    cabinet: str
    avocat: str
    url: str
    adresse: str
    ville: str
    code_postal: str
    date_vente: date
    mise_a_prix: float
    surface: Optional[float] = None
    type_bien: Optional[str] = None
    description: Optional[str] = None
    pv_url: Optional[str] = None
    cahier_charges_url: Optional[str] = None
    documents: List[Dict[str, str]] = None

    def __post_init__(self):
        if self.documents is None:
            self.documents = []


class MascaronScraper:
    """Scraper pour le site Mascaron Avocats"""

    BASE_URL = "https://www.mascaron-avocats.com"
    ENCHERES_URL = "https://www.mascaron-avocats.com/domaines-dintervention/encheres-immobilieres/"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })

    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Récupère une page"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            logger.error(f"[MascaronScraper] Erreur fetch {url}: {e}")
            return None

    def get_auction_urls(self) -> List[str]:
        """Récupère la liste des URLs des ventes"""
        soup = self.fetch_page(self.ENCHERES_URL)
        if not soup:
            return []

        urls = []
        # Chercher les liens vers les pages de détail
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/enchere/" in href or "vente-du-" in href:
                full_url = urljoin(self.BASE_URL, href)
                if full_url not in urls:
                    urls.append(full_url)

        logger.info(f"[MascaronScraper] {len(urls)} ventes trouvées")
        return urls

    def parse_auction_detail(self, url: str) -> Optional[LawyerAuction]:
        """Parse une page de détail de vente"""
        soup = self.fetch_page(url)
        if not soup:
            return None

        try:
            # Extraire le titre
            title = soup.find("h1") or soup.find("title")
            title_text = title.get_text(strip=True) if title else ""

            # Extraire date de vente du titre ou URL
            date_match = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", title_text)
            if not date_match:
                date_match = re.search(r"vente-du-(\d{1,2})-(\d{1,2})-(\d{4})", url)

            date_vente = None
            if date_match:
                day, month, year = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
                date_vente = date(year, month, day)

            # Extraire l'adresse et la ville
            adresse, ville, code_postal = self._extract_location(title_text, soup)

            # Extraire la mise à prix
            mise_a_prix = self._extract_price(soup)

            # Extraire la surface
            surface = self._extract_surface(title_text + " " + soup.get_text())

            # Extraire les documents PDF
            documents = self._extract_documents(soup, url)

            # Trouver le PV descriptif
            pv_url = None
            cahier_url = None
            for doc in documents:
                name_lower = doc["name"].lower()
                if "pv" in name_lower and "descriptif" in name_lower:
                    pv_url = doc["url"]
                elif "cahier" in name_lower and "condition" in name_lower:
                    cahier_url = doc["url"]

            return LawyerAuction(
                cabinet="SELARL Mascaron Avocats",
                avocat="Philippe Cornet",
                url=url,
                adresse=adresse,
                ville=ville,
                code_postal=code_postal,
                date_vente=date_vente,
                mise_a_prix=mise_a_prix,
                surface=surface,
                pv_url=pv_url,
                cahier_charges_url=cahier_url,
                documents=documents
            )

        except Exception as e:
            logger.error(f"[MascaronScraper] Erreur parsing {url}: {e}")
            return None

    def _extract_location(self, title: str, soup: BeautifulSoup) -> Tuple[str, str, str]:
        """Extrait adresse, ville et code postal"""
        text = title + " " + soup.get_text()

        # Pattern pour code postal et ville
        cp_match = re.search(r"(\d{5})\s*([A-ZÀ-Ü][a-zà-ü-]+(?:\s+[A-ZÀ-Ü]?[a-zà-ü-]+)*)", text)
        code_postal = cp_match.group(1) if cp_match else ""
        ville = cp_match.group(2).strip() if cp_match else ""

        # Pattern pour adresse
        addr_patterns = [
            r"(\d+(?:bis|ter)?[\s,]+(?:rue|boulevard|bd|avenue|av|chemin|allée|square|impasse|place)[^,\d]{5,50})",
            r"((?:rue|boulevard|bd|avenue|av|chemin|allée|square|impasse|place)[^,\d]{5,50})",
        ]
        adresse = ""
        for pattern in addr_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                adresse = match.group(1).strip()
                break

        return adresse, ville, code_postal

    def _extract_price(self, soup: BeautifulSoup) -> float:
        """Extrait la mise à prix"""
        text = soup.get_text()
        # Chercher "mise à prix" suivie d'un montant
        patterns = [
            r"mise\s*[àa]\s*prix[:\s]*(\d[\d\s]*(?:[,.]\d+)?)\s*(?:€|euros?)?",
            r"(\d[\d\s]*(?:[,.]\d+)?)\s*(?:€|euros?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(" ", "").replace(",", ".")
                try:
                    return float(price_str)
                except:
                    pass
        return 0

    def _extract_surface(self, text: str) -> Optional[float]:
        """Extrait la surface"""
        patterns = [
            r"(\d+(?:[,.]\d+)?)\s*m[²2]",
            r"superficie[:\s]*(\d+(?:[,.]\d+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1).replace(",", "."))
                except:
                    pass
        return None

    def _extract_documents(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
        """Extrait tous les liens vers des documents PDF"""
        documents = []
        seen_urls = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]
            if ".pdf" in href.lower():
                full_url = urljoin(base_url, href)
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    # Extraire le nom du fichier
                    name = link.get_text(strip=True)
                    if not name:
                        name = href.split("/")[-1].replace(".pdf", "").replace("-", " ").replace("_", " ")
                    documents.append({"name": name, "url": full_url})

        return documents

    def scrape_all(self) -> List[LawyerAuction]:
        """Scrape toutes les ventes"""
        auctions = []
        urls = self.get_auction_urls()

        for url in urls:
            auction = self.parse_auction_detail(url)
            if auction:
                auctions.append(auction)
                logger.info(f"[MascaronScraper] Scraped: {auction.adresse} ({auction.ville})")

        logger.info(f"[MascaronScraper] Total: {len(auctions)} ventes récupérées")
        return auctions


def match_lawyer_auction_to_db(lawyer_auction: LawyerAuction, db_auctions: List[Auction]) -> Optional[Auction]:
    """
    Trouve la correspondance entre une vente avocat et une vente en base

    Critères de match:
    - Même date de vente
    - Même ville ou code postal
    - Prix similaire (±20%)
    """
    for db_auction in db_auctions:
        # Date de vente
        if lawyer_auction.date_vente and db_auction.date_vente:
            if lawyer_auction.date_vente != db_auction.date_vente:
                continue

        # Ville ou code postal
        ville_match = False
        if lawyer_auction.ville and db_auction.ville:
            if lawyer_auction.ville.lower() in db_auction.ville.lower() or \
               db_auction.ville.lower() in lawyer_auction.ville.lower():
                ville_match = True
        if lawyer_auction.code_postal and db_auction.code_postal:
            if lawyer_auction.code_postal == db_auction.code_postal:
                ville_match = True

        if not ville_match:
            continue

        # Prix similaire
        if lawyer_auction.mise_a_prix and db_auction.mise_a_prix:
            price_diff = abs(lawyer_auction.mise_a_prix - db_auction.mise_a_prix)
            avg_price = (lawyer_auction.mise_a_prix + db_auction.mise_a_prix) / 2
            if price_diff / avg_price > 0.2:
                continue

        # Match trouvé !
        return db_auction

    return None


def update_auctions_with_lawyer_data(db) -> Dict[str, int]:
    """
    Met à jour les annonces en base avec les données des sites d'avocats

    Returns:
        Stats: {"matched": n, "pv_added": n, "new": n}
    """
    stats = {"matched": 0, "pv_added": 0, "new": 0}

    # Scraper Mascaron
    scraper = MascaronScraper()
    lawyer_auctions = scraper.scrape_all()

    # Récupérer les annonces en base
    db_auctions = db.get_all_auctions(limit=1000)

    for la in lawyer_auctions:
        match = match_lawyer_auction_to_db(la, db_auctions)

        if match:
            stats["matched"] += 1

            # Mettre à jour le PV si trouvé
            if la.pv_url and not match.pv_url:
                match.pv_url = la.pv_url
                stats["pv_added"] += 1
                logger.info(f"[LawyerScraper] PV ajouté pour #{match.id}: {la.pv_url}")

            # Mettre à jour les documents
            if la.documents:
                if not match.documents:
                    match.documents = []
                for doc in la.documents:
                    if doc not in match.documents:
                        match.documents.append(doc)

            # Sauvegarder
            db.save_auction(match)
        else:
            stats["new"] += 1
            logger.debug(f"[LawyerScraper] Pas de match pour: {la.adresse} ({la.ville})")

    logger.info(f"[LawyerScraper] Résultats: {stats}")
    return stats
