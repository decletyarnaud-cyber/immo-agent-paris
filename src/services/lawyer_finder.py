"""
Lawyer website finder service - Uses web search to find lawyer websites
"""
import re
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from loguru import logger

import requests
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import DATA_DIR


class LawyerWebsiteFinder:
    """
    Finds lawyer websites using Google search
    Results are cached to avoid repeated searches
    """

    CACHE_FILE = DATA_DIR / "lawyer_websites_cache.json"
    CACHE_DURATION_DAYS = 30

    # Known lawyer directories to prioritize
    LAWYER_DOMAINS = [
        "avocats.fr",
        "avocat.fr",
        "cnb.avocat.fr",
        "annuaire-avocat.fr",
        "conseil-national.avocat.fr",
    ]

    def __init__(self):
        self.cache = self._load_cache()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })

    def _load_cache(self) -> Dict[str, Any]:
        """Load cached lawyer websites"""
        if self.CACHE_FILE.exists():
            try:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
        return {}

    def _save_cache(self):
        """Save cache to file"""
        try:
            self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _get_cache_key(self, lawyer_name: str, city: str = "") -> str:
        """Generate cache key from lawyer name and city"""
        normalized = f"{lawyer_name.lower().strip()}_{city.lower().strip()}"
        return hashlib.md5(normalized.encode()).hexdigest()

    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """Check if cache entry is still valid"""
        if not cache_entry.get("cached_at"):
            return False
        cached_at = datetime.fromisoformat(cache_entry["cached_at"])
        return datetime.now() - cached_at < timedelta(days=self.CACHE_DURATION_DAYS)

    def find_website(self, lawyer_name: str, city: str = "", tribunal: str = "") -> Optional[str]:
        """
        Find a lawyer's website using web search

        Args:
            lawyer_name: Name of the lawyer (e.g., "Me Dupont" or "Cabinet XYZ")
            city: City for better search results
            tribunal: Tribunal name for context

        Returns:
            URL of the lawyer's website or None if not found
        """
        if not lawyer_name:
            return None

        # Check cache first
        cache_key = self._get_cache_key(lawyer_name, city)
        if cache_key in self.cache and self._is_cache_valid(self.cache[cache_key]):
            return self.cache[cache_key].get("website")

        # Build search query
        query_parts = [lawyer_name, "avocat"]
        if city:
            query_parts.append(city)
        elif tribunal:
            # Extract city from tribunal name
            city_match = re.search(r"(?:de|d')\s*([A-ZÀ-Ü][a-zà-ü-]+(?:\s+[A-ZÀ-Ü][a-zà-ü-]+)*)", tribunal)
            if city_match:
                query_parts.append(city_match.group(1))

        query_parts.append("site officiel")
        query = " ".join(query_parts)

        logger.info(f"[LawyerFinder] Searching for: {query}")

        # Use DuckDuckGo HTML search (no API key needed)
        website = self._search_duckduckgo(query, lawyer_name)

        # Cache result
        self.cache[cache_key] = {
            "lawyer_name": lawyer_name,
            "city": city,
            "website": website,
            "cached_at": datetime.now().isoformat()
        }
        self._save_cache()

        return website

    def _search_duckduckgo(self, query: str, lawyer_name: str) -> Optional[str]:
        """Search DuckDuckGo and extract relevant website"""
        try:
            url = "https://html.duckduckgo.com/html/"
            response = self.session.post(url, data={"q": query}, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Find result links
            results = soup.select(".result__a, .result__url")

            for result in results[:10]:
                href = result.get("href", "")
                text = result.get_text().lower()

                # Skip ads and irrelevant results
                if "ad_domain" in href or not href:
                    continue

                # Extract actual URL from DuckDuckGo redirect
                url_match = re.search(r"uddg=([^&]+)", href)
                if url_match:
                    from urllib.parse import unquote
                    href = unquote(url_match.group(1))

                # Check if it's a lawyer-related site
                if self._is_lawyer_website(href, lawyer_name):
                    return href

            return None

        except Exception as e:
            logger.warning(f"[LawyerFinder] Search failed: {e}")
            return None

    def _is_lawyer_website(self, url: str, lawyer_name: str) -> bool:
        """Check if URL is likely a lawyer's website"""
        url_lower = url.lower()

        # Skip social media and generic sites
        skip_domains = ["facebook", "linkedin", "twitter", "instagram", "youtube", "wikipedia"]
        if any(d in url_lower for d in skip_domains):
            return False

        # Prioritize known lawyer directories
        if any(d in url_lower for d in self.LAWYER_DOMAINS):
            return True

        # Check for lawyer-related keywords in URL
        lawyer_keywords = ["avocat", "lawyer", "cabinet", "scp", "selarl", "barreau"]
        if any(kw in url_lower for kw in lawyer_keywords):
            return True

        # Check if lawyer name appears in URL (normalized)
        name_parts = re.findall(r"[a-zà-ü]+", lawyer_name.lower())
        if any(part in url_lower for part in name_parts if len(part) > 3):
            return True

        return False

    def enrich_auctions(self, auctions: list) -> list:
        """
        Enrich a list of auctions with lawyer website URLs

        Args:
            auctions: List of Auction objects

        Returns:
            Same list with avocat_site_web populated where possible
        """
        for auction in auctions:
            if auction.avocat_nom and not auction.avocat_site_web:
                website = self.find_website(
                    lawyer_name=auction.avocat_nom,
                    city=auction.ville or "",
                    tribunal=auction.tribunal or ""
                )
                if website:
                    auction.avocat_site_web = website
                    logger.info(f"[LawyerFinder] Found website for {auction.avocat_nom}: {website}")

        return auctions


# Singleton instance
_finder = None


def get_lawyer_finder() -> LawyerWebsiteFinder:
    """Get singleton instance of LawyerWebsiteFinder"""
    global _finder
    if _finder is None:
        _finder = LawyerWebsiteFinder()
    return _finder
