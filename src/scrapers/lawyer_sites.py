"""
Scraper for lawyer/cabinet websites to download PV and cahier des charges
"""
import re
from typing import Optional, List, Dict, Any
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from loguru import logger

from .base_scraper import BaseScraper
from src.storage.models import Lawyer, PVStatus

# Configuration for known lawyer websites
KNOWN_LAWYERS = {
    "jurisbelair": {
        "base_url": "https://www.jurisbelair.com",
        "auctions_path": "/encheres-publiques-marseille/",
        "pattern": "jurisbelair"
    },
    "cabinet_naudin": {
        "base_url": "https://www.cabinetnaudin.com",
        "auctions_path": "/ventes-aux-encheres-immobilieres",
        "pattern": "naudin"
    },
    "zemmam_avocat": {
        "base_url": "https://www.zemmam-avocat.com",
        "auctions_path": "/adjudications-encheres-transactions-immobilieres/encheres-immobilieres-a-marseille/",
        "pattern": "zemmam"
    },
}


class LawyerSiteScraper(BaseScraper):
    """Scraper for lawyer websites to find PV and documents"""

    def __init__(self):
        super().__init__(
            name="LawyerSites",
            base_url=""  # Dynamic based on lawyer
        )
        self.known_lawyers = KNOWN_LAWYERS

    def get_auction_list_url(self, page: int = 1) -> str:
        """Not used - lawyer sites are scraped individually"""
        return ""

    def parse_auction_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse auction list from lawyer site"""
        auctions = []

        # Look for auction listings
        cards = soup.select(".vente, .enchere, .annonce, article, .listing-item")

        if not cards:
            # Try generic links to PDFs
            links = soup.find_all("a", href=True)
            for link in links:
                href = link.get("href", "").lower()
                if ".pdf" in href or "cahier" in href or "vente" in href:
                    auctions.append({
                        "url": href,
                        "title": link.get_text(strip=True)
                    })

        for card in cards:
            link = card.find("a", href=True)
            if link:
                auctions.append({
                    "url": link.get("href"),
                    "title": link.get_text(strip=True)
                })

        return auctions

    def parse_auction_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """Not the primary use - we're looking for PDFs"""
        return None

    def extract_lawyer_info(self, soup: BeautifulSoup) -> Optional[Lawyer]:
        """Extract lawyer info from their website"""
        lawyer = Lawyer()

        # Look for contact info
        contact = soup.select_one(".contact, #contact, footer, .coordonnees")
        text = contact.get_text() if contact else soup.get_text()

        # Name
        name_match = re.search(r"(?:Maître|Me|Cabinet)\s+([A-ZÀ-Ü][a-zà-ü]+(?:\s+[A-ZÀ-Ü][a-zà-ü]+)*)", text)
        if name_match:
            lawyer.nom = name_match.group(1)

        # Phone
        phone_match = re.search(r"(?:Tél|Tel|Téléphone)\s*:?\s*((?:\+33|0)[\d\s.]+)", text)
        if phone_match:
            lawyer.telephone = phone_match.group(1).strip()

        # Email
        email_match = re.search(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", text)
        if email_match:
            lawyer.email = email_match.group(1)

        return lawyer if lawyer.nom else None

    def find_pdf_links(self, url: str) -> List[Dict[str, str]]:
        """Find all PDF links on a lawyer's page"""
        soup = self.fetch_page(url)
        if not soup:
            return []

        pdfs = []
        base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True).lower()

            # Check if it's a PDF link
            if ".pdf" in href.lower():
                full_url = urljoin(base_url, href)
                pdfs.append({
                    "url": full_url,
                    "title": link.get_text(strip=True),
                    "type": self._classify_document(text, href)
                })

            # Check for links that might lead to PDFs
            elif any(kw in text for kw in ["cahier", "charges", "télécharger", "document", "pv"]):
                pdfs.append({
                    "url": urljoin(base_url, href),
                    "title": link.get_text(strip=True),
                    "type": "potential_pdf"
                })

        return pdfs

    def _classify_document(self, text: str, href: str) -> str:
        """Classify document type"""
        text = text.lower()
        href = href.lower()

        if "cahier" in text or "cahier" in href or "charges" in text:
            return "cahier_charges"
        elif "pv" in text or "proces" in text or "verbal" in text:
            return "proces_verbal"
        elif "photo" in text or "image" in href:
            return "photos"
        else:
            return "document"

    def scrape_lawyer_site(self, lawyer: Lawyer) -> List[Dict[str, str]]:
        """Scrape a specific lawyer's website for auction documents"""
        if not lawyer.site_web:
            return []

        all_pdfs = []
        visited = set()

        # Start from the main site
        base_url = lawyer.site_web
        pages_to_visit = [base_url]

        # Add known auction paths
        for config in self.known_lawyers.values():
            if config["pattern"] in base_url.lower():
                pages_to_visit.append(urljoin(base_url, config["auctions_path"]))

        # Also try common paths
        common_paths = [
            "/encheres", "/ventes", "/adjudications",
            "/encheres-immobilieres", "/ventes-aux-encheres"
        ]
        for path in common_paths:
            pages_to_visit.append(urljoin(base_url, path))

        for page_url in pages_to_visit[:5]:  # Limit to 5 pages
            if page_url in visited:
                continue
            visited.add(page_url)

            logger.debug(f"[LawyerSites] Checking {page_url}")
            pdfs = self.find_pdf_links(page_url)
            all_pdfs.extend(pdfs)

        # Remove duplicates
        seen_urls = set()
        unique_pdfs = []
        for pdf in all_pdfs:
            if pdf["url"] not in seen_urls:
                seen_urls.add(pdf["url"])
                unique_pdfs.append(pdf)

        logger.info(f"[LawyerSites] Found {len(unique_pdfs)} documents on {lawyer.site_web}")
        return unique_pdfs

    def download_document(self, url: str, save_dir: Path, filename: Optional[str] = None) -> Optional[str]:
        """Download a document and save it"""
        if not filename:
            # Generate filename from URL
            parsed = urlparse(url)
            filename = Path(parsed.path).name
            if not filename:
                filename = f"document_{hash(url)}.pdf"

        save_path = save_dir / filename
        save_dir.mkdir(parents=True, exist_ok=True)

        if self.download_pdf(url, str(save_path)):
            return str(save_path)
        return None

    def match_document_to_auction(
        self,
        documents: List[Dict[str, str]],
        auction_address: str,
        auction_date: str = ""
    ) -> Optional[Dict[str, str]]:
        """Try to match a document to a specific auction"""
        address_parts = auction_address.lower().split()

        for doc in documents:
            doc_title = doc.get("title", "").lower()
            doc_url = doc.get("url", "").lower()

            # Check if address parts appear in document title/url
            matches = sum(1 for part in address_parts if part in doc_title or part in doc_url)

            if matches >= 2:  # At least 2 parts of address match
                return doc

            # Check for date match
            if auction_date and auction_date.replace("/", "-") in doc_url:
                return doc

        return None


