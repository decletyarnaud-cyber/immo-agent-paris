"""
Base classes for price sources
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class SourceType(Enum):
    """Types of price data sources"""
    DVF = "dvf"                    # Official transaction data
    COMMUNE_STATS = "commune"      # Aggregated commune statistics
    LISTINGS = "listings"          # Online listings (asking prices)
    NOTAIRES = "notaires"          # Notary indices


class ReliabilityLevel(Enum):
    """Reliability levels for estimates"""
    HIGH = "high"           # Many data points, multiple sources agree
    MEDIUM = "medium"       # Some data, sources mostly agree
    LOW = "low"             # Few data points or sources disagree
    INSUFFICIENT = "insufficient"  # Not enough data


@dataclass
class PriceEstimate:
    """Price estimate from a single source"""
    source_type: SourceType
    source_name: str
    prix_m2: Optional[float]
    prix_total: Optional[float] = None

    # Data quality indicators
    nb_data_points: int = 0
    date_range_days: int = 0           # How recent is the data
    geographic_match: str = ""         # "exact", "commune", "department"

    # Raw data for transparency
    comparables: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    retrieved_at: datetime = field(default_factory=datetime.now)
    source_url: Optional[str] = None
    notes: str = ""

    @property
    def confidence_score(self) -> float:
        """Calculate confidence score (0-100) based on data quality"""
        score = 0.0

        # Number of data points (max 40 points)
        if self.nb_data_points >= 20:
            score += 40
        elif self.nb_data_points >= 10:
            score += 30
        elif self.nb_data_points >= 5:
            score += 20
        elif self.nb_data_points >= 3:
            score += 10

        # Data recency (max 30 points)
        if self.date_range_days <= 180:  # 6 months
            score += 30
        elif self.date_range_days <= 365:  # 1 year
            score += 20
        elif self.date_range_days <= 730:  # 2 years
            score += 10

        # Geographic match (max 30 points)
        if self.geographic_match == "exact":
            score += 30
        elif self.geographic_match == "commune":
            score += 20
        elif self.geographic_match == "department":
            score += 10

        return score


@dataclass
class MultiSourceEstimate:
    """Combined estimate from multiple sources"""
    # Individual source estimates
    estimates: List[PriceEstimate] = field(default_factory=list)

    # Combined values
    prix_m2_combined: Optional[float] = None
    prix_m2_min: Optional[float] = None
    prix_m2_max: Optional[float] = None

    # Reliability assessment
    reliability: ReliabilityLevel = ReliabilityLevel.INSUFFICIENT
    reliability_score: float = 0.0  # 0-100
    sources_agreement: float = 0.0  # 0-100, how much sources agree

    # Breakdown by source type
    dvf_estimate: Optional[float] = None
    listings_estimate: Optional[float] = None
    commune_estimate: Optional[float] = None

    # For display
    analysis_notes: List[str] = field(default_factory=list)

    def add_estimate(self, estimate: PriceEstimate):
        """Add an estimate and recalculate combined values"""
        if estimate.prix_m2:
            self.estimates.append(estimate)
            self._recalculate()

    def _recalculate(self):
        """Recalculate combined values from all estimates"""
        valid_estimates = [e for e in self.estimates if e.prix_m2]

        if not valid_estimates:
            return

        prices = [e.prix_m2 for e in valid_estimates]
        weights = [e.confidence_score for e in valid_estimates]

        # Weighted average
        if sum(weights) > 0:
            self.prix_m2_combined = sum(p * w for p, w in zip(prices, weights)) / sum(weights)
        else:
            self.prix_m2_combined = sum(prices) / len(prices)

        self.prix_m2_min = min(prices)
        self.prix_m2_max = max(prices)

        # Store by source type
        for e in valid_estimates:
            if e.source_type == SourceType.DVF:
                self.dvf_estimate = e.prix_m2
            elif e.source_type == SourceType.LISTINGS:
                self.listings_estimate = e.prix_m2
            elif e.source_type == SourceType.COMMUNE_STATS:
                self.commune_estimate = e.prix_m2

        # Calculate reliability
        self._calculate_reliability()

    def _calculate_reliability(self):
        """Calculate overall reliability score"""
        if not self.estimates:
            self.reliability = ReliabilityLevel.INSUFFICIENT
            self.reliability_score = 0
            return

        # Average confidence of sources
        avg_confidence = sum(e.confidence_score for e in self.estimates) / len(self.estimates)

        # Bonus for multiple sources
        source_bonus = min(20, len(self.estimates) * 10)

        # Calculate agreement (inverse of coefficient of variation)
        prices = [e.prix_m2 for e in self.estimates if e.prix_m2]
        if len(prices) >= 2:
            mean_price = sum(prices) / len(prices)
            if mean_price > 0:
                std_dev = (sum((p - mean_price) ** 2 for p in prices) / len(prices)) ** 0.5
                cv = std_dev / mean_price  # Coefficient of variation
                self.sources_agreement = max(0, 100 - cv * 200)  # 0% CV = 100 agreement
            else:
                self.sources_agreement = 0
        else:
            self.sources_agreement = 50  # Single source, medium agreement

        # Combined reliability score
        self.reliability_score = (avg_confidence * 0.5 + source_bonus + self.sources_agreement * 0.3)
        self.reliability_score = min(100, self.reliability_score)

        # Determine level
        if self.reliability_score >= 70 and len(self.estimates) >= 2:
            self.reliability = ReliabilityLevel.HIGH
        elif self.reliability_score >= 40:
            self.reliability = ReliabilityLevel.MEDIUM
        elif self.reliability_score > 0:
            self.reliability = ReliabilityLevel.LOW
        else:
            self.reliability = ReliabilityLevel.INSUFFICIENT


class PriceSource(ABC):
    """Abstract base class for price data sources"""

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """Return the type of this source"""
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name of this source"""
        pass

    @abstractmethod
    def get_price_estimate(
        self,
        code_postal: str,
        ville: str,
        type_bien: str,
        surface: Optional[float] = None,
    ) -> Optional[PriceEstimate]:
        """
        Get price estimate for a property

        Args:
            code_postal: Postal code
            ville: City name
            type_bien: Property type (appartement, maison, etc.)
            surface: Property surface in m² (optional, for better matching)

        Returns:
            PriceEstimate or None if no data available
        """
        pass
