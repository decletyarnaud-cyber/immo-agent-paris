"""
DVF (Demandes de Valeurs Foncières) API client
Access to official French real estate transaction data
"""
import os
import gzip
import csv
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import requests
from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import DATA_DIR, DVF, DEPARTMENTS
from src.storage.models import DVFTransaction


@dataclass
class DVFSearchParams:
    """Parameters for DVF search"""
    code_postal: Optional[str] = None
    commune: Optional[str] = None
    department: Optional[str] = None
    type_local: Optional[str] = None  # Appartement, Maison, etc.
    date_min: Optional[date] = None
    date_max: Optional[date] = None
    prix_min: Optional[float] = None
    prix_max: Optional[float] = None
    surface_min: Optional[float] = None
    surface_max: Optional[float] = None


class DVFClient:
    """
    Client for accessing DVF (Demandes de Valeurs Foncières) data

    DVF provides official data on real estate transactions in France.
    Data is available as open data from data.gouv.fr
    """

    # Column mappings for DVF CSV files
    COLUMN_MAPPING = {
        "date_mutation": "date_mutation",
        "nature_mutation": "nature_mutation",
        "valeur_fonciere": "valeur_fonciere",
        "adresse_numero": "no_voie",
        "adresse_nom_voie": "voie",
        "code_postal": "code_postal",
        "nom_commune": "commune",
        "type_local": "type_local",
        "surface_reelle_bati": "surface_reelle_bati",
        "nombre_pieces_principales": "nombre_pieces_principales",
        "latitude": "latitude",
        "longitude": "longitude",
    }

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize DVF client

        Args:
            data_dir: Directory to store downloaded DVF data
        """
        self.data_dir = data_dir or DATA_DIR / "dvf"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()

        # Cache for loaded data
        self._data_cache: Dict[str, List[DVFTransaction]] = {}

    def download_department_data(self, department: str, year: Optional[int] = None) -> Optional[Path]:
        """
        Download DVF data for a specific department

        Args:
            department: Department code (e.g., "13", "83")
            year: Specific year to download, or None for latest

        Returns:
            Path to downloaded file
        """
        if year is None:
            year = datetime.now().year - 1  # Previous year is usually complete

        # DVF data URL pattern from data.gouv.fr
        url = f"https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/departements/{department}.csv.gz"

        save_path = self.data_dir / f"dvf_{department}_{year}.csv"

        if save_path.exists():
            logger.info(f"DVF data already exists: {save_path}")
            return save_path

        try:
            logger.info(f"Downloading DVF data for department {department}, year {year}...")
            response = self.session.get(url, stream=True, timeout=60)
            response.raise_for_status()

            # Decompress and save
            gz_path = self.data_dir / f"dvf_{department}_{year}.csv.gz"
            with open(gz_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Decompress
            with gzip.open(gz_path, 'rt', encoding='utf-8') as gz_file:
                with open(save_path, 'w', encoding='utf-8') as out_file:
                    out_file.write(gz_file.read())

            # Remove compressed file
            gz_path.unlink()

            logger.info(f"DVF data saved to {save_path}")
            return save_path

        except Exception as e:
            logger.error(f"Error downloading DVF data: {e}")
            return None

    def download_all_departments(self, years: int = 3) -> List[Path]:
        """
        Download DVF data for all monitored departments

        Args:
            years: Number of years to download

        Returns:
            List of downloaded file paths
        """
        current_year = datetime.now().year
        downloaded = []

        for dept in DEPARTMENTS:
            for year in range(current_year - years, current_year):
                path = self.download_department_data(dept, year)
                if path:
                    downloaded.append(path)

        return downloaded

    def load_data(self, department: str, year: Optional[int] = None) -> List[DVFTransaction]:
        """
        Load DVF data for a department

        Args:
            department: Department code
            year: Specific year, or None for all available

        Returns:
            List of DVFTransaction objects
        """
        cache_key = f"{department}_{year or 'all'}"
        if cache_key in self._data_cache:
            return self._data_cache[cache_key]

        transactions = []

        # Find matching files
        pattern = f"dvf_{department}_*.csv" if year is None else f"dvf_{department}_{year}.csv"
        files = list(self.data_dir.glob(pattern))

        for file_path in files:
            transactions.extend(self._parse_csv_file(file_path))

        self._data_cache[cache_key] = transactions
        logger.info(f"Loaded {len(transactions)} transactions for department {department}")
        return transactions

    def _parse_csv_file(self, file_path: Path) -> List[DVFTransaction]:
        """Parse a DVF CSV file"""
        transactions = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    try:
                        transaction = self._row_to_transaction(row)
                        if transaction:
                            transactions.append(transaction)
                    except Exception as e:
                        continue  # Skip malformed rows

        except Exception as e:
            logger.error(f"Error parsing DVF file {file_path}: {e}")

        return transactions

    def _row_to_transaction(self, row: Dict[str, str]) -> Optional[DVFTransaction]:
        """Convert a CSV row to DVFTransaction"""
        try:
            # Parse date
            date_str = row.get("date_mutation", "")
            date_mutation = None
            if date_str:
                try:
                    date_mutation = datetime.strptime(date_str, "%Y-%m-%d").date()
                except:
                    pass

            # Parse price
            valeur_str = row.get("valeur_fonciere", "").replace(",", ".")
            valeur = float(valeur_str) if valeur_str else 0.0

            # Parse surface
            surface_str = row.get("surface_reelle_bati", "").replace(",", ".")
            surface = float(surface_str) if surface_str else None

            # Parse pieces
            pieces_str = row.get("nombre_pieces_principales", "")
            pieces = int(pieces_str) if pieces_str.isdigit() else None

            # Build address
            numero = row.get("no_voie", "")
            voie = row.get("voie", "")
            adresse = f"{numero} {voie}".strip()

            # Coordinates
            lat_str = row.get("latitude", "")
            lon_str = row.get("longitude", "")
            lat = float(lat_str) if lat_str else None
            lon = float(lon_str) if lon_str else None

            # Calculate price per m²
            prix_m2 = None
            if surface and surface > 0 and valeur > 0:
                prix_m2 = valeur / surface

            return DVFTransaction(
                date_mutation=date_mutation,
                nature_mutation=row.get("nature_mutation", ""),
                valeur_fonciere=valeur,
                adresse=adresse,
                code_postal=row.get("code_postal", ""),
                commune=row.get("commune", ""),
                type_local=row.get("type_local", ""),
                surface_reelle=surface,
                nombre_pieces=pieces,
                latitude=lat,
                longitude=lon,
                prix_m2=prix_m2,
            )
        except Exception as e:
            return None

    def search(self, params: DVFSearchParams) -> List[DVFTransaction]:
        """
        Search DVF data with filters

        Args:
            params: Search parameters

        Returns:
            List of matching transactions
        """
        # Determine which data to load
        if params.department:
            all_data = self.load_data(params.department)
        elif params.code_postal:
            dept = params.code_postal[:2]
            all_data = self.load_data(dept)
        else:
            # Load all departments
            all_data = []
            for dept in DEPARTMENTS:
                all_data.extend(self.load_data(dept))

        # Filter
        results = []
        for t in all_data:
            if self._matches_criteria(t, params):
                results.append(t)

        return results

    def _matches_criteria(self, t: DVFTransaction, params: DVFSearchParams) -> bool:
        """Check if transaction matches search criteria"""
        if params.code_postal and t.code_postal != params.code_postal:
            return False

        if params.commune and params.commune.lower() not in t.commune.lower():
            return False

        if params.type_local and params.type_local.lower() not in t.type_local.lower():
            return False

        if params.date_min and t.date_mutation and t.date_mutation < params.date_min:
            return False

        if params.date_max and t.date_mutation and t.date_mutation > params.date_max:
            return False

        if params.prix_min and t.valeur_fonciere < params.prix_min:
            return False

        if params.prix_max and t.valeur_fonciere > params.prix_max:
            return False

        if params.surface_min and t.surface_reelle and t.surface_reelle < params.surface_min:
            return False

        if params.surface_max and t.surface_reelle and t.surface_reelle > params.surface_max:
            return False

        return True

    def get_price_per_m2_stats(
        self,
        code_postal: str,
        type_local: str = "Appartement",
        months: int = 24
    ) -> Dict[str, float]:
        """
        Get price per m² statistics for a postal code

        Args:
            code_postal: Postal code
            type_local: Property type
            months: Number of months to consider

        Returns:
            Dictionary with statistics
        """
        from datetime import timedelta

        date_min = date.today() - timedelta(days=months * 30)

        params = DVFSearchParams(
            code_postal=code_postal,
            type_local=type_local,
            date_min=date_min,
        )

        transactions = self.search(params)

        # Calculate stats
        prices_m2 = [t.prix_m2 for t in transactions if t.prix_m2 and t.prix_m2 > 0]

        if not prices_m2:
            return {
                "count": 0,
                "mean": None,
                "median": None,
                "min": None,
                "max": None,
            }

        prices_m2.sort()
        count = len(prices_m2)
        mean = sum(prices_m2) / count
        median = prices_m2[count // 2] if count % 2 else (prices_m2[count // 2 - 1] + prices_m2[count // 2]) / 2

        return {
            "count": count,
            "mean": round(mean, 2),
            "median": round(median, 2),
            "min": round(min(prices_m2), 2),
            "max": round(max(prices_m2), 2),
        }

    def find_comparable_sales(
        self,
        code_postal: str,
        surface: float,
        type_local: str = "Appartement",
        tolerance_percent: float = 20,
        months: int = 24,
        limit: int = 10
    ) -> List[DVFTransaction]:
        """
        Find comparable sales for a property

        Args:
            code_postal: Postal code
            surface: Property surface in m²
            type_local: Property type
            tolerance_percent: Surface tolerance percentage
            months: Number of months to look back
            limit: Maximum results

        Returns:
            List of comparable transactions
        """
        from datetime import timedelta

        date_min = date.today() - timedelta(days=months * 30)
        surface_min = surface * (1 - tolerance_percent / 100)
        surface_max = surface * (1 + tolerance_percent / 100)

        params = DVFSearchParams(
            code_postal=code_postal,
            type_local=type_local,
            date_min=date_min,
            surface_min=surface_min,
            surface_max=surface_max,
        )

        transactions = self.search(params)

        # Sort by date (most recent first) and limit
        transactions.sort(key=lambda t: t.date_mutation or date.min, reverse=True)
        return transactions[:limit]
