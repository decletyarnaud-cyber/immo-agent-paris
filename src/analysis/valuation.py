"""
Property valuation and opportunity scoring module
"""
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import date, datetime
from loguru import logger

from src.storage.models import Auction, AnalysisReport
from .market_analyzer import MarketAnalyzer, MarketComparison


@dataclass
class ValuationResult:
    """Complete valuation result for an auction"""
    auction: Auction
    market_comparison: MarketComparison

    # Valuation
    estimated_value: Optional[float] = None
    potential_profit: Optional[float] = None
    roi_percent: Optional[float] = None

    # Scoring
    opportunity_score: float = 0  # 0-100
    investment_score: float = 0  # 0-100
    risk_score: float = 0  # 0-100 (lower is better)

    # Classification
    badge: str = ""  # "Opportunité", "Bonne affaire", etc.
    badge_color: str = "gray"  # green, orange, red, gray

    # Details
    strengths: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


class PropertyValuator:
    """
    Complete property valuation for judicial auctions
    """

    BADGES = {
        "exceptional": {"label": "Opportunité exceptionnelle", "color": "green"},
        "opportunity": {"label": "Opportunité", "color": "green"},
        "good_deal": {"label": "Bonne affaire", "color": "lightgreen"},
        "fair": {"label": "Prix marché", "color": "orange"},
        "overpriced": {"label": "À éviter", "color": "red"},
        "unknown": {"label": "À analyser", "color": "gray"},
    }

    # Estimated costs as percentage of purchase price
    ADDITIONAL_COSTS = {
        "frais_avocat": 0.02,  # ~2% lawyer fees
        "frais_divers": 0.03,  # ~3% various fees (registration, etc.)
        "travaux_estimation": 0.10,  # 10% estimated renovation
    }

    def __init__(self, market_analyzer: Optional[MarketAnalyzer] = None):
        self.market_analyzer = market_analyzer or MarketAnalyzer()

    def valuate(self, auction: Auction) -> ValuationResult:
        """
        Complete valuation of an auction

        Args:
            auction: The auction to valuate

        Returns:
            ValuationResult with complete analysis
        """
        # Get market comparison
        comparison = self.market_analyzer.analyze_auction(auction)

        # Calculate valuation
        result = ValuationResult(
            auction=auction,
            market_comparison=comparison,
        )

        # Estimated value
        result.estimated_value = comparison.estimated_market_value

        # Calculate potential profit
        if result.estimated_value and auction.mise_a_prix:
            # Account for additional costs
            total_cost = auction.mise_a_prix * (1 + sum(self.ADDITIONAL_COSTS.values()))
            result.potential_profit = result.estimated_value - total_cost

            if total_cost > 0:
                result.roi_percent = (result.potential_profit / total_cost) * 100

        # Scores
        result.opportunity_score = comparison.opportunity_score
        result.investment_score = self._calculate_investment_score(auction, comparison)
        result.risk_score = self._calculate_risk_score(auction, comparison)

        # Badge
        badge_key = self._determine_badge(comparison, result)
        result.badge = self.BADGES[badge_key]["label"]
        result.badge_color = self.BADGES[badge_key]["color"]

        # Strengths and risks
        result.strengths = self._identify_strengths(auction, comparison)
        result.risks = self._identify_risks(auction, comparison)
        result.notes = self._generate_notes(auction, comparison)

        return result

    def _calculate_investment_score(self, auction: Auction, comparison: MarketComparison) -> float:
        """Calculate investment attractiveness score"""
        score = 0

        # Base from opportunity score
        score += comparison.opportunity_score * 0.5

        # Bonus for surface/price ratio
        if auction.surface and auction.mise_a_prix:
            price_per_m2 = auction.mise_a_prix / auction.surface
            if comparison.market_price_m2:
                ratio = price_per_m2 / comparison.market_price_m2
                if ratio < 0.5:
                    score += 20
                elif ratio < 0.7:
                    score += 15
                elif ratio < 0.8:
                    score += 10

        # Bonus for good location (more comparables)
        if len(comparison.comparable_transactions) >= 10:
            score += 10

        # Cap at 100
        return min(100, score)

    def _calculate_risk_score(self, auction: Auction, comparison: MarketComparison) -> float:
        """
        Calculate risk score (0-100, lower is better)
        """
        risk = 0

        # Lack of data
        if len(comparison.comparable_transactions) < 3:
            risk += 20
        elif len(comparison.comparable_transactions) < 5:
            risk += 10

        # No surface info
        if not auction.surface:
            risk += 15

        # No visit dates
        if not auction.dates_visite:
            risk += 10

        # High starting price relative to market
        if comparison.discount_percent is not None and comparison.discount_percent < 10:
            risk += 15

        # Unknown occupation status (from description)
        if auction.description:
            desc_lower = auction.description.lower()
            if "occupé" in desc_lower or "loué" in desc_lower:
                risk += 20  # Occupied property is riskier

        # Very low price (might indicate problems)
        if auction.mise_a_prix and comparison.estimated_market_value:
            if auction.mise_a_prix < comparison.estimated_market_value * 0.3:
                risk += 15  # Suspiciously low

        return min(100, risk)

    def _determine_badge(self, comparison: MarketComparison, result: ValuationResult) -> str:
        """Determine the badge to display"""
        if comparison.discount_percent is None:
            return "unknown"

        if comparison.discount_percent >= 40 and result.risk_score < 40:
            return "exceptional"
        elif comparison.discount_percent >= 30:
            return "opportunity"
        elif comparison.discount_percent >= 20:
            return "good_deal"
        elif comparison.discount_percent >= 0:
            return "fair"
        else:
            return "overpriced"

    def _identify_strengths(self, auction: Auction, comparison: MarketComparison) -> List[str]:
        """Identify positive points"""
        strengths = []

        if comparison.discount_percent and comparison.discount_percent >= 20:
            strengths.append(f"Décote de {comparison.discount_percent:.0f}% par rapport au marché")

        if len(comparison.comparable_transactions) >= 10:
            strengths.append("Nombreuses transactions comparables (données fiables)")

        if auction.surface and auction.surface > 50:
            strengths.append(f"Belle surface de {auction.surface}m²")

        if auction.dates_visite:
            strengths.append(f"{len(auction.dates_visite)} date(s) de visite programmée(s)")

        if auction.pv_url:
            strengths.append("Procès-verbal disponible")

        if comparison.market_price_m2 and auction.mise_a_prix and auction.surface:
            price_m2 = auction.mise_a_prix / auction.surface
            if price_m2 < comparison.market_price_m2 * 0.7:
                strengths.append(f"Prix/m² très attractif ({price_m2:.0f}€ vs {comparison.market_price_m2:.0f}€ marché)")

        return strengths

    def _identify_risks(self, auction: Auction, comparison: MarketComparison) -> List[str]:
        """Identify risk factors"""
        risks = []

        if len(comparison.comparable_transactions) < 3:
            risks.append("Peu de données comparables (estimation moins fiable)")

        if not auction.surface:
            risks.append("Surface non renseignée")

        if not auction.dates_visite:
            risks.append("Aucune date de visite connue")

        if auction.description:
            desc_lower = auction.description.lower()
            if "occupé" in desc_lower:
                risks.append("Bien potentiellement occupé")
            if "travaux" in desc_lower or "rénovation" in desc_lower:
                risks.append("Travaux probablement nécessaires")

        if comparison.discount_percent and comparison.discount_percent < 10:
            risks.append("Faible décote par rapport au marché")

        if comparison.discount_percent and comparison.discount_percent < 0:
            risks.append("Prix supérieur au marché!")

        return risks

    def _generate_notes(self, auction: Auction, comparison: MarketComparison) -> List[str]:
        """Generate informational notes"""
        notes = []

        # Auction date info
        if auction.date_vente:
            days_until = (auction.date_vente - date.today()).days
            if days_until > 0:
                notes.append(f"Vente dans {days_until} jours")
            elif days_until == 0:
                notes.append("Vente aujourd'hui!")
            else:
                notes.append("Vente passée")

        # Market context
        if comparison.market_price_m2:
            notes.append(f"Prix moyen du secteur: {comparison.market_price_m2:.0f}€/m²")

        # Tribunal
        if auction.tribunal:
            notes.append(f"Tribunal: {auction.tribunal}")

        return notes

    def valuate_batch(self, auctions: List[Auction]) -> List[ValuationResult]:
        """
        Valuate multiple auctions

        Args:
            auctions: List of auctions

        Returns:
            List of ValuationResult, sorted by opportunity score
        """
        results = []

        for auction in auctions:
            try:
                result = self.valuate(auction)
                results.append(result)
            except Exception as e:
                logger.error(f"Error valuating auction {auction.source_id}: {e}")

        # Sort by opportunity score (highest first)
        results.sort(key=lambda x: x.opportunity_score, reverse=True)

        return results

    def get_top_opportunities(
        self,
        auctions: List[Auction],
        min_score: float = 50,
        limit: int = 10
    ) -> List[ValuationResult]:
        """
        Get top investment opportunities

        Args:
            auctions: List of auctions to analyze
            min_score: Minimum opportunity score
            limit: Maximum results

        Returns:
            Top opportunities sorted by score
        """
        results = self.valuate_batch(auctions)

        # Filter by minimum score
        filtered = [r for r in results if r.opportunity_score >= min_score]

        return filtered[:limit]

    def to_report(self, result: ValuationResult) -> AnalysisReport:
        """Convert ValuationResult to AnalysisReport"""
        return AnalysisReport(
            auction_id=result.auction.id or 0,
            date_analyse=datetime.now(),
            transactions_comparables=result.market_comparison.comparable_transactions,
            prix_m2_moyen_secteur=result.market_comparison.market_price_m2,
            prix_estime=result.estimated_value,
            decote=result.market_comparison.discount_percent,
            score=result.opportunity_score,
            recommandation=result.badge,
            points_forts=result.strengths,
            points_vigilance=result.risks,
        )
