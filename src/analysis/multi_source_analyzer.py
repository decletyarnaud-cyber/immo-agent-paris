"""
Multi-source market price analyzer
Combines DVF, commune indicators, and online listings for robust price estimates
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from loguru import logger

from .price_sources.base import (
    PriceSource, PriceEstimate, MultiSourceEstimate,
    SourceType, ReliabilityLevel
)
from .price_sources.dvf_source import DVFPriceSource
from .price_sources.commune_indicators import CommuneIndicatorsSource
from .price_sources.listings_scraper import ListingsPriceSource
from .dvf_client import DVFClient


@dataclass
class DetailedPriceAnalysis:
    """Complete price analysis for a property"""
    # Input parameters
    code_postal: str
    ville: str
    type_bien: str
    surface: Optional[float]

    # Multi-source estimate
    estimate: MultiSourceEstimate = field(default_factory=MultiSourceEstimate)

    # Final recommendation
    prix_m2_recommended: Optional[float] = None
    prix_total_estimated: Optional[float] = None

    # Comparison with auction
    mise_a_prix: Optional[float] = None
    decote_vs_market: Optional[float] = None

    # Reliability assessment
    reliability: ReliabilityLevel = ReliabilityLevel.INSUFFICIENT
    reliability_score: float = 0.0

    # Analysis details
    analysis_notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Metadata
    analyzed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/display"""
        return {
            'code_postal': self.code_postal,
            'ville': self.ville,
            'type_bien': self.type_bien,
            'surface': self.surface,
            'prix_m2_recommended': self.prix_m2_recommended,
            'prix_total_estimated': self.prix_total_estimated,
            'mise_a_prix': self.mise_a_prix,
            'decote_vs_market': self.decote_vs_market,
            'reliability': self.reliability.value,
            'reliability_score': self.reliability_score,
            'sources': {
                'dvf': self.estimate.dvf_estimate,
                'commune': self.estimate.commune_estimate,
                'listings': self.estimate.listings_estimate,
            },
            'price_range': {
                'min': self.estimate.prix_m2_min,
                'max': self.estimate.prix_m2_max,
            },
            'analysis_notes': self.analysis_notes,
            'warnings': self.warnings,
            'analyzed_at': self.analyzed_at.isoformat(),
        }


