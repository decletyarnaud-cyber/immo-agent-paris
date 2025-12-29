"""
CSV export and import handler
"""
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import EXPORTS_DIR
from src.storage.models import Auction, PropertyType


class CSVHandler:
    """Handle CSV export and import of auction data"""

    # Column definitions for export
    COLUMNS = [
        "id",
        "source",
        "url",
        "adresse",
        "code_postal",
        "ville",
        "type_bien",
        "surface_m2",
        "nb_pieces",
        "nb_chambres",
        "etage",
        "date_vente",
        "heure_vente",
        "dates_visite",
        "mise_a_prix_euros",
        "tribunal",
        "avocat",
        "pv_disponible",
        "pv_url",
        "prix_marche_estime",
        "prix_m2_marche",
        "decote_pourcent",
        "score_opportunite",
        "recommandation",
        "description",
    ]

    def __init__(self, export_dir: Optional[Path] = None):
        self.export_dir = export_dir or EXPORTS_DIR
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_auctions(
        self,
        auctions: List[Auction],
        filename: Optional[str] = None,
        include_all_columns: bool = True,
    ) -> Path:
        """
        Export auctions to CSV

        Args:
            auctions: List of auctions to export
            filename: Optional filename (default: auctions_YYYYMMDD.csv)
            include_all_columns: Include all columns or just essential ones

        Returns:
            Path to exported file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"encheres_{timestamp}.csv"

        filepath = self.export_dir / filename

        columns = self.COLUMNS if include_all_columns else self.COLUMNS[:15]

        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()

            for auction in auctions:
                row = self._auction_to_row(auction)
                writer.writerow(row)

        logger.info(f"Exported {len(auctions)} auctions to {filepath}")
        return filepath

    def _auction_to_row(self, auction: Auction) -> Dict[str, Any]:
        """Convert auction to CSV row"""
        # Get recommendation from score
        recommendation = "À analyser"
        if auction.decote_pourcentage is not None:
            if auction.decote_pourcentage >= 40:
                recommendation = "Opportunité exceptionnelle"
            elif auction.decote_pourcentage >= 30:
                recommendation = "Opportunité"
            elif auction.decote_pourcentage >= 20:
                recommendation = "Bonne affaire"
            elif auction.decote_pourcentage >= 0:
                recommendation = "Prix marché"
            else:
                recommendation = "Surévalué"

        return {
            "id": auction.id or "",
            "source": auction.source,
            "url": auction.url,
            "adresse": auction.adresse,
            "code_postal": auction.code_postal,
            "ville": auction.ville,
            "type_bien": auction.type_bien.value if auction.type_bien else "",
            "surface_m2": auction.surface or "",
            "nb_pieces": auction.nb_pieces or "",
            "nb_chambres": auction.nb_chambres or "",
            "etage": auction.etage or "",
            "date_vente": auction.date_vente.strftime("%d/%m/%Y") if auction.date_vente else "",
            "heure_vente": auction.heure_vente or "",
            "dates_visite": "; ".join(
                d.strftime("%d/%m/%Y %H:%M") for d in auction.dates_visite
            ) if auction.dates_visite else "",
            "mise_a_prix_euros": f"{auction.mise_a_prix:.0f}" if auction.mise_a_prix else "",
            "tribunal": auction.tribunal,
            "avocat": "",  # TODO: Get from lawyer_id
            "pv_disponible": "Oui" if auction.pv_url else "Non",
            "pv_url": auction.pv_url or "",
            "prix_marche_estime": f"{auction.prix_marche_estime:.0f}" if auction.prix_marche_estime else "",
            "prix_m2_marche": f"{auction.prix_m2_marche:.0f}" if auction.prix_m2_marche else "",
            "decote_pourcent": f"{auction.decote_pourcentage:.1f}" if auction.decote_pourcentage else "",
            "score_opportunite": f"{auction.score_opportunite:.0f}" if auction.score_opportunite else "",
            "recommandation": recommendation,
            "description": (auction.description or "")[:500],
        }

    def export_opportunities(
        self,
        auctions: List[Auction],
        min_score: float = 50,
    ) -> Path:
        """
        Export only opportunities (high score auctions)

        Args:
            auctions: All auctions
            min_score: Minimum score to include

        Returns:
            Path to exported file
        """
        opportunities = [a for a in auctions if (a.score_opportunite or 0) >= min_score]
        opportunities.sort(key=lambda x: x.score_opportunite or 0, reverse=True)

        filename = f"opportunites_{datetime.now().strftime('%Y%m%d')}.csv"
        return self.export_auctions(opportunities, filename)

    def export_by_city(self, auctions: List[Auction]) -> List[Path]:
        """
        Export auctions grouped by city

        Args:
            auctions: List of auctions

        Returns:
            List of exported file paths
        """
        # Group by city
        by_city: Dict[str, List[Auction]] = {}
        for auction in auctions:
            city = auction.ville or "Inconnu"
            if city not in by_city:
                by_city[city] = []
            by_city[city].append(auction)

        # Export each city
        paths = []
        date_str = datetime.now().strftime("%Y%m%d")

        for city, city_auctions in by_city.items():
            filename = f"encheres_{city.lower().replace(' ', '_')}_{date_str}.csv"
            path = self.export_auctions(city_auctions, filename)
            paths.append(path)

        return paths

    def export_summary(self, auctions: List[Auction]) -> Path:
        """
        Export a summary CSV with key metrics

        Args:
            auctions: List of auctions

        Returns:
            Path to summary file
        """
        filename = f"resume_{datetime.now().strftime('%Y%m%d')}.csv"
        filepath = self.export_dir / filename

        # Calculate summary stats
        summary_data = []

        # By city
        cities = set(a.ville for a in auctions if a.ville)
        for city in cities:
            city_auctions = [a for a in auctions if a.ville == city]
            prices = [a.mise_a_prix for a in city_auctions if a.mise_a_prix]
            scores = [a.score_opportunite for a in city_auctions if a.score_opportunite]

            summary_data.append({
                "ville": city,
                "nombre_encheres": len(city_auctions),
                "prix_moyen": f"{sum(prices)/len(prices):.0f}" if prices else "",
                "prix_min": f"{min(prices):.0f}" if prices else "",
                "prix_max": f"{max(prices):.0f}" if prices else "",
                "score_moyen": f"{sum(scores)/len(scores):.1f}" if scores else "",
                "opportunites": len([a for a in city_auctions if (a.score_opportunite or 0) >= 50]),
            })

        # Sort by number of auctions
        summary_data.sort(key=lambda x: x["nombre_encheres"], reverse=True)

        # Write
        columns = ["ville", "nombre_encheres", "prix_moyen", "prix_min", "prix_max", "score_moyen", "opportunites"]

        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(summary_data)

        logger.info(f"Exported summary to {filepath}")
        return filepath

    def list_exports(self) -> List[Dict[str, Any]]:
        """List all exported files"""
        exports = []

        for file in self.export_dir.glob("*.csv"):
            stats = file.stat()
            exports.append({
                "filename": file.name,
                "path": str(file),
                "size_kb": stats.st_size / 1024,
                "created": datetime.fromtimestamp(stats.st_ctime),
                "modified": datetime.fromtimestamp(stats.st_mtime),
            })

        # Sort by date (most recent first)
        exports.sort(key=lambda x: x["modified"], reverse=True)
        return exports
