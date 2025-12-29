"""
LLM-based data extraction for auction pages
Uses Claude to intelligently extract structured data from HTML
"""
import os
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, date
from dataclasses import dataclass, asdict
from loguru import logger

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    logger.warning("[LLMExtractor] anthropic package not installed. Run: pip install anthropic")


@dataclass
class ExtractedAuctionData:
    """Structured auction data extracted by LLM"""
    # Location
    adresse: Optional[str] = None
    code_postal: Optional[str] = None
    ville: Optional[str] = None
    department: Optional[str] = None

    # Property details
    type_bien: Optional[str] = None  # appartement, maison, local_commercial, terrain, parking
    surface: Optional[float] = None
    nb_pieces: Optional[int] = None
    nb_chambres: Optional[int] = None
    etage: Optional[int] = None
    description: Optional[str] = None
    occupation: Optional[str] = None  # libre, occupé, inconnu

    # Auction details
    mise_a_prix: Optional[float] = None
    date_vente: Optional[str] = None  # ISO format YYYY-MM-DD
    heure_vente: Optional[str] = None
    dates_visite: List[str] = None  # ISO format with time
    tribunal: Optional[str] = None

    # Lawyer info
    avocat_nom: Optional[str] = None
    avocat_cabinet: Optional[str] = None
    avocat_telephone: Optional[str] = None
    avocat_email: Optional[str] = None
    avocat_adresse: Optional[str] = None

    # Documents and photos
    photos: List[str] = None  # URLs
    documents: List[Dict[str, str]] = None  # [{name, url}]
    pv_url: Optional[str] = None

    # Extraction metadata
    confidence: float = 0.0
    extraction_notes: List[str] = None

    def __post_init__(self):
        if self.dates_visite is None:
            self.dates_visite = []
        if self.photos is None:
            self.photos = []
        if self.documents is None:
            self.documents = []
        if self.extraction_notes is None:
            self.extraction_notes = []