class MultiSourceAnalyzer:
    """
    Analyzes property prices using multiple data sources

    Sources:
    1. DVF (Demandes de Valeurs Foncières) - Official transaction data
    2. Commune indicators from data.gouv.fr - Aggregated statistics
    3. Online listings - Current asking prices (with correction)

    The analyzer:
    - Fetches data from all available sources
    - Compares estimates and calculates agreement
    - Produces a reliability score
    - Generates a recommended price with confidence interval
    """

    def __init__(self, dvf_client: Optional[DVFClient] = None):
        self._dvf_source = DVFPriceSource(dvf_client)
        self._commune_source = CommuneIndicatorsSource()
        self._listings_source = ListingsPriceSource()

        self._sources: List[PriceSource] = [
            self._dvf_source,
            self._commune_source,
            self._listings_source,
        ]

    def analyze(
        self,
        code_postal: str,
        ville: str,
        type_bien: str,
        surface: Optional[float] = None,
        mise_a_prix: Optional[float] = None,
    ) -> DetailedPriceAnalysis:
        """
        Perform comprehensive price analysis

        Args:
            code_postal: Postal code
            ville: City name
            type_bien: Property type (appartement, maison, etc.)
            surface: Property surface in m² (for better accuracy)
            mise_a_prix: Auction starting price (for comparison)

        Returns:
            DetailedPriceAnalysis with all source data and recommendations
        """
        analysis = DetailedPriceAnalysis(
            code_postal=code_postal,
            ville=ville,
            type_bien=type_bien,
            surface=surface,
            mise_a_prix=mise_a_prix,
        )

        logger.info(f"[MultiSource] Analyzing {ville} ({code_postal}), {type_bien}, {surface}m²")

        # Collect estimates from all sources
        for source in self._sources:
            try:
                estimate = source.get_price_estimate(
                    code_postal=code_postal,
                    ville=ville,
                    type_bien=type_bien,
                    surface=surface,
                )

                if estimate and estimate.prix_m2:
                    analysis.estimate.add_estimate(estimate)
                    analysis.analysis_notes.append(
                        f"{source.source_name}: {estimate.prix_m2:,.0f} €/m² "
                        f"({estimate.nb_data_points} données, confiance: {estimate.confidence_score:.0f}%)"
                    )
                    logger.info(f"[MultiSource] {source.source_name}: {estimate.prix_m2:,.0f} €/m²")
                else:
                    analysis.analysis_notes.append(
                        f"{source.source_name}: Données insuffisantes"
                    )

            except Exception as e:
                logger.error(f"[MultiSource] Error from {source.source_name}: {e}")
                analysis.warnings.append(f"Erreur {source.source_name}: {str(e)}")

        # Generate recommendation
        self._generate_recommendation(analysis)

        # Compare with auction price
        if mise_a_prix and analysis.prix_m2_recommended and surface:
            market_value = analysis.prix_m2_recommended * surface
            analysis.decote_vs_market = ((market_value - mise_a_prix) / market_value) * 100

        # Transfer reliability from estimate
        analysis.reliability = analysis.estimate.reliability
        analysis.reliability_score = analysis.estimate.reliability_score

        return analysis

    def _generate_recommendation(self, analysis: DetailedPriceAnalysis):
        """Generate final price recommendation from multi-source estimate"""
        estimate = analysis.estimate

        if not estimate.estimates:
            analysis.warnings.append("Aucune source de données disponible")
            return

        # Use combined weighted estimate
        if estimate.prix_m2_combined:
            analysis.prix_m2_recommended = round(estimate.prix_m2_combined, 0)

            if analysis.surface:
                analysis.prix_total_estimated = round(
                    analysis.prix_m2_recommended * analysis.surface, 0
                )

        # Add notes about source agreement
        if len(estimate.estimates) >= 2:
            if estimate.sources_agreement >= 80:
                analysis.analysis_notes.append(
                    f"Sources en accord ({estimate.sources_agreement:.0f}%)"
                )
            elif estimate.sources_agreement >= 50:
                analysis.analysis_notes.append(
                    f"Accord modéré entre sources ({estimate.sources_agreement:.0f}%)"
                )
            else:
                analysis.warnings.append(
                    f"Désaccord entre sources ({estimate.sources_agreement:.0f}%) - "
                    f"plage: {estimate.prix_m2_min:,.0f} - {estimate.prix_m2_max:,.0f} €/m²"
                )

        # Reliability warnings
        if analysis.reliability == ReliabilityLevel.LOW:
            analysis.warnings.append(
                "Fiabilité faible - peu de données ou sources en désaccord"
            )
        elif analysis.reliability == ReliabilityLevel.INSUFFICIENT:
            analysis.warnings.append(
                "Données insuffisantes pour une estimation fiable"
            )

    def download_commune_data(self) -> bool:
        """Download commune indicators (call periodically)"""
        return self._commune_source.download_indicators()

    def clear_listings_cache(self):
        """Clear the listings cache"""
        self._listings_source.clear_cache()

    def get_source_details(self, analysis: DetailedPriceAnalysis) -> Dict[str, Any]:
        """Get detailed information about each source for display"""
        details = {}

        for estimate in analysis.estimate.estimates:
            source_key = estimate.source_type.value
            details[source_key] = {
                'name': estimate.source_name,
                'prix_m2': estimate.prix_m2,
                'confidence': estimate.confidence_score,
                'nb_data_points': estimate.nb_data_points,
                'date_range_days': estimate.date_range_days,
                'geographic_match': estimate.geographic_match,
                'source_url': estimate.source_url,
                'notes': estimate.notes,
                'comparables': estimate.comparables[:5],  # Top 5 for display
            }

        return details
