"""
Cross-source validation for auction data
Merges data from multiple sources to improve reliability
"""
import re
from datetime import date, datetime
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from loguru import logger

from src.storage.models import Auction, PropertyType


@dataclass
class ValidationResult:
    """Result of cross-validation"""
    merged_auction: Auction
    sources_matched: List[str]
    fields_from_source: Dict[str, str]  # field -> source
    confidence: float
    validation_notes: List[str] = field(default_factory=list)


class CrossValidator:
    """
    Cross-validates auction data from multiple sources

    Strategy:
    1. Match auctions across sources by:
       - Same tribunal + similar date + similar price
       - Similar address/location
       - Same property type + surface

    2. For each field, pick the best value:
       - Non-empty over empty
       - Longer/more specific over shorter
       - Validated format over raw

    3. Calculate confidence score based on agreement
    """

    # Known postal codes for cities (for validation) - Paris et petite couronne
    POSTAL_CODES = {
        # Paris (75)
        "paris": "75001", "paris 1er": "75001", "paris 2eme": "75002", "paris 3eme": "75003",
        "paris 4eme": "75004", "paris 5eme": "75005", "paris 6eme": "75006", "paris 7eme": "75007",
        "paris 8eme": "75008", "paris 9eme": "75009", "paris 10eme": "75010", "paris 11eme": "75011",
        "paris 12eme": "75012", "paris 13eme": "75013", "paris 14eme": "75014", "paris 15eme": "75015",
        "paris 16eme": "75016", "paris 17eme": "75017", "paris 18eme": "75018", "paris 19eme": "75019",
        "paris 20eme": "75020",
        # Hauts-de-Seine (92)
        "boulogne-billancourt": "92100", "nanterre": "92000", "courbevoie": "92400",
        "colombes": "92700", "asnieres-sur-seine": "92600", "rueil-malmaison": "92500",
        "levallois-perret": "92300", "issy-les-moulineaux": "92130", "neuilly-sur-seine": "92200",
        "antony": "92160", "clamart": "92140", "montrouge": "92120", "meudon": "92190",
        "suresnes": "92150", "puteaux": "92800", "gennevilliers": "92230", "clichy": "92110",
        "malakoff": "92240", "vanves": "92170", "chatillon": "92320", "bagneux": "92220",
        "fontenay-aux-roses": "92260", "le plessis-robinson": "92350", "sceaux": "92330",
        "bourg-la-reine": "92340", "chatenay-malabry": "92290",
        # Seine-Saint-Denis (93)
        "saint-denis": "93200", "montreuil": "93100", "aubervilliers": "93300",
        "aulnay-sous-bois": "93600", "drancy": "93700", "noisy-le-grand": "93160",
        "pantin": "93500", "bondy": "93140", "epinay-sur-seine": "93800",
        "sevran": "93270", "le blanc-mesnil": "93150", "bobigny": "93000",
        "saint-ouen": "93400", "rosny-sous-bois": "93110", "livry-gargan": "93190",
        "la courneuve": "93120", "bagnolet": "93170", "le pre-saint-gervais": "93310",
        "les lilas": "93260", "romainville": "93230", "noisy-le-sec": "93130",
        "villepinte": "93420", "tremblay-en-france": "93290", "stains": "93240",
        # Val-de-Marne (94)
        "creteil": "94000", "vitry-sur-seine": "94400", "saint-maur-des-fosses": "94100",
        "champigny-sur-marne": "94500", "ivry-sur-seine": "94200", "maisons-alfort": "94700",
        "fontenay-sous-bois": "94120", "villejuif": "94800", "vincennes": "94300",
        "alfortville": "94140", "choisy-le-roi": "94600", "le kremlin-bicetre": "94270",
        "cachan": "94230", "charenton-le-pont": "94220", "nogent-sur-marne": "94130",
        "joinville-le-pont": "94340", "saint-mande": "94160", "thiais": "94320",
        "orly": "94310", "gentilly": "94250", "arcueil": "94110", "fresnes": "94260",
        "le perreux-sur-marne": "94170", "bry-sur-marne": "94360", "sucy-en-brie": "94370",
    }

    # Reverse lookup
    CITIES_BY_POSTAL = {v: k for k, v in POSTAL_CODES.items()}

    def __init__(self):
        self.stats = {
            'total_processed': 0,
            'matches_found': 0,
            'fields_improved': 0,
        }

    def _normalize_text(self, text: Optional[str]) -> str:
        """Normalize text for comparison"""
        if not text:
            return ""
        # Lowercase, remove accents approximation, normalize spaces
        text = text.lower().strip()
        text = re.sub(r'\s+', ' ', text)
        # Common replacements
        replacements = {
            'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
            'à': 'a', 'â': 'a', 'ä': 'a',
            'ù': 'u', 'û': 'u', 'ü': 'u',
            'ô': 'o', 'ö': 'o',
            'î': 'i', 'ï': 'i',
            'ç': 'c',
            '-': ' ', "'": ' ',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    def _similarity(self, a: Optional[str], b: Optional[str]) -> float:
        """Calculate similarity between two strings"""
        if not a or not b:
            return 0.0
        a_norm = self._normalize_text(a)
        b_norm = self._normalize_text(b)
        return SequenceMatcher(None, a_norm, b_norm).ratio()

    def _match_auctions(self, auction1: Auction, auction2: Auction) -> float:
        """
        Calculate match score between two auctions (0-1)

        High score = likely same property
        """
        score = 0.0
        weights = 0.0

        # Same date de vente (strong indicator)
        if auction1.date_vente and auction2.date_vente:
            if auction1.date_vente == auction2.date_vente:
                score += 0.3
            weights += 0.3

        # Same tribunal
        if auction1.tribunal and auction2.tribunal:
            if self._similarity(auction1.tribunal, auction2.tribunal) > 0.7:
                score += 0.15
            weights += 0.15

        # Similar price (within 10%)
        if auction1.mise_a_prix and auction2.mise_a_prix:
            price_diff = abs(auction1.mise_a_prix - auction2.mise_a_prix)
            avg_price = (auction1.mise_a_prix + auction2.mise_a_prix) / 2
            if price_diff / avg_price < 0.1:
                score += 0.2
            weights += 0.2

        # Same city
        if auction1.ville and auction2.ville:
            if self._similarity(auction1.ville, auction2.ville) > 0.8:
                score += 0.15
            weights += 0.15

        # Same property type
        if auction1.type_bien and auction2.type_bien:
            if auction1.type_bien == auction2.type_bien:
                score += 0.1
            weights += 0.1

        # Similar surface (within 5%)
        if auction1.surface and auction2.surface:
            surface_diff = abs(auction1.surface - auction2.surface)
            avg_surface = (auction1.surface + auction2.surface) / 2
            if surface_diff / avg_surface < 0.05:
                score += 0.1
            weights += 0.1

        return score / weights if weights > 0 else 0.0

    def _pick_best_value(
        self,
        val1: Any,
        val2: Any,
        source1: str,
        source2: str,
        field_name: str
    ) -> Tuple[Any, str]:
        """
        Pick the best value between two sources

        Returns: (value, source_name)
        """
        # Both empty
        if not val1 and not val2:
            return None, ""

        # One empty, one not
        if val1 and not val2:
            return val1, source1
        if val2 and not val1:
            return val2, source2

        # Both have values - pick based on field type
        if field_name in ['adresse', 'description', 'avocat_adresse']:
            # Prefer longer (more complete)
            if len(str(val1)) > len(str(val2)):
                return val1, source1
            return val2, source2

        elif field_name in ['code_postal']:
            # Validate format (5 digits)
            v1_valid = bool(re.match(r'^\d{5}$', str(val1)))
            v2_valid = bool(re.match(r'^\d{5}$', str(val2)))
            if v1_valid and not v2_valid:
                return val1, source1
            if v2_valid and not v1_valid:
                return val2, source2
            # Both valid or both invalid - prefer first
            return val1, source1

        elif field_name in ['ville']:
            # Check against known cities
            v1_known = self._normalize_text(val1) in self.POSTAL_CODES
            v2_known = self._normalize_text(val2) in self.POSTAL_CODES
            if v1_known and not v2_known:
                return val1, source1
            if v2_known and not v1_known:
                return val2, source2
            # Both known - prefer longer/more specific (La Seyne-sur-Mer > Toulon)
            if len(str(val1)) > len(str(val2)):
                return val1, source1
            if len(str(val2)) > len(str(val1)):
                return val2, source2
            # Same length - prefer source2 as it often has more detailed data
            return val2, source2

        elif field_name in ['surface', 'nb_pieces', 'nb_chambres', 'mise_a_prix']:
            # Numeric - prefer non-zero
            if val1 and (not val2 or val2 == 0):
                return val1, source1
            if val2 and (not val1 or val1 == 0):
                return val2, source2
            # Both have values - average might be more accurate but stick with first
            return val1, source1

        elif field_name in ['photos', 'documents']:
            # Lists - merge
            merged = list(val1 or []) + list(val2 or [])
            # Deduplicate
            seen = set()
            unique = []
            for item in merged:
                key = str(item)
                if key not in seen:
                    seen.add(key)
                    unique.append(item)
            return unique, f"{source1}+{source2}"

        # Default: prefer first source
        return val1, source1

    def _enrich_from_postal(self, auction: Auction) -> List[str]:
        """
        Enrich auction data using postal code database

        Returns list of changes made
        """
        changes = []

        # If we have postal code but no city
        if auction.code_postal and not auction.ville:
            city = self.CITIES_BY_POSTAL.get(auction.code_postal)
            if city:
                auction.ville = city.title()
                changes.append(f"ville inferred from postal code: {auction.ville}")

        # If we have city but no postal code
        if auction.ville and not auction.code_postal:
            city_norm = self._normalize_text(auction.ville)
            # Handle city with district (Marseille 14ème)
            match = re.match(r'marseille\s*(\d+)', city_norm)
            if match:
                district = int(match.group(1))
                auction.code_postal = f"130{district:02d}"
                changes.append(f"postal code inferred from Marseille district: {auction.code_postal}")
            elif city_norm in self.POSTAL_CODES:
                auction.code_postal = self.POSTAL_CODES[city_norm]
                changes.append(f"postal code inferred from city: {auction.code_postal}")

        # Validate city matches postal code - CORRECT if mismatch
        if auction.code_postal and auction.ville:
            expected_city = self.CITIES_BY_POSTAL.get(auction.code_postal)
            if expected_city:
                ville_norm = self._normalize_text(auction.ville)
                expected_norm = self._normalize_text(expected_city)
                # If city doesn't match postal code, trust postal code
                if ville_norm != expected_norm and self._similarity(ville_norm, expected_norm) < 0.6:
                    old_ville = auction.ville
                    auction.ville = expected_city.title()
                    changes.append(f"ville corrected from '{old_ville}' to '{auction.ville}' (based on postal code {auction.code_postal})")

        # Infer department from postal code
        if auction.code_postal and not auction.department:
            auction.department = auction.code_postal[:2]
            changes.append(f"department inferred: {auction.department}")

        return changes

    def merge_auctions(self, auction1: Auction, auction2: Auction) -> ValidationResult:
        """
        Merge two auctions into one with best data from each

        Args:
            auction1: First auction (usually from Licitor)
            auction2: Second auction (usually from encheres-publiques)

        Returns:
            ValidationResult with merged auction
        """
        source1 = auction1.source or "source1"
        source2 = auction2.source or "source2"

        merged = Auction()
        fields_from = {}
        notes = []

        # Preserve source info
        merged.source = f"{source1}+{source2}"
        merged.url = auction1.url or auction2.url

        # Merge each field
        fields_to_merge = [
            'adresse', 'code_postal', 'ville', 'department',
            'type_bien', 'surface', 'nb_pieces', 'nb_chambres', 'etage',
            'description', 'occupation',
            'mise_a_prix', 'date_vente', 'heure_vente', 'tribunal',
            'avocat_nom', 'avocat_cabinet', 'avocat_telephone', 'avocat_email', 'avocat_adresse',
            'pv_url', 'photos', 'documents'
        ]

        for field in fields_to_merge:
            val1 = getattr(auction1, field, None)
            val2 = getattr(auction2, field, None)

            best_val, best_source = self._pick_best_value(val1, val2, source1, source2, field)

            if best_val is not None:
                setattr(merged, field, best_val)
                if best_source:
                    fields_from[field] = best_source
                    if val1 != val2 and val1 and val2:
                        notes.append(f"{field}: picked '{best_val}' from {best_source} over '{val1 if best_source == source2 else val2}'")

        # Merge dates_visite (combine lists)
        all_dates = list(auction1.dates_visite or []) + list(auction2.dates_visite or [])
        merged.dates_visite = sorted(set(all_dates))
        if auction1.dates_visite and auction2.dates_visite:
            fields_from['dates_visite'] = f"{source1}+{source2}"

        # Enrich from postal code database
        enrichment_notes = self._enrich_from_postal(merged)
        notes.extend(enrichment_notes)

        # Calculate confidence
        agreement_count = sum(
            1 for f in fields_to_merge
            if getattr(auction1, f, None) and getattr(auction2, f, None)
            and getattr(auction1, f, None) == getattr(auction2, f, None)
        )
        total_fields = sum(1 for f in fields_to_merge if getattr(merged, f, None))
        confidence = (agreement_count / total_fields) if total_fields > 0 else 0.5

        self.stats['fields_improved'] += len([n for n in notes if 'picked' in n or 'inferred' in n])

        return ValidationResult(
            merged_auction=merged,
            sources_matched=[source1, source2],
            fields_from_source=fields_from,
            confidence=confidence,
            validation_notes=notes
        )

    def find_matches(
        self,
        auctions_source1: List[Auction],
        auctions_source2: List[Auction],
        threshold: float = 0.5
    ) -> List[Tuple[Auction, Auction, float]]:
        """
        Find matching auctions between two sources

        Returns: List of (auction1, auction2, match_score) tuples
        """
        matches = []
        used_indices = set()

        for a1 in auctions_source1:
            best_match = None
            best_score = 0.0
            best_idx = -1

            for idx, a2 in enumerate(auctions_source2):
                if idx in used_indices:
                    continue

                score = self._match_auctions(a1, a2)
                if score > best_score and score >= threshold:
                    best_match = a2
                    best_score = score
                    best_idx = idx

            if best_match:
                matches.append((a1, best_match, best_score))
                used_indices.add(best_idx)
                self.stats['matches_found'] += 1

        logger.info(f"[CrossValidator] Found {len(matches)} matches between sources")
        return matches

    def validate_and_merge_all(
        self,
        auctions_source1: List[Auction],
        auctions_source2: List[Auction],
        threshold: float = 0.5
    ) -> List[Auction]:
        """
        Cross-validate and merge auctions from two sources

        Args:
            auctions_source1: Auctions from first source (e.g., Licitor)
            auctions_source2: Auctions from second source (e.g., encheres-publiques)
            threshold: Minimum match score to consider a match

        Returns:
            List of merged/validated auctions
        """
        self.stats['total_processed'] = len(auctions_source1) + len(auctions_source2)

        # Find matches
        matches = self.find_matches(auctions_source1, auctions_source2, threshold)

        results = []
        matched_from_s1 = set()
        matched_from_s2 = set()

        # Process matches - merge them
        for a1, a2, score in matches:
            result = self.merge_auctions(a1, a2)
            results.append(result.merged_auction)
            matched_from_s1.add(id(a1))
            matched_from_s2.add(id(a2))

            if result.validation_notes:
                logger.debug(f"[CrossValidator] Merged {a1.ville}/{a2.ville}: {result.validation_notes}")

        # Add unmatched auctions (but enrich them)
        for a in auctions_source1:
            if id(a) not in matched_from_s1:
                self._enrich_from_postal(a)
                results.append(a)

        for a in auctions_source2:
            if id(a) not in matched_from_s2:
                self._enrich_from_postal(a)
                results.append(a)

        logger.info(f"[CrossValidator] Results: {len(matches)} merged, "
                    f"{len(auctions_source1) - len(matches)} from source1 only, "
                    f"{len(auctions_source2) - len(matches)} from source2 only")

        return results

    def get_stats(self) -> Dict[str, int]:
        """Get validation statistics"""
        return self.stats.copy()


# Convenience function
def cross_validate(
    licitor_auctions: List[Auction],
    encheres_auctions: List[Auction]
) -> List[Auction]:
    """
    Cross-validate auctions from Licitor and EnchèresPubliques

    Args:
        licitor_auctions: Auctions scraped from Licitor
        encheres_auctions: Auctions scraped from EnchèresPubliques

    Returns:
        List of validated/merged auctions
    """
    validator = CrossValidator()
    return validator.validate_and_merge_all(licitor_auctions, encheres_auctions)