class LLMExtractor:
    """
    Extracts structured auction data from HTML using Claude

    Benefits over regex:
    - Understands context and semantics
    - Handles variations in formatting
    - Distinguishes property address from lawyer address
    - Extracts dates in any French format
    - Self-correcting with confidence scores
    """

    EXTRACTION_PROMPT = """Tu es un expert en extraction de données immobilières françaises.
Analyse cette page HTML d'une vente aux enchères judiciaire et extrais TOUTES les informations structurées.

IMPORTANT:
- L'adresse du BIEN est différente de l'adresse de l'AVOCAT - ne les confonds pas
- Les dates de visite sont différentes de la date de vente
- Convertis tous les prix en nombres (pas de symboles)
- Les dates doivent être en format ISO (YYYY-MM-DD ou YYYY-MM-DDTHH:MM pour les visites)
- Le code postal est un nombre à 5 chiffres (13001, 83500, etc.)

Retourne un JSON avec cette structure exacte:
{
    "adresse": "adresse complète du bien (PAS de l'avocat)",
    "code_postal": "code postal 5 chiffres",
    "ville": "nom de la ville",
    "department": "numéro département (13, 83, etc.)",
    "type_bien": "appartement|maison|local_commercial|terrain|parking",
    "surface": nombre en m²,
    "nb_pieces": nombre de pièces,
    "nb_chambres": nombre de chambres,
    "etage": numéro d'étage (null si maison),
    "description": "description du bien",
    "occupation": "libre|occupé|inconnu",
    "mise_a_prix": nombre en euros,
    "date_vente": "YYYY-MM-DD",
    "heure_vente": "HHhMM",
    "dates_visite": ["YYYY-MM-DDTHH:MM", ...],
    "tribunal": "nom du tribunal",
    "avocat_nom": "nom de l'avocat",
    "avocat_cabinet": "nom du cabinet",
    "avocat_telephone": "numéro de téléphone",
    "avocat_email": "email",
    "avocat_adresse": "adresse du cabinet (PAS du bien)",
    "photos": ["url1", "url2", ...],
    "documents": [{"name": "Cahier des charges", "url": "..."}, ...],
    "pv_url": "URL du procès-verbal si disponible",
    "confidence": 0.0 à 1.0 (confiance dans l'extraction),
    "extraction_notes": ["note sur les données manquantes ou incertaines", ...]
}

Si une information n'est pas trouvée, utilise null.
Retourne UNIQUEMENT le JSON, pas d'explication."""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-haiku-20241022"):
        """
        Initialize the LLM extractor

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Claude model to use (haiku is fast and cheap for extraction)
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self._client = None

        # Cache directory for extracted data
        self.cache_dir = Path(__file__).parent.parent.parent / "data" / "extraction_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if not self.api_key:
            logger.warning("[LLMExtractor] No ANTHROPIC_API_KEY found. Set it in environment or pass to constructor.")

    @property
    def client(self):
        """Lazy initialization of Anthropic client"""
        if self._client is None:
            if not HAS_ANTHROPIC:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")
            if not self.api_key:
                raise ValueError("ANTHROPIC_API_KEY not set")
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _get_cache_key(self, html: str, url: str) -> str:
        """Generate cache key from URL and HTML hash"""
        content_hash = hashlib.md5(html.encode()).hexdigest()[:8]
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return f"{url_hash}_{content_hash}"

    def _load_from_cache(self, cache_key: str) -> Optional[ExtractedAuctionData]:
        """Load extracted data from cache"""
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                logger.debug(f"[LLMExtractor] Loaded from cache: {cache_key}")
                return ExtractedAuctionData(**data)
            except Exception as e:
                logger.warning(f"[LLMExtractor] Cache load error: {e}")
        return None

    def _save_to_cache(self, cache_key: str, data: ExtractedAuctionData):
        """Save extracted data to cache"""
        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(asdict(data), f, ensure_ascii=False, indent=2)
            logger.debug(f"[LLMExtractor] Saved to cache: {cache_key}")
        except Exception as e:
            logger.warning(f"[LLMExtractor] Cache save error: {e}")

    def _clean_html(self, html: str) -> str:
        """
        Clean HTML to reduce token usage while preserving important content
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')

        # Remove scripts, styles, and other non-content elements
        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'noscript', 'iframe']):
            tag.decompose()

        # Remove comments
        from bs4 import Comment
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Get text with some structure preserved
        # Keep important semantic elements
        text_parts = []

        # Extract title
        title = soup.find('title')
        if title:
            text_parts.append(f"TITRE: {title.get_text(strip=True)}")

        # Extract main content areas
        main_content = soup.find('main') or soup.find('article') or soup.find(class_=lambda x: x and 'content' in str(x).lower())
        if main_content:
            soup = main_content

        # Get all text with paragraph breaks
        text = soup.get_text(separator='\n', strip=True)

        # Clean up excessive whitespace
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        # Also extract image URLs
        images = []
        for img in soup.find_all('img', src=True):
            src = img.get('src', '')
            if src and not any(x in src.lower() for x in ['logo', 'icon', 'avatar', 'sprite']):
                images.append(src)

        # Extract document links
        docs = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            link_text = link.get_text(strip=True)
            if '.pdf' in href.lower() or any(x in link_text.lower() for x in ['cahier', 'pv', 'document', 'télécharger']):
                docs.append(f"{link_text}: {href}")

        result = text_parts + [text]
        if images:
            result.append(f"\nIMAGES: {', '.join(images[:10])}")
        if docs:
            result.append(f"\nDOCUMENTS: {', '.join(docs)}")

        return '\n'.join(result)[:15000]  # Limit to ~15k chars to stay within token limits

    def extract(self, html: str, url: str, use_cache: bool = True) -> Optional[ExtractedAuctionData]:
        """
        Extract structured auction data from HTML using Claude

        Args:
            html: Raw HTML content of the auction page
            url: URL of the page (for caching and context)
            use_cache: Whether to use cached extractions

        Returns:
            ExtractedAuctionData object or None if extraction fails
        """
        if not self.api_key:
            logger.error("[LLMExtractor] No API key configured")
            return None

        # Check cache
        cache_key = self._get_cache_key(html, url)
        if use_cache:
            cached = self._load_from_cache(cache_key)
            if cached:
                return cached

        # Clean HTML to reduce tokens
        cleaned_html = self._clean_html(html)

        try:
            logger.info(f"[LLMExtractor] Extracting data from {url}")

            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[
                    {
                        "role": "user",
                        "content": f"{self.EXTRACTION_PROMPT}\n\nURL: {url}\n\nCONTENU DE LA PAGE:\n{cleaned_html}"
                    }
                ]
            )

            # Parse JSON response
            response_text = response.content[0].text.strip()

            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            data = json.loads(response_text)

            # Convert to dataclass
            result = ExtractedAuctionData(
                adresse=data.get("adresse"),
                code_postal=data.get("code_postal"),
                ville=data.get("ville"),
                department=data.get("department"),
                type_bien=data.get("type_bien"),
                surface=data.get("surface"),
                nb_pieces=data.get("nb_pieces"),
                nb_chambres=data.get("nb_chambres"),
                etage=data.get("etage"),
                description=data.get("description"),
                occupation=data.get("occupation"),
                mise_a_prix=data.get("mise_a_prix"),
                date_vente=data.get("date_vente"),
                heure_vente=data.get("heure_vente"),
                dates_visite=data.get("dates_visite", []),
                tribunal=data.get("tribunal"),
                avocat_nom=data.get("avocat_nom"),
                avocat_cabinet=data.get("avocat_cabinet"),
                avocat_telephone=data.get("avocat_telephone"),
                avocat_email=data.get("avocat_email"),
                avocat_adresse=data.get("avocat_adresse"),
                photos=data.get("photos", []),
                documents=data.get("documents", []),
                pv_url=data.get("pv_url"),
                confidence=data.get("confidence", 0.5),
                extraction_notes=data.get("extraction_notes", [])
            )

            # Cache the result
            if use_cache:
                self._save_to_cache(cache_key, result)

            logger.info(f"[LLMExtractor] Extracted: {result.ville} ({result.code_postal}), confidence: {result.confidence}")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"[LLMExtractor] JSON parse error: {e}")
            logger.debug(f"[LLMExtractor] Response was: {response_text[:500]}")
            return None
        except anthropic.APIError as e:
            logger.error(f"[LLMExtractor] API error: {e}")
            return None
        except Exception as e:
            logger.error(f"[LLMExtractor] Extraction error: {e}")
            return None

    def extract_from_url(self, url: str, use_cache: bool = True) -> Optional[ExtractedAuctionData]:
        """
        Fetch URL and extract data

        Args:
            url: URL to fetch and extract from
            use_cache: Whether to use cached extractions
        """
        import requests

        try:
            response = requests.get(url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            })
            response.raise_for_status()
            return self.extract(response.text, url, use_cache)
        except requests.RequestException as e:
            logger.error(f"[LLMExtractor] Fetch error for {url}: {e}")
            return None


# Convenience function for quick extraction
def extract_auction_data(url: str, api_key: Optional[str] = None) -> Optional[ExtractedAuctionData]:
    """
    Quick extraction of auction data from URL

    Args:
        url: Auction page URL
        api_key: Optional Anthropic API key

    Returns:
        ExtractedAuctionData or None
    """
    extractor = LLMExtractor(api_key=api_key)
    return extractor.extract_from_url(url)
