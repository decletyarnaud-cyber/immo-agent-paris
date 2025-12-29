"""
Market analysis module - Compare auction prices with market data
"""
from datetime import date, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from loguru import logger

from .dvf_client import DVFClient, DVFSearchParams
from src.storage.models import Auction, DVFTransaction, AnalysisReport

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import ANALYSIS


@dataclass
class MarketComparison:
    """Result of market comparison"""
    auction: Auction
    comparable_transactions: List[DVFTransaction]
    market_price_m2: Optional[float]
    estimated_market_value: Optional[float]
    discount_percent: Optional[float]
    opportunity_score: float  # 0-100
    recommendation: str


class MarketAnalyzer:
    """
    Analyze auction prices compared to market data
    """

    SCORE_WEIGHTS = {
        "discount": 0.5,      # How much below market
        "data_quality": 0.2,  # Number of comparable transactions
        "recency": 0.15,      # How recent the comparable data is
        "location_match": 0.15,  # How well location matches
    }

    RECOMMENDATIONS = {
        "exceptional": "Opportunité exceptionnelle",
        "opportunity": "Bonne opportunité",
        "good_deal": "Bonne affaire",
        "fair": "Prix marché",
        "overpriced": "Surévalué",
        "no_data": "Données insuffisantes",
    }

    def __init__(self, dvf_client: Optional[DVFClient] = None):
        self.dvf_client = dvf_client or DVFClient()
        self.good_deal_threshold = ANALYSIS["good_deal_threshold"]
        self.opportunity_threshold = ANALYSIS["opportunity_threshold"]

    def analyze_auction(self, auction: Auction) -> MarketComparison:
        """
        Analyze a single auction against market data

        Args:
            auction: The auction to analyze

        Returns:
            MarketComparison with analysis results
        """
        # Get comparable transactions
        comparables = self._find_comparables(auction)

        if not comparables:
            return MarketComparison(
                auction=auction,
                comparable_transactions=[],
                market_price_m2=None,
                estimated_market_value=None,
                discount_percent=None,
                opportunity_score=0,
                recommendation=self.RECOMMENDATIONS["no_data"],
            )

        # Calculate market price per m²
        market_price_m2 = self._calculate_market_price_m2(comparables)

        # Estimate market value
        estimated_value = None
        if market_price_m2 and auction.surface:
            estimated_value = market_price_m2 * auction.surface

        # Calculate discount
        discount = None
        if estimated_value and auction.mise_a_prix:
            discount = (estimated_value - auction.mise_a_prix) / estimated_value

        # Calculate opportunity score
        score = self._calculate_opportunity_score(
            discount=discount,
            num_comparables=len(comparables),
            comparables=comparables,
            auction=auction,
        )

        # Determine recommendation
        recommendation = self._get_recommendation(discount, score)

        # Update auction with analysis results
        auction.prix_marche_estime = estimated_value
        auction.prix_m2_marche = market_price_m2
        auction.decote_pourcentage = discount * 100 if discount else None
        auction.score_opportunite = score

        return MarketComparison(
            auction=auction,
            comparable_transactions=comparables,
            market_price_m2=market_price_m2,
            estimated_market_value=estimated_value,
            discount_percent=discount * 100 if discount else None,
            opportunity_score=score,
            recommendation=recommendation,
        )

    def _find_comparables(self, auction: Auction) -> List[DVFTransaction]:
        """Find comparable transactions for an auction"""
        if not auction.code_postal:
            return []

        # Determine property type for DVF
        type_local = "Appartement"  # Default
        if auction.type_bien:
            type_mapping = {
                "appartement": "Appartement",
                "maison": "Maison",
                "local_commercial": "Local",
                "parking": "Dépendance",
            }
            type_local = type_mapping.get(auction.type_bien.value, "Appartement")

        # Get surface tolerance
        surface = auction.surface or 50  # Default 50m² if unknown
        tolerance = 25  # 25% tolerance

        return self.dvf_client.find_comparable_sales(
            code_postal=auction.code_postal,
            surface=surface,
            type_local=type_local,
            tolerance_percent=tolerance,
            months=24,
            limit=20,
        )

    def _calculate_market_price_m2(self, transactions: List[DVFTransaction]) -> Optional[float]:
        """Calculate median price per m² with outlier filtering"""
        if not transactions:
            return None

        # Filter out outliers: keep only reasonable prices (500-15000 €/m²)
        MIN_PRICE_M2 = 500   # Below this is likely a gift, family transfer, or error
        MAX_PRICE_M2 = 15000  # Above this is likely luxury or data error
        MIN_VALID_COMPARABLES = 3  # Minimum for reliable estimate

        valid_prices = []
        for t in transactions:
            if t.prix_m2 and MIN_PRICE_M2 <= t.prix_m2 <= MAX_PRICE_M2:
                valid_prices.append(t.prix_m2)

        # Require minimum number of valid comparables for reliability
        if len(valid_prices) < MIN_VALID_COMPARABLES:
            logger.warning(f"Only {len(valid_prices)} valid comparables (need {MIN_VALID_COMPARABLES})")
            return None

        # Use median for robustness against remaining outliers
        valid_prices.sort()
        n = len(valid_prices)
        if n % 2 == 0:
            return (valid_prices[n // 2 - 1] + valid_prices[n // 2]) / 2
        else:
            return valid_prices[n // 2]

    def _calculate_opportunity_score(
        self,
        discount: Optional[float],
        num_comparables: int,
        comparables: List[DVFTransaction],
        auction: Auction,
    ) -> float:
        """
        Calculate opportunity score (0-100)

        Higher score = better opportunity
        """
        scores = {}

        # Discount score (0-50 points)
        if discount is not None:
            if discount >= 0.40:
                scores["discount"] = 50
            elif discount >= 0.30:
                scores["discount"] = 40
            elif discount >= 0.20:
                scores["discount"] = 30
            elif discount >= 0.10:
                scores["discount"] = 20
            elif discount >= 0:
                scores["discount"] = 10
            else:
                scores["discount"] = 0
        else:
            scores["discount"] = 0

        # Data quality score (0-20 points)
        if num_comparables >= 10:
            scores["data_quality"] = 20
        elif num_comparables >= 5:
            scores["data_quality"] = 15
        elif num_comparables >= 3:
            scores["data_quality"] = 10
        elif num_comparables >= 1:
            scores["data_quality"] = 5
        else:
            scores["data_quality"] = 0

        # Recency score (0-15 points)
        if comparables:
            avg_age = sum(
                (date.today() - t.date_mutation).days
                for t in comparables if t.date_mutation
            ) / len(comparables)

            if avg_age <= 180:  # 6 months
                scores["recency"] = 15
            elif avg_age <= 365:  # 1 year
                scores["recency"] = 10
            else:
                scores["recency"] = 5
        else:
            scores["recency"] = 0

        # Location match score (0-15 points)
        # Based on how many comparables are in the same postal code
        same_cp = sum(1 for t in comparables if t.code_postal == auction.code_postal)
        if same_cp >= 5:
            scores["location_match"] = 15
        elif same_cp >= 3:
            scores["location_match"] = 10
        elif same_cp >= 1:
            scores["location_match"] = 5
        else:
            scores["location_match"] = 0

        return sum(scores.values())

    def _get_recommendation(self, discount: Optional[float], score: float) -> str:
        """Get recommendation based on discount and score"""
        if discount is None:
            return self.RECOMMENDATIONS["no_data"]

        if discount >= 0.40:
            return self.RECOMMENDATIONS["exceptional"]
        elif discount >= self.opportunity_threshold:
            return self.RECOMMENDATIONS["opportunity"]
        elif discount >= self.good_deal_threshold:
            return self.RECOMMENDATIONS["good_deal"]
        elif discount >= 0:
            return self.RECOMMENDATIONS["fair"]
        else:
            return self.RECOMMENDATIONS["overpriced"]

    def analyze_multiple(self, auctions: List[Auction]) -> List[MarketComparison]:
        """
        Analyze multiple auctions

        Args:
            auctions: List of auctions to analyze

        Returns:
            List of MarketComparison results, sorted by opportunity score
        """
        results = []

        for auction in auctions:
            try:
                result = self.analyze_auction(auction)
                results.append(result)
            except Exception as e:
                logger.error(f"Error analyzing auction {auction.source_id}: {e}")

        # Sort by opportunity score (highest first)
        results.sort(key=lambda x: x.opportunity_score, reverse=True)

        return results

    def get_market_stats(self, code_postal: str, type_bien: str = "Appartement") -> Dict[str, Any]:
        """
        Get market statistics for a postal code

        Args:
            code_postal: Postal code
            type_bien: Property type

        Returns:
            Dictionary with market statistics
        """
        stats = self.dvf_client.get_price_per_m2_stats(
            code_postal=code_postal,
            type_local=type_bien,
            months=24,
        )

        return {
            "code_postal": code_postal,
            "type_bien": type_bien,
            "transactions_count": stats.get("count", 0),
            "prix_m2_moyen": stats.get("mean"),
            "prix_m2_median": stats.get("median"),
            "prix_m2_min": stats.get("min"),
            "prix_m2_max": stats.get("max"),
            "periode": "24 derniers mois",
        }
