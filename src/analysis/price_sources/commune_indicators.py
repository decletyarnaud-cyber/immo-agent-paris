"""
Commune price indicators from data.gouv.fr
Aggregated price statistics by commune
"""
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import requests
from loguru import logger

from .base import PriceSource, PriceEstimate, SourceType

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from config.settings import DATA_DIR


class CommuneIndicatorsSource(PriceSource):
    """
    Price source using aggregated commune indicators from data.gouv.fr

    This provides average/median prices by commune, useful as a reference point.
    """

    # Dataset URL from data.gouv.fr (updated 2024)
    DATASET_URL = "https://static.data.gouv.fr/resources/indicateurs-immobiliers-par-commune-et-par-annee-prix-et-volumes-sur-la-periode-2014-2024/20250707-085855/communesdvf2024.csv"
    DATA_FILE = DATA_DIR / "commune_indicators.json"
    SOURCE_URL = "https://www.data.gouv.fr/fr/datasets/indicateurs-immobiliers-par-commune-et-par-annee-prix-et-volumes-sur-la-periode-2014-2024/"

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._load_data()

    @property
    def source_type(self) -> SourceType:
        return SourceType.COMMUNE_STATS

    @property
    def source_name(self) -> str:
        return "Indicateurs Commune (data.gouv.fr)"

    def _load_data(self):
        """Load commune indicators from local cache or download"""
        if self.DATA_FILE.exists():
            try:
                with open(self.DATA_FILE, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
                logger.info(f"[CommuneIndicators] Loaded {len(self._data)} communes from cache")
                return
            except Exception as e:
                logger.warning(f"[CommuneIndicators] Failed to load cache: {e}")

        # If no cache, data will be empty
        logger.info("[CommuneIndicators] No local data, use download_indicators() to fetch")

    def download_indicators(self) -> bool:
        """Download and process commune indicators from data.gouv.fr"""
        logger.info("[CommuneIndicators] Downloading commune indicators...")

        try:
            response = requests.get(self.DATASET_URL, timeout=60)
            response.raise_for_status()

            # Parse CSV content (comma-separated)
            lines = response.text.splitlines()
            reader = csv.DictReader(lines, delimiter=',')

            data = {}
            for row in reader:
                try:
                    # Use INSEE code as key (first 2 digits = department, can derive postal code)
                    insee_code = row.get('INSEE_COM', '').strip()
                    annee = row.get('annee', '').strip()

                    if not insee_code or not annee:
                        continue

                    # Derive postal code from INSEE code (approximate - department prefix)
                    # For departments 13 and 83 (our focus area)
                    dept = insee_code[:2]
                    if dept not in ['13', '83']:
                        continue  # Only keep our departments

                    # Parse price data
                    prix_m2 = self._parse_float(row.get('Prixm2Moyen', ''))
                    prix_moyen = self._parse_float(row.get('PrixMoyen', ''))
                    nb_mutations = self._parse_int(row.get('nb_mutations', ''))
                    nb_maisons = self._parse_int(row.get('NbMaisons', ''))
                    nb_apparts = self._parse_int(row.get('NbApparts', ''))
                    surface_moy = self._parse_float(row.get('SurfaceMoy', ''))

                    # Use INSEE code as key
                    key = insee_code

                    if key not in data:
                        data[key] = {
                            'insee_code': insee_code,
                            'department': dept,
                            'years': {}
                        }

                    data[key]['years'][annee] = {
                        'prix_m2': prix_m2,
                        'prix_moyen': prix_moyen,
                        'nb_mutations': nb_mutations,
                        'nb_maisons': nb_maisons,
                        'nb_apparts': nb_apparts,
                        'surface_moy': surface_moy,
                    }

                except Exception as e:
                    continue

            # Also create postal code index (approximate mapping)
            # For common cities in 13 and 83
            postal_mapping = {
                # Bouches-du-Rhône (13)
                '13001': '13001',  # Marseille 1er
                '13055': '13001',  # Marseille (main INSEE)
                '13004': '13100',  # Aix-en-Provence
                '13028': '13400',  # Aubagne
                '13047': '13500',  # Martigues
                # Var (83)
                '83137': '83000',  # Toulon
                '83050': '83400',  # Hyères
                '83061': '83600',  # Fréjus
            }

            # Add postal code lookups
            for insee, postal in postal_mapping.items():
                if insee in data:
                    data[postal] = data[insee]
                    data[postal]['code_postal'] = postal

            # Save to cache
            self.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self._data = data
            logger.info(f"[CommuneIndicators] Downloaded data for {len(data)} communes in departments 13 and 83")
            return True

        except Exception as e:
            logger.error(f"[CommuneIndicators] Download failed: {e}")
            return False

    def _parse_float(self, value: str) -> Optional[float]:
        """Parse float from string, handling comma decimals"""
        try:
            return float(value.replace(',', '.').replace(' ', ''))
        except:
            return None

    def _parse_int(self, value: str) -> Optional[int]:
        """Parse int from string"""
        try:
            return int(value.replace(' ', ''))
        except:
            return None

    def get_price_estimate(
        self,
        code_postal: str,
        ville: str,
        type_bien: str,
        surface: Optional[float] = None,
    ) -> Optional[PriceEstimate]:
        """Get price estimate from commune indicators"""

        if not self._data:
            return None

        # Look up by postal code first, then try INSEE code patterns
        commune_data = self._data.get(code_postal)

        if not commune_data:
            # Try to find by department prefix (approximate)
            dept = code_postal[:2]
            # Search for any commune in this department
            for key, data in self._data.items():
                if data.get('department') == dept:
                    commune_data = data
                    break

        if not commune_data:
            return None

        # Get most recent year's data
        years = commune_data.get('years', {})
        if not years:
            return None

        # Sort years descending and get most recent
        sorted_years = sorted(years.keys(), reverse=True)
        latest_year = sorted_years[0]
        latest_data = years[latest_year]

        # Get price (this dataset has overall prix_m2, not split by type)
        prix_m2 = latest_data.get('prix_m2')
        nb_mutations = latest_data.get('nb_mutations', 0)

        if not prix_m2:
            return None

        # Calculate days since data (approximate - using mid-year)
        try:
            data_date = datetime(int(latest_year), 6, 30)
            date_range = (datetime.now() - data_date).days
        except:
            date_range = 365

        return PriceEstimate(
            source_type=self.source_type,
            source_name=self.source_name,
            prix_m2=round(prix_m2, 0),
            prix_total=round(prix_m2 * surface, 0) if surface else None,
            nb_data_points=nb_mutations or 0,
            date_range_days=date_range,
            geographic_match="commune",
            source_url=self.SOURCE_URL,
            notes=f"Moyenne commune {latest_year} ({nb_mutations or '?'} mutations)",
            comparables=[{
                'annee': year,
                'prix_m2': data.get('prix_m2'),
                'nb_mutations': data.get('nb_mutations'),
                'surface_moy': data.get('surface_moy'),
            } for year, data in sorted(years.items(), reverse=True)[:5]],
        )