class EmailTemplateGenerator:
    """Generate email templates for requesting PV documents"""

    TEMPLATE_FR = """
Objet : Demande de procès-verbal - Vente judiciaire du {date_vente}

Maître,

Je me permets de vous contacter concernant la vente aux enchères judiciaires prévue le {date_vente} au {tribunal}, pour le bien situé :

{adresse}

Mise à prix : {mise_a_prix} €

Pourriez-vous, s'il vous plaît, me transmettre :
- Le cahier des charges
- Le procès-verbal de description
- Toute documentation utile relative à ce bien

Je vous remercie par avance pour votre retour.

Cordialement,
{signature}
"""

    def generate_request_email(
        self,
        lawyer: Lawyer,
        adresse: str,
        date_vente: str,
        tribunal: str,
        mise_a_prix: float,
        signature: str = "[Votre nom]"
    ) -> Dict[str, str]:
        """Generate email content for PV request"""
        body = self.TEMPLATE_FR.format(
            date_vente=date_vente,
            tribunal=tribunal,
            adresse=adresse,
            mise_a_prix=f"{mise_a_prix:,.0f}".replace(",", " "),
            signature=signature
        )

        return {
            "to": lawyer.email,
            "subject": f"Demande de procès-verbal - Vente du {date_vente}",
            "body": body,
            "lawyer_name": lawyer.nom,
            "lawyer_phone": lawyer.telephone
        }

    def generate_mailto_link(
        self,
        lawyer: Lawyer,
        adresse: str,
        date_vente: str,
        tribunal: str,
        mise_a_prix: float
    ) -> str:
        """Generate mailto: link for easy email sending"""
        import urllib.parse

        email_data = self.generate_request_email(
            lawyer, adresse, date_vente, tribunal, mise_a_prix
        )

        subject = urllib.parse.quote(email_data["subject"])
        body = urllib.parse.quote(email_data["body"])

        return f"mailto:{lawyer.email}?subject={subject}&body={body}"
