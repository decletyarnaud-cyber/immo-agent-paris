"""
Online listings price source
Scrapes asking prices from multiple real estate listing sites:
- LeBonCoin
- SeLoger
- PAP.fr
"""
import re
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import quote, urlencode
import requests
from bs4 import BeautifulSoup
from loguru import logger

from .base import PriceSource, PriceEstimate, SourceType

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from config.settings import DATA_DIR


class ListingsPriceSource(PriceSource):
    """
    Price source using online real estate listings

    Scrapes current asking prices from multiple listing sites:
    - LeBonCoin (API)
    - SeLoger (web scraping)
    - PAP.fr (web scraping)

    Uses caching to minimize requests and respect rate limits.

    Note: Asking prices are typically 5-15% higher than transaction prices.
    This source applies a correction factor.
    """

    CACHE_FILE = DATA_DIR / "listings_cache.json"
    CACHE_DURATION_HOURS = 24

    # Correction factor: asking prices are usually higher than actual transaction prices
    ASKING_PRICE_PREMIUM = 0.10  # 10% premium

    def __init__(self):
        self._cache = self._load_cache()
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })

    @property
    def source_type(self) -> SourceType:
        return SourceType.LISTINGS

    @property
    def source_name(self) -> str:
        return "Annonces en ligne"

    def _load_cache(self) -> Dict:
        """Load cached listings data"""
        if self.CACHE_FILE.exists():
            try:
                with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_cache(self):
        """Save cache to file"""
        try:
            self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[Listings] Failed to save cache: {e}")

    def _get_cache_key(self, code_postal: str, type_bien: str, surface: Optional[float]) -> str:
        """Generate cache key"""
        surface_range = f"{int((surface or 60) // 20) * 20}" if surface else "any"
        key = f"{code_postal}_{type_bien}_{surface_range}"
        return hashlib.md5(key.encode()).hexdigest()

    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """Check if cache entry is still valid"""
        if not cache_entry.get('cached_at'):
            return False
        cached_at = datetime.fromisoformat(cache_entry['cached_at'])
        return datetime.now() - cached_at < timedelta(hours=self.CACHE_DURATION_HOURS)

    def get_price_estimate(
        self,
        code_postal: str,
        ville: str,
        type_bien: str,
        surface: Optional[float] = None,
    ) -> Optional[PriceEstimate]:
        """Get price estimate from online listings (multiple sources)"""

        cache_key = self._get_cache_key(code_postal, type_bien, surface)

        # Check cache first
        if cache_key in self._cache and self._is_cache_valid(self._cache[cache_key]):
            cached = self._cache[cache_key]
            if cached.get('prix_m2'):
                return PriceEstimate(
                    source_type=self.source_type,
                    source_name=self.source_name,
                    prix_m2=cached['prix_m2'],
                    nb_data_points=cached.get('nb_listings', 0),
                    date_range_days=1,
                    geographic_match=cached.get('geographic_match', 'commune'),
                    source_url=cached.get('source_url'),
                    notes=cached.get('notes', f"Multi-sources ({cached.get('nb_listings', 0)} annonces) - cache"),
                    comparables=cached.get('comparables', []),
                )

        # Fetch from all sources
        all_listings = []
        sources_used = []

        # 1. LeBonCoin
        lbc_listings = self._fetch_leboncoin_listings(code_postal, ville, type_bien, surface)
        if lbc_listings:
            all_listings.extend(lbc_listings)
            sources_used.append("LeBonCoin")
            logger.info(f"[Listings] LeBonCoin: {len(lbc_listings)} annonces")

        # 2. SeLoger
        seloger_listings = self._fetch_seloger_listings(code_postal, ville, type_bien, surface)
        if seloger_listings:
            all_listings.extend(seloger_listings)
            sources_used.append("SeLoger")
            logger.info(f"[Listings] SeLoger: {len(seloger_listings)} annonces")

        # 3. PAP.fr
        pap_listings = self._fetch_pap_listings(code_postal, ville, type_bien, surface)
        if pap_listings:
            all_listings.extend(pap_listings)
            sources_used.append("PAP")
            logger.info(f"[Listings] PAP: {len(pap_listings)} annonces")

        # 4. Bien'ici
        bienici_listings = self._fetch_bienici_listings(code_postal, ville, type_bien, surface)
        if bienici_listings:
            all_listings.extend(bienici_listings)
            sources_used.append("Bien'ici")
            logger.info(f"[Listings] Bien'ici: {len(bienici_listings)} annonces")

        # 5. Logic-Immo
        logicimmo_listings = self._fetch_logicimmo_listings(code_postal, ville, type_bien, surface)
        if logicimmo_listings:
            all_listings.extend(logicimmo_listings)
            sources_used.append("Logic-Immo")
            logger.info(f"[Listings] Logic-Immo: {len(logicimmo_listings)} annonces")

        # If no listings with surface filter, try broader search
        if not all_listings and surface:
            logger.info(f"[Listings] No results with surface filter, trying broader search...")
            lbc_listings = self._fetch_leboncoin_listings(code_postal, ville, type_bien, None)
            if lbc_listings:
                all_listings.extend(lbc_listings)
                sources_used.append("LeBonCoin")

        if not all_listings:
            logger.warning(f"[Listings] No listings found for {code_postal}")
            return None

        # Calculate median price per m²
        valid_prices = []
        comparables = []

        for listing in all_listings:
            prix = listing.get('prix')
            surf = listing.get('surface')
            if prix and surf and surf > 0:
                prix_m2 = prix / surf
                # Filter outliers
                if 500 <= prix_m2 <= 15000:
                    valid_prices.append(prix_m2)
                    comparables.append({
                        'titre': listing.get('titre', '')[:60],
                        'prix': prix,
                        'surface': surf,
                        'prix_m2': round(prix_m2, 0),
                        'url': listing.get('url', ''),
                        'source': listing.get('source', ''),
                    })

        if len(valid_prices) < 3:
            logger.warning(f"[Listings] Only {len(valid_prices)} valid prices (need 3)")
            return None

        # Calculate median
        valid_prices.sort()
        n = len(valid_prices)
        if n % 2 == 0:
            median = (valid_prices[n // 2 - 1] + valid_prices[n // 2]) / 2
        else:
            median = valid_prices[n // 2]

        # Apply correction for asking price premium
        corrected_price = median * (1 - self.ASKING_PRICE_PREMIUM)

        # Sort comparables by price/m² closest to median
        comparables.sort(key=lambda x: abs(x['prix_m2'] - median))

        sources_str = ", ".join(sources_used)
        notes = f"Prix demandés -10% ({len(valid_prices)} annonces via {sources_str})"

        # Cache result
        self._cache[cache_key] = {
            'prix_m2': round(corrected_price, 0),
            'prix_m2_raw': round(median, 0),
            'nb_listings': len(valid_prices),
            'geographic_match': 'commune',
            'source_url': f"https://www.leboncoin.fr/recherche?category=9&locations={quote(ville)}",
            'sources': sources_used,
            'notes': notes,
            'comparables': comparables[:15],  # Keep more for multi-source
            'cached_at': datetime.now().isoformat(),
        }
        self._save_cache()

        return PriceEstimate(
            source_type=self.source_type,
            source_name=self.source_name,
            prix_m2=round(corrected_price, 0),
            nb_data_points=len(valid_prices),
            date_range_days=1,
            geographic_match='commune',
            source_url=f"https://www.leboncoin.fr/recherche?category=9&locations={quote(ville)}",
            notes=notes,
            comparables=comparables[:15],
        )

    # ==================== LEBONCOIN ====================
    def _fetch_leboncoin_listings(
        self,
        code_postal: str,
        ville: str,
        type_bien: str,
        surface: Optional[float],
    ) -> List[Dict]:
        """Fetch listings from LeBonCoin API"""

        type_mapping = {
            'appartement': '2',
            'maison': '1',
            'terrain': '3',
            'parking': '4',
        }
        real_estate_type = type_mapping.get(type_bien.lower(), '2')

        try:
            api_url = "https://api.leboncoin.fr/finder/search"

            payload = {
                "limit": 35,
                "limit_alu": 3,
                "filters": {
                    "category": {"id": "9"},
                    "location": {
                        "locations": [{"zipcode": code_postal}]
                    },
                    "keywords": {},
                    "ranges": {},
                    "enums": {
                        "real_estate_type": [real_estate_type]
                    }
                }
            }

            if surface:
                payload["filters"]["ranges"]["square"] = {
                    "min": int(surface * 0.7),
                    "max": int(surface * 1.3)
                }

            headers = {
                'Content-Type': 'application/json',
                'api_key': 'ba0c2dad52b3ec',
                'Accept': 'application/json',
            }

            response = self._session.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=10
            )

            if response.status_code != 200:
                logger.warning(f"[Listings] LeBonCoin API returned {response.status_code}")
                return []

            data = response.json()
            ads = data.get('ads', [])

            listings = []
            for ad in ads:
                try:
                    prix = ad.get('price', [None])[0]
                    surface_val = None
                    for attr in ad.get('attributes', []):
                        if attr.get('key') == 'square':
                            surface_val = float(attr.get('value', 0))
                            break

                    if prix and surface_val:
                        listings.append({
                            'titre': ad.get('subject', ''),
                            'prix': prix,
                            'surface': surface_val,
                            'url': f"https://www.leboncoin.fr/ad/ventes_immobilieres/{ad.get('list_id')}",
                            'ville': ad.get('location', {}).get('city', ''),
                            'source': 'LeBonCoin',
                        })
                except:
                    continue

            return listings

        except Exception as e:
            logger.warning(f"[Listings] Failed to fetch LeBonCoin: {e}")
            return []

    # ==================== SELOGER ====================
    def _fetch_seloger_listings(
        self,
        code_postal: str,
        ville: str,
        type_bien: str,
        surface: Optional[float],
    ) -> List[Dict]:
        """Fetch listings from SeLoger using their API"""

        # SeLoger type mapping
        type_mapping = {
            'appartement': '1',
            'maison': '2',
        }
        property_type = type_mapping.get(type_bien.lower(), '1')

        try:
            # Use SeLoger's search API endpoint
            api_url = "https://www.seloger.com/list.htm"

            # Build realistic browser-like request
            import random
            import time

            # Random delay to appear more human
            time.sleep(random.uniform(0.5, 1.5))

            # Realistic headers mimicking a real browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'Cache-Control': 'max-age=0',
                'Connection': 'keep-alive',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"macOS"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
                'Referer': 'https://www.google.com/',
            }

            params = {
                'projects': '2',
                'types': property_type,
                'places': f'[{{cp:{code_postal}}}]',
                'enterprise': '0',
                'qsVersion': '1.0',
            }

            if surface:
                params['surface'] = f'{int(surface * 0.7)}/{int(surface * 1.3)}'

            # Create a fresh session for SeLoger
            session = requests.Session()
            session.headers.update(headers)

            # First, visit the homepage to get cookies
            try:
                session.get('https://www.seloger.com/', timeout=10)
            except:
                pass

            response = session.get(
                api_url,
                params=params,
                timeout=15
            )

            if response.status_code != 200:
                logger.warning(f"[Listings] SeLoger returned {response.status_code}")
                return []

            soup = BeautifulSoup(response.text, 'html.parser')
            listings = []

            # Try to find embedded JSON data (Next.js data)
            scripts = soup.find_all('script', id='__NEXT_DATA__')
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    props = data.get('props', {}).get('pageProps', {})
                    cards = props.get('cards', [])

                    for card in cards:
                        try:
                            prix = card.get('price')
                            surface_val = card.get('livingArea') or card.get('surface')

                            if prix and surface_val:
                                listings.append({
                                    'titre': card.get('title', f"{type_bien} {surface_val}m²"),
                                    'prix': float(prix),
                                    'surface': float(surface_val),
                                    'url': f"https://www.seloger.com{card.get('url', '')}",
                                    'ville': card.get('city', ville),
                                    'source': 'SeLoger',
                                })
                        except:
                            continue
                except:
                    continue

            # Fallback: Try JSON-LD data
            if not listings:
                scripts = soup.find_all('script', type='application/ld+json')
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict) and data.get('@type') == 'ItemList':
                            for item in data.get('itemListElement', []):
                                listing = item.get('item', {})
                                if listing.get('@type') == 'Residence':
                                    prix = None
                                    offers = listing.get('offers', {})
                                    if offers:
                                        prix = offers.get('price')
                                    surface_val = listing.get('floorSize', {}).get('value')
                                    if prix and surface_val:
                                        listings.append({
                                            'titre': listing.get('name', ''),
                                            'prix': float(prix),
                                            'surface': float(surface_val),
                                            'url': listing.get('url', ''),
                                            'ville': ville,
                                            'source': 'SeLoger',
                                        })
                    except:
                        continue

            # Fallback: Parse HTML with various selectors
            if not listings:
                # Try multiple card selectors
                card_selectors = [
                    '[data-testid="sl.explore.card-container"]',
                    '.CardContainer__CardContainerWrapper-sc-1tt2vbg-0',
                    '[class*="Card_card"]',
                    'article[class*="card"]',
                    '.listing-item',
                ]

                cards = []
                for selector in card_selectors:
                    cards = soup.select(selector)
                    if cards:
                        break

                for card in cards[:20]:
                    try:
                        # Get all text content
                        text = card.get_text(' ', strip=True)

                        # Extract price
                        price_match = re.search(r'([\d\s]+)\s*€', text.replace('\xa0', ' '))
                        if not price_match:
                            continue
                        prix = float(price_match.group(1).replace(' ', ''))

                        # Extract surface
                        surf_match = re.search(r'(\d+(?:[.,]\d+)?)\s*m²', text)
                        if not surf_match:
                            continue
                        surface_val = float(surf_match.group(1).replace(',', '.'))

                        # Get URL
                        link = card.select_one('a[href*="/annonces/"]') or card.select_one('a[href]')
                        url = ''
                        if link and link.get('href'):
                            href = link.get('href')
                            url = href if href.startswith('http') else f"https://www.seloger.com{href}"

                        listings.append({
                            'titre': f"{type_bien.capitalize()} {surface_val}m²",
                            'prix': prix,
                            'surface': surface_val,
                            'url': url,
                            'ville': ville,
                            'source': 'SeLoger',
                        })
                    except:
                        continue

            return listings

        except Exception as e:
            logger.warning(f"[Listings] Failed to fetch SeLoger: {e}")
            return []

    # ==================== PAP.FR ====================
    def _fetch_pap_listings(
        self,
        code_postal: str,
        ville: str,
        type_bien: str,
        surface: Optional[float],
    ) -> List[Dict]:
        """Fetch listings from PAP.fr (Particulier à Particulier)"""
        import random
        import time

        # PAP type mapping
        type_mapping = {
            'appartement': 'appartement',
            'maison': 'maison',
        }
        property_type = type_mapping.get(type_bien.lower(), 'appartement')

        try:
            # Random delay
            time.sleep(random.uniform(0.5, 1.5))

            # Create fresh session with browser-like headers
            session = requests.Session()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'Cache-Control': 'max-age=0',
                'Connection': 'keep-alive',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"macOS"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
                'Referer': 'https://www.google.fr/search?q=pap+immobilier',
            }
            session.headers.update(headers)

            # Visit homepage first to get cookies
            try:
                session.get('https://www.pap.fr/', timeout=10)
                time.sleep(random.uniform(0.3, 0.8))
            except:
                pass

            # PAP search URL format
            ville_slug = ville.lower().replace(' ', '-').replace("'", '-').replace('è', 'e').replace('é', 'e')
            dept = code_postal[:2]

            # Build URL - PAP format: vente-appartements-marseille-13
            base_url = f"https://www.pap.fr/annonce/vente-{property_type}s-{ville_slug}-{dept}"

            # Add surface filter if specified
            if surface:
                min_surf = int(surface * 0.7)
                max_surf = int(surface * 1.3)
                base_url += f"-a-partir-de-{min_surf}-m2-jusqu-a-{max_surf}-m2"

            response = session.get(base_url, timeout=15)

            if response.status_code != 200:
                # Try simpler URL without surface
                base_url = f"https://www.pap.fr/annonce/vente-{property_type}s-{ville_slug}-{dept}"
                response = session.get(base_url, timeout=15)

                if response.status_code != 200:
                    # Try with just department
                    base_url = f"https://www.pap.fr/annonce/vente-{property_type}s-{dept}"
                    response = session.get(base_url, timeout=15)

                    if response.status_code != 200:
                        logger.warning(f"[Listings] PAP returned {response.status_code}")
                        return []

            soup = BeautifulSoup(response.text, 'html.parser')
            listings = []

            # Try to find JSON-LD structured data first
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    if script.string:
                        data = json.loads(script.string)
                        if isinstance(data, dict) and data.get('@type') == 'ItemList':
                            for item in data.get('itemListElement', []):
                                listing = item.get('item', {})
                                prix = listing.get('offers', {}).get('price')
                                # Try to extract surface from name/description
                                name = listing.get('name', '')
                                desc = listing.get('description', '')
                                surf_match = re.search(r'(\d+(?:[.,]\d+)?)\s*m²', name + ' ' + desc)
                                surface_val = float(surf_match.group(1).replace(',', '.')) if surf_match else None

                                if prix and surface_val:
                                    listings.append({
                                        'titre': name[:60] if name else f"{type_bien} {surface_val}m²",
                                        'prix': float(prix),
                                        'surface': surface_val,
                                        'url': listing.get('url', ''),
                                        'ville': ville,
                                        'source': 'PAP',
                                    })
                except:
                    continue

            # Parse HTML cards with multiple selectors
            if not listings:
                card_selectors = [
                    '.search-list-item',
                    '[class*="search-results"] article',
                    '.item-listing',
                    'article[class*="item"]',
                    '[data-testid*="listing"]',
                    '.annonce',
                ]

                cards = []
                for selector in card_selectors:
                    cards = soup.select(selector)
                    if cards:
                        break

                # If still no cards, try finding any element with price pattern
                if not cards:
                    # Look for divs containing price patterns
                    all_divs = soup.find_all(['div', 'article', 'li'], class_=True)
                    for div in all_divs:
                        text = div.get_text()
                        if re.search(r'\d{2,3}\s*\d{3}\s*€', text) and 'm²' in text:
                            cards.append(div)
                        if len(cards) >= 20:
                            break

                for card in cards[:20]:
                    try:
                        text = card.get_text(' ', strip=True)

                        # Price - PAP format: "XXX XXX €"
                        price_match = re.search(r'([\d\s]{5,})\s*€', text.replace('\xa0', ' '))
                        if not price_match:
                            continue
                        prix = float(price_match.group(1).replace(' ', ''))
                        if prix < 10000:  # Too low, probably not a property price
                            continue

                        # Surface - "XX m²"
                        surf_match = re.search(r'(\d+(?:[.,]\d+)?)\s*m²', text)
                        if not surf_match:
                            continue
                        surface_val = float(surf_match.group(1).replace(',', '.'))

                        # URL
                        link = card.select_one('a[href*="/annonces/"]')
                        if not link:
                            link = card.select_one('a[href]')

                        url = ''
                        if link and link.get('href'):
                            href = link.get('href')
                            if href.startswith('/'):
                                url = f"https://www.pap.fr{href}"
                            else:
                                url = href

                        # Title
                        title_elem = card.select_one('.item-title, h2, h3')
                        titre = title_elem.get_text().strip() if title_elem else f"{type_bien.capitalize()} {surface_val}m²"

                        listings.append({
                            'titre': titre,
                            'prix': prix,
                            'surface': surface_val,
                            'url': url,
                            'ville': ville,
                            'source': 'PAP',
                        })

                    except Exception as e:
                        continue

            return listings

        except Exception as e:
            logger.warning(f"[Listings] Failed to fetch PAP: {e}")
            return []

    # ==================== BIEN'ICI ====================
    def _fetch_bienici_listings(
        self,
        code_postal: str,
        ville: str,
        type_bien: str,
        surface: Optional[float],
    ) -> List[Dict]:
        """Fetch listings from Bien'ici (API-based)"""

        type_mapping = {
            'appartement': 'flat',
            'maison': 'house',
        }
        property_type = type_mapping.get(type_bien.lower(), 'flat')

        try:
            # Bien'ici uses a GraphQL-like API
            api_url = "https://www.bienici.com/realEstateAds.json"

            # Build filters
            filters = {
                "size": 24,
                "from": 0,
                "filterType": "buy",
                "propertyType": [property_type],
                "postalCodes": [code_postal],
                "sortBy": "relevance",
                "sortOrder": "desc",
            }

            if surface:
                filters["minArea"] = int(surface * 0.7)
                filters["maxArea"] = int(surface * 1.3)

            response = self._session.get(
                api_url,
                params={"filters": json.dumps(filters)},
                timeout=15,
                headers={
                    'Accept': 'application/json',
                    'Referer': 'https://www.bienici.com/',
                }
            )

            if response.status_code != 200:
                logger.warning(f"[Listings] Bien'ici returned {response.status_code}")
                return []

            data = response.json()
            ads = data.get('realEstateAds', [])

            listings = []
            for ad in ads[:20]:
                try:
                    prix = ad.get('price')
                    surface_val = ad.get('surfaceArea')

                    if prix and surface_val:
                        ad_id = ad.get('id', '')
                        listings.append({
                            'titre': ad.get('title', f"{type_bien.capitalize()} {surface_val}m²"),
                            'prix': float(prix),
                            'surface': float(surface_val),
                            'url': f"https://www.bienici.com/annonce/{ad_id}" if ad_id else '',
                            'ville': ad.get('city', ville),
                            'source': "Bien'ici",
                        })
                except:
                    continue

            return listings

        except Exception as e:
            logger.warning(f"[Listings] Failed to fetch Bien'ici: {e}")
            return []

    # ==================== LOGIC-IMMO ====================
    def _fetch_logicimmo_listings(
        self,
        code_postal: str,
        ville: str,
        type_bien: str,
        surface: Optional[float],
    ) -> List[Dict]:
        """Fetch listings from Logic-Immo"""

        type_mapping = {
            'appartement': 'appartement',
            'maison': 'maison',
        }
        property_type = type_mapping.get(type_bien.lower(), 'appartement')

        try:
            # Logic-Immo search URL
            ville_slug = ville.lower().replace(' ', '-').replace("'", "-")
            dept = code_postal[:2]

            search_url = f"https://www.logic-immo.com/vente-immobilier-{ville_slug}-{dept},all_{property_type}/options/groupprptypesalialialialialialialialia"

            response = self._session.get(search_url, timeout=15)

            if response.status_code != 200:
                logger.warning(f"[Listings] Logic-Immo returned {response.status_code}")
                return []

            soup = BeautifulSoup(response.text, 'html.parser')
            listings = []

            # Try to find JSON-LD data first
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        for item in data:
                            if item.get('@type') in ['Product', 'Residence', 'Apartment', 'House']:
                                prix = None
                                offers = item.get('offers', {})
                                if isinstance(offers, dict):
                                    prix = offers.get('price')
                                elif isinstance(offers, list) and offers:
                                    prix = offers[0].get('price')

                                # Try to get surface from description
                                desc = item.get('description', '')
                                surf_match = re.search(r'(\d+(?:[.,]\d+)?)\s*m²', desc)
                                surface_val = float(surf_match.group(1).replace(',', '.')) if surf_match else None

                                if prix and surface_val:
                                    listings.append({
                                        'titre': item.get('name', f"{type_bien} {surface_val}m²"),
                                        'prix': float(prix),
                                        'surface': surface_val,
                                        'url': item.get('url', ''),
                                        'ville': ville,
                                        'source': 'Logic-Immo',
                                    })
                except:
                    continue

            # Fallback: parse HTML cards
            if not listings:
                cards = soup.select('.offer-block, .announcement-card, [class*="offer"]')
                for card in cards[:15]:
                    try:
                        # Price
                        price_elem = card.select_one('.offer-price, .price, [class*="price"]')
                        if price_elem:
                            price_text = price_elem.get_text()
                            price_match = re.search(r'([\d\s]+)\s*€', price_text.replace('\xa0', ' '))
                            if price_match:
                                prix = float(price_match.group(1).replace(' ', ''))
                            else:
                                continue
                        else:
                            continue

                        # Surface
                        text = card.get_text()
                        surf_match = re.search(r'(\d+(?:[.,]\d+)?)\s*m²', text)
                        if surf_match:
                            surface_val = float(surf_match.group(1).replace(',', '.'))
                        else:
                            continue

                        # URL
                        link = card.select_one('a[href*="/detail"]')
                        if not link:
                            link = card.select_one('a[href]')
                        url = ''
                        if link and link.get('href'):
                            href = link.get('href')
                            url = href if href.startswith('http') else f"https://www.logic-immo.com{href}"

                        listings.append({
                            'titre': f"{type_bien.capitalize()} {surface_val}m²",
                            'prix': prix,
                            'surface': surface_val,
                            'url': url,
                            'ville': ville,
                            'source': 'Logic-Immo',
                        })
                    except:
                        continue

            return listings

        except Exception as e:
            logger.warning(f"[Listings] Failed to fetch Logic-Immo: {e}")
            return []

    def clear_cache(self):
        """Clear the listings cache"""
        self._cache = {}
        if self.CACHE_FILE.exists():
            self.CACHE_FILE.unlink()
