"""
Smart scraper using LLM extraction for robust data extraction
Combines URL discovery from existing scrapers with LLM-based data extraction
"""
import os
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from loguru import logger

from .base_scraper import BaseScraper
from .licitor import LicitorScraper
from .encheres_publiques import EncherePubliquesScraper
from src.storage.models import Auction, PropertyType, AuctionStatus, PVStatus
from src.extractors.llm_extractor import LLMExtractor, ExtractedAuctionData
from src.extractors.photo_downloader import PhotoDownloader


class SmartScraper:
    """
    Intelligent scraper that uses LLM for data extraction

    Strategy:
    1. Use existing scrapers to discover auction URLs
    2. Fetch raw HTML for each auction page
    3. Use Claude to extract structured data
    4. Download and store photos locally
    5. Validate and enrich data

    Benefits:
    - More robust than regex patterns
    - Handles site changes gracefully
    - Better address/location extraction
    - Distinguishes property vs lawyer info
    - Self-documenting with confidence scores
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        use_llm: bool = True,
        download_photos: bool = True
    ):
        """
        Initialize smart scraper

        Args:
            api_key: Anthropic API key (uses env var if not provided)
            use_llm: Whether to use LLM extraction (falls back to regex if False)
            download_photos: Whether to download photos locally
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.use_llm = use_llm and bool(self.api_key)
        self.download_photos = download_photos

        # Initialize components
        self.licitor = LicitorScraper()
        self.encheres_publiques = EncherePubliquesScraper()

        if self.use_llm:
            self.llm_extractor = LLMExtractor(api_key=self.api_key)
            logger.info("[SmartScraper] LLM extraction enabled")
        else:
            self.llm_extractor = None
            logger.warning("[SmartScraper] LLM extraction disabled - using regex fallback")

        if self.download_photos:
            self.photo_downloader = PhotoDownloader()
            logger.info("[SmartScraper] Photo download enabled")
        else:
            self.photo_downloader = None

    def _convert_extracted_to_auction(self, extracted: ExtractedAuctionData, url: str, source: str) -> Auction:
        """Convert LLM extracted data to Auction model"""
        auction = Auction()
        auction.source = source
        auction.url = url

        # Location
        auction.adresse = extracted.adresse
        auction.code_postal = extracted.code_postal
        auction.ville = extracted.ville
        auction.department = extracted.department

        # Property type mapping
        type_map = {
            "appartement": PropertyType.APPARTEMENT,
            "maison": PropertyType.MAISON,
            "local_commercial": PropertyType.LOCAL_COMMERCIAL,
            "terrain": PropertyType.TERRAIN,
            "parking": PropertyType.PARKING,
        }
        auction.type_bien = type_map.get(extracted.type_bien, PropertyType.AUTRE)

        # Property details
        auction.surface = extracted.surface
        auction.nb_pieces = extracted.nb_pieces
        auction.nb_chambres = extracted.nb_chambres
        auction.etage = extracted.etage
        auction.description = extracted.description
        auction.occupation = extracted.occupation

        # Auction details
        auction.mise_a_prix = extracted.mise_a_prix
        auction.tribunal = extracted.tribunal

        # Parse sale date
        if extracted.date_vente:
            try:
                auction.date_vente = date.fromisoformat(extracted.date_vente)
            except:
                pass

        auction.heure_vente = extracted.heure_vente

        # Parse visit dates
        if extracted.dates_visite:
            for dt_str in extracted.dates_visite:
                try:
                    dt = datetime.fromisoformat(dt_str)
                    auction.dates_visite.append(dt)
                except:
                    pass

        # Lawyer info
        auction.avocat_nom = extracted.avocat_nom
        auction.avocat_cabinet = extracted.avocat_cabinet
        auction.avocat_telephone = extracted.avocat_telephone
        auction.avocat_email = extracted.avocat_email
        auction.avocat_adresse = extracted.avocat_adresse

        # Documents
        auction.photos = extracted.photos or []

        if extracted.documents:
            auction.documents = extracted.documents

        if extracted.pv_url:
            auction.pv_url = extracted.pv_url
            auction.pv_status = PVStatus.A_TELECHARGER

        return auction

    def scrape_url(self, url: str, source: str = "unknown") -> Optional[Auction]:
        """
        Scrape a single auction URL

        Args:
            url: Auction page URL
            source: Source identifier (licitor, encheres_publiques, etc.)

        Returns:
            Auction object or None
        """
        logger.info(f"[SmartScraper] Scraping: {url}")

        if self.use_llm and self.llm_extractor:
            # Use LLM extraction
            extracted = self.llm_extractor.extract_from_url(url)

            if extracted:
                auction = self._convert_extracted_to_auction(extracted, url, source)

                # Log confidence
                if extracted.confidence < 0.7:
                    logger.warning(f"[SmartScraper] Low confidence ({extracted.confidence:.0%}): {url}")
                    if extracted.extraction_notes:
                        for note in extracted.extraction_notes:
                            logger.warning(f"  - {note}")

                # Download photos if enabled
                if self.download_photos and self.photo_downloader and extracted.photos:
                    # We'll need auction ID after saving - for now store URLs
                    pass

                return auction
            else:
                logger.warning(f"[SmartScraper] LLM extraction failed, falling back to regex")

        # Fallback to regex-based scraper
        if "licitor" in url or "licitor" in source:
            return self.licitor.parse_auction_detail(url)
        elif "encheres-publiques" in url or "encheres_publiques" in source:
            return self.encheres_publiques.parse_auction_detail(url)
        else:
            # Try both
            auction = self.licitor.parse_auction_detail(url)
            if not auction:
                auction = self.encheres_publiques.parse_auction_detail(url)
            return auction

    def scrape_licitor(self) -> List[Auction]:
        """Scrape all auctions from Licitor using smart extraction"""
        all_auctions = []

        for slug, name in self.licitor.TRIBUNAUX.items():
            logger.info(f"[SmartScraper] Scraping Licitor - {name}...")

            # Get auction URLs
            auction_urls = self.licitor.find_tribunal_auction_urls(slug)

            for date_url in auction_urls:
                soup = self.licitor.fetch_page(date_url)
                if soup:
                    # Find individual auction links
                    for link in soup.select("a[href*='/annonce/']"):
                        href = link.get("href", "")
                        full_url = href if href.startswith("http") else f"{self.licitor.base_url}{href}"

                        auction = self.scrape_url(full_url, "licitor")
                        if auction:
                            auction.tribunal = name
                            all_auctions.append(auction)

        logger.info(f"[SmartScraper] Licitor: {len(all_auctions)} auctions scraped")
        return all_auctions

    def scrape_encheres_publiques(self) -> List[Auction]:
        """Scrape auctions from encheres-publiques.com"""
        all_auctions = []

        # Scrape by department
        for dept in ["13", "83"]:
            logger.info(f"[SmartScraper] Scraping EnchèresPubliques - Department {dept}...")

            page = 1
            while page <= 10:  # Max 10 pages
                url = self.encheres_publiques.get_department_url(dept, page)
                soup = self.encheres_publiques.fetch_page(url)

                if not soup:
                    break

                auction_list = self.encheres_publiques.parse_auction_list(soup)
                if not auction_list:
                    break

                for item in auction_list:
                    auction_url = item.get("url")
                    if auction_url:
                        auction = self.scrape_url(auction_url, "encheres_publiques")
                        if auction:
                            all_auctions.append(auction)

                page += 1

        logger.info(f"[SmartScraper] EnchèresPubliques: {len(all_auctions)} auctions scraped")
        return all_auctions

    def scrape_all(self) -> List[Auction]:
        """Scrape all sources"""
        all_auctions = []

        # Licitor
        all_auctions.extend(self.scrape_licitor())

        # Enchères Publiques
        all_auctions.extend(self.scrape_encheres_publiques())

        logger.info(f"[SmartScraper] Total: {len(all_auctions)} auctions from all sources")
        return all_auctions

    def download_photos_for_auction(self, auction: Auction) -> List[str]:
        """Download photos for a saved auction (needs auction.id)"""
        if not self.photo_downloader or not auction.id:
            return []

        if not auction.photos:
            return []

        base_url = auction.url.rsplit('/', 1)[0] if auction.url else None
        return self.photo_downloader.download_photos(
            auction.photos,
            auction.id,
            base_url
        )


def smart_scrape(api_key: Optional[str] = None) -> List[Auction]:
    """
    Convenience function to run smart scraping

    Args:
        api_key: Anthropic API key (uses env var if not provided)

    Returns:
        List of scraped auctions
    """
    scraper = SmartScraper(api_key=api_key)
    return scraper.scrape_all()
