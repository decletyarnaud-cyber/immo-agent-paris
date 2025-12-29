"""
DVF (Demandes de Valeurs Foncières) price source
Uses official French government transaction data
"""
from datetime import date, timedelta
from typing import Optional, List
from loguru import logger

from .base import PriceSource, PriceEstimate, SourceType
from ..dvf_client import DVFClient, DVFSearchParams


class DVFPriceSource(PriceSource):
    """
    Price source using DVF (official transaction data)

    Source: data.gouv.fr - Demandes de Valeurs Foncières
    Updated: Twice yearly (April and October)
    """

    SOURCE_URL = "https://app.dvf.etalab.gouv.fr/"

    # Price filters
    MIN_PRICE_M2 = 500
    MAX_PRICE_M2 = 15000
    MIN_COMPARABLES = 3

    def __init__(self, dvf_client: Optional[DVFClient] = None):
        self._client = dvf_client or DVFClient()

    @property
    def source_type(self) -> SourceType:
        return SourceType.DVF

    @property
    def source_name(self) -> str:
        return "DVF (Transactions officielles)"

    def get_price_estimate(
        self,
        code_postal: str,
        ville: str,
        type_bien: str,
        surface: Optional[float] = None,
    ) -> Optional[PriceEstimate]:
        """Get price estimate from DVF transactions"""

        if not code_postal:
            return None

        # Map property type to DVF type_local
        type_mapping = {
            "appartement": "Appartement",
            "maison": "Maison",
            "local_commercial": "Local",
            "parking": "Dépendance",
            "terrain": "Terrain",
        }
        type_local = type_mapping.get(type_bien.lower(), "Appartement")

        # Search parameters
        surface_ref = surface or 60  # Default 60m² if unknown
        tolerance = 0.30  # 30% tolerance

        try:
            transactions = self._client.find_comparable_sales(
                code_postal=code_postal,
                surface=surface_ref,
                type_local=type_local,
                tolerance_percent=tolerance * 100,
                months=24,
                limit=50,
            )
        except Exception as e:
            logger.error(f"[DVFSource] Error fetching transactions: {e}")
            return None

        if not transactions:
            return None

        # Filter outliers and calculate median
        valid_prices = []
        comparables_data = []

        for t in transactions:
            if t.prix_m2 and self.MIN_PRICE_M2 <= t.prix_m2 <= self.MAX_PRICE_M2:
                valid_prices.append(t.prix_m2)
                comparables_data.append({
                    "date": t.date_mutation.isoformat() if t.date_mutation else None,
                    "adresse": t.adresse,
                    "commune": t.commune,
                    "surface": t.surface_reelle,
                    "prix": t.valeur_fonciere,
                    "prix_m2": round(t.prix_m2, 0),
                })

        if len(valid_prices) < self.MIN_COMPARABLES:
            logger.warning(f"[DVFSource] Only {len(valid_prices)} valid comparables for {code_postal}")
            return PriceEstimate(
                source_type=self.source_type,
                source_name=self.source_name,
                prix_m2=None,
                nb_data_points=len(valid_prices),
                notes=f"Données insuffisantes ({len(valid_prices)} transactions)",
                source_url=self.SOURCE_URL,
            )

        # Calculate median
        valid_prices.sort()
        n = len(valid_prices)
        if n % 2 == 0:
            median_price = (valid_prices[n // 2 - 1] + valid_prices[n // 2]) / 2
        else:
            median_price = valid_prices[n // 2]

        # Calculate date range
        dates = [t.date_mutation for t in transactions if t.date_mutation]
        if dates:
            date_range = (date.today() - min(dates)).days
        else:
            date_range = 730  # Default 2 years

        return PriceEstimate(
            source_type=self.source_type,
            source_name=self.source_name,
            prix_m2=round(median_price, 0),
            prix_total=round(median_price * surface_ref, 0) if surface else None,
            nb_data_points=len(valid_prices),
            date_range_days=date_range,
            geographic_match="commune",
            comparables=comparables_data[:10],  # Keep top 10 for display
            source_url=self.SOURCE_URL,
            notes=f"Médiane de {len(valid_prices)} transactions sur 24 mois",
        )
