"""
Base scraper class for auction websites
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import time
import requests
from bs4 import BeautifulSoup
from loguru import logger
import sys

# Configure logger
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO"
)

sys.path.insert(0, str(__file__).rsplit("/", 3)[0])
from config.settings import SCRAPING, ALL_POSTAL_CODES
from src.storage.models import Auction, Lawyer


class BaseScraper(ABC):
    """Abstract base class for all auction scrapers"""

    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": SCRAPING["user_agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        })
        self.delay = SCRAPING["delay_between_requests"]
        self.timeout = SCRAPING["timeout"]
        self.max_retries = SCRAPING["max_retries"]
        self._last_request_time = 0

    def _wait_between_requests(self):
        """Ensure minimum delay between requests"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()

    def fetch_page(self, url: str, params: Optional[Dict] = None) -> Optional[BeautifulSoup]:
        """Fetch a page and return BeautifulSoup object"""
        self._wait_between_requests()

        for attempt in range(self.max_retries):
            try:
                logger.debug(f"[{self.name}] Fetching: {url}")
                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                return BeautifulSoup(response.content, "lxml")
            except requests.RequestException as e:
                logger.warning(f"[{self.name}] Attempt {attempt + 1}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff

        logger.error(f"[{self.name}] Failed to fetch {url} after {self.max_retries} attempts")
        return None

    def is_in_target_area(self, code_postal: str) -> bool:
        """Check if postal code is in target area"""
        return code_postal in ALL_POSTAL_CODES

    @abstractmethod
    def get_auction_list_url(self, page: int = 1) -> str:
        """Build URL for auction listing page"""
        pass

    @abstractmethod
    def parse_auction_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse auction listing page and return list of auction data"""
        pass

    @abstractmethod
    def parse_auction_detail(self, url: str) -> Optional[Auction]:
        """Parse individual auction page and return Auction object"""
        pass

    @abstractmethod
    def extract_lawyer_info(self, soup: BeautifulSoup) -> Optional[Lawyer]:
        """Extract lawyer information from auction page"""
        pass

    def scrape_all(self, max_pages: int = 10) -> List[Auction]:
        """Scrape all auctions from source"""
        all_auctions = []
        page = 1

        while page <= max_pages:
            url = self.get_auction_list_url(page)
            soup = self.fetch_page(url)

            if not soup:
                break

            auction_data = self.parse_auction_list(soup)

            if not auction_data:
                logger.info(f"[{self.name}] No more auctions found at page {page}")
                break

            for data in auction_data:
                # Check if in target area
                if "code_postal" in data and not self.is_in_target_area(data["code_postal"]):
                    continue

                # Get detailed info
                if "url" in data:
                    auction = self.parse_auction_detail(data["url"])
                    if auction:
                        all_auctions.append(auction)

            logger.info(f"[{self.name}] Page {page}: found {len(auction_data)} auctions")
            page += 1

        logger.info(f"[{self.name}] Total auctions scraped: {len(all_auctions)}")
        return all_auctions

    def download_pdf(self, url: str, save_path: str) -> bool:
        """Download PDF file from URL"""
        self._wait_between_requests()

        try:
            response = self.session.get(url, timeout=self.timeout, stream=True)
            response.raise_for_status()

            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"[{self.name}] Downloaded PDF to {save_path}")
            return True
        except Exception as e:
            logger.error(f"[{self.name}] Failed to download PDF from {url}: {e}")
            return False
