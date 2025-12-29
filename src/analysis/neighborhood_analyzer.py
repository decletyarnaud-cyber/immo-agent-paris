"""
Neighborhood price analyzer using DVF data
Analyzes real estate prices by postal code, property type, and time period
"""
from datetime import date, datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict
from dataclasses import dataclass
from loguru import logger

from .dvf_client import DVFClient


@dataclass
class NeighborhoodStats:
    """Statistics for a neighborhood/postal code"""
    code_postal: str
    ville: str
    nb_transactions: int
    prix_m2_median: float
    prix_m2_moyen: float
    prix_m2_min: float
    prix_m2_max: float
    surface_moyenne: float
    prix_moyen: float
    annee: int
    type_bien: str  # "Appartement", "Maison", "Tous"


class NeighborhoodAnalyzer:
    """Analyzes real estate prices by neighborhood using DVF data"""

    def __init__(self, dvf_client: Optional[DVFClient] = None):
        self._client = dvf_client or DVFClient()
        self._cache: Dict[str, List[NeighborhoodStats]] = {}

    def get_all_neighborhood_stats(
        self,
        department: str = "13",
        year: Optional[int] = None,
        type_bien: Optional[str] = None,
    ) -> List[NeighborhoodStats]:
        """
        Get price statistics for all neighborhoods in a department

        Args:
            department: Department code (13 or 83)
            year: Filter by year (None = all years)
            type_bien: Filter by property type ("Appartement", "Maison", None = all)

        Returns:
            List of NeighborhoodStats sorted by prix_m2_median descending
        """
        cache_key = f"{department}_{year}_{type_bien}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Load DVF data for department
        self._client.load_data(department)
        transactions = self._client._transactions.get(department, [])

        if not transactions:
            logger.warning(f"[NeighborhoodAnalyzer] No DVF data for department {department}")
            return []

        # Group transactions by postal code
        by_postal = defaultdict(list)
        for t in transactions:
            # Filter by year if specified
            if year and t.date_mutation:
                if t.date_mutation.year != year:
                    continue

            # Filter by type if specified
            if type_bien and t.type_local != type_bien:
                continue

            # Only include valid transactions with price per m²
            if t.prix_m2 and 500 <= t.prix_m2 <= 15000 and t.code_postal:
                by_postal[t.code_postal].append(t)

        # Calculate stats for each postal code
        stats = []
        for code_postal, trans in by_postal.items():
            if len(trans) < 3:  # Minimum 3 transactions for meaningful stats
                continue

            prices_m2 = sorted([t.prix_m2 for t in trans])
            surfaces = [t.surface_reelle for t in trans if t.surface_reelle]
            total_prices = [t.valeur_fonciere for t in trans if t.valeur_fonciere]

            # Calculate median
            n = len(prices_m2)
            if n % 2 == 0:
                median = (prices_m2[n // 2 - 1] + prices_m2[n // 2]) / 2
            else:
                median = prices_m2[n // 2]

            # Get ville name from first transaction
            ville = trans[0].commune or self._get_ville_from_postal(code_postal)

            stat = NeighborhoodStats(
                code_postal=code_postal,
                ville=ville,
                nb_transactions=len(trans),
                prix_m2_median=round(median, 0),
                prix_m2_moyen=round(sum(prices_m2) / len(prices_m2), 0),
                prix_m2_min=round(min(prices_m2), 0),
                prix_m2_max=round(max(prices_m2), 0),
                surface_moyenne=round(sum(surfaces) / len(surfaces), 1) if surfaces else 0,
                prix_moyen=round(sum(total_prices) / len(total_prices), 0) if total_prices else 0,
                annee=year or 0,
                type_bien=type_bien or "Tous",
            )
            stats.append(stat)

        # Sort by median price descending
        stats.sort(key=lambda x: x.prix_m2_median, reverse=True)

        self._cache[cache_key] = stats
        return stats

    def get_price_evolution(
        self,
        code_postal: str,
        type_bien: Optional[str] = None,
        years: List[int] = None,
    ) -> Dict[int, NeighborhoodStats]:
        """
        Get price evolution over multiple years for a specific postal code

        Returns:
            Dict mapping year to stats
        """
        if years is None:
            years = [2022, 2023, 2024]

        department = code_postal[:2]
        evolution = {}

        for year in years:
            all_stats = self.get_all_neighborhood_stats(department, year, type_bien)
            for stat in all_stats:
                if stat.code_postal == code_postal:
                    evolution[year] = stat
                    break

        return evolution

    def get_top_neighborhoods(
        self,
        department: str = "13",
        year: int = 2024,
        type_bien: Optional[str] = None,
        top_n: int = 20,
        sort_by: str = "prix_m2_median",  # or "nb_transactions", "prix_m2_moyen"
        ascending: bool = False,
    ) -> List[NeighborhoodStats]:
        """Get top N neighborhoods by specified criteria"""
        stats = self.get_all_neighborhood_stats(department, year, type_bien)

        if sort_by == "prix_m2_median":
            stats.sort(key=lambda x: x.prix_m2_median, reverse=not ascending)
        elif sort_by == "nb_transactions":
            stats.sort(key=lambda x: x.nb_transactions, reverse=not ascending)
        elif sort_by == "prix_m2_moyen":
            stats.sort(key=lambda x: x.prix_m2_moyen, reverse=not ascending)

        return stats[:top_n]

    def compare_neighborhoods(
        self,
        codes_postaux: List[str],
        year: int = 2024,
        type_bien: Optional[str] = None,
    ) -> List[NeighborhoodStats]:
        """Compare specific neighborhoods"""
        results = []
        for cp in codes_postaux:
            department = cp[:2]
            all_stats = self.get_all_neighborhood_stats(department, year, type_bien)
            for stat in all_stats:
                if stat.code_postal == cp:
                    results.append(stat)
                    break
        return results

    def get_department_summary(
        self,
        department: str = "13",
        year: int = 2024,
    ) -> Dict[str, Any]:
        """Get summary statistics for entire department"""
        # Get stats for all property types
        all_stats = self.get_all_neighborhood_stats(department, year)
        appart_stats = self.get_all_neighborhood_stats(department, year, "Appartement")
        maison_stats = self.get_all_neighborhood_stats(department, year, "Maison")

        def calc_summary(stats_list):
            if not stats_list:
                return None
            total_trans = sum(s.nb_transactions for s in stats_list)
            weighted_price = sum(s.prix_m2_median * s.nb_transactions for s in stats_list)
            return {
                "nb_quartiers": len(stats_list),
                "nb_transactions": total_trans,
                "prix_m2_median_global": round(weighted_price / total_trans, 0) if total_trans else 0,
                "quartier_plus_cher": stats_list[0] if stats_list else None,
                "quartier_moins_cher": stats_list[-1] if stats_list else None,
            }

        return {
            "department": department,
            "year": year,
            "tous_biens": calc_summary(all_stats),
            "appartements": calc_summary(appart_stats),
            "maisons": calc_summary(maison_stats),
        }

    def _get_ville_from_postal(self, code_postal: str) -> str:
        """Get city name from postal code"""
        # Common mappings for departments 13 and 83
        postal_to_ville = {
            "13001": "Marseille 1er",
            "13002": "Marseille 2ème",
            "13003": "Marseille 3ème",
            "13004": "Marseille 4ème",
            "13005": "Marseille 5ème",
            "13006": "Marseille 6ème",
            "13007": "Marseille 7ème",
            "13008": "Marseille 8ème",
            "13009": "Marseille 9ème",
            "13010": "Marseille 10ème",
            "13011": "Marseille 11ème",
            "13012": "Marseille 12ème",
            "13013": "Marseille 13ème",
            "13014": "Marseille 14ème",
            "13015": "Marseille 15ème",
            "13016": "Marseille 16ème",
            "13100": "Aix-en-Provence",
            "13090": "Aix-en-Provence",
            "13400": "Aubagne",
            "13500": "Martigues",
            "13600": "La Ciotat",
            "13127": "Vitrolles",
            "13300": "Salon-de-Provence",
            "83000": "Toulon",
            "83100": "Toulon",
            "83200": "Toulon",
            "83400": "Hyères",
            "83600": "Fréjus",
            "83700": "Saint-Raphaël",
            "83500": "La Seyne-sur-Mer",
        }
        return postal_to_ville.get(code_postal, f"CP {code_postal}")
