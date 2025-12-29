"""
Data models for Immo-Agent
"""
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List
from enum import Enum


class PropertyType(Enum):
    APPARTEMENT = "appartement"
    MAISON = "maison"
    LOCAL_COMMERCIAL = "local_commercial"
    TERRAIN = "terrain"
    PARKING = "parking"
    AUTRE = "autre"


class AuctionStatus(Enum):
    A_VENIR = "a_venir"
    EN_COURS = "en_cours"
    ADJUGE = "adjuge"
    ANNULE = "annule"


class PVStatus(Enum):
    DISPONIBLE = "disponible"
    A_TELECHARGER = "a_telecharger"
    A_DEMANDER = "a_demander"
    NON_DISPONIBLE = "non_disponible"


@dataclass
class Lawyer:
    """Cabinet d'avocat"""
    id: Optional[int] = None
    nom: str = ""
    cabinet: str = ""
    adresse: str = ""
    telephone: str = ""
    email: str = ""
    site_web: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class Auction:
    """Vente aux enchères judiciaires"""
    id: Optional[int] = None

    # Identification
    source: str = ""  # licitor, encheres_publiques, vench
    source_id: str = ""  # ID unique sur la source
    url: str = ""

    # Localisation
    adresse: str = ""
    code_postal: str = ""
    ville: str = ""
    department: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Description du bien
    type_bien: PropertyType = PropertyType.AUTRE
    surface: Optional[float] = None  # m²
    nb_pieces: Optional[int] = None
    nb_chambres: Optional[int] = None
    etage: Optional[int] = None
    description: str = ""
    description_detaillee: str = ""  # Description enrichie (composition par étage, etc.)
    occupation: str = ""  # "Libre", "Occupé", etc.
    cadastre: str = ""  # Référence cadastrale

    # Photos et documents
    photos: List[str] = field(default_factory=list)  # URLs des photos
    documents: List[dict] = field(default_factory=list)  # [{nom, url, type}, ...]

    # Dates importantes
    date_vente: Optional[date] = None
    heure_vente: Optional[str] = None
    dates_visite: List[datetime] = field(default_factory=list)
    date_jugement: Optional[date] = None

    # Prix
    mise_a_prix: Optional[float] = None
    prix_adjudication: Optional[float] = None  # Si déjà vendu

    # Tribunal et avocat
    tribunal: str = ""
    lawyer_id: Optional[int] = None
    avocat_nom: Optional[str] = None
    avocat_cabinet: Optional[str] = None
    avocat_adresse: Optional[str] = None
    avocat_telephone: Optional[str] = None
    avocat_email: Optional[str] = None
    avocat_site_web: Optional[str] = None

    # Procès-verbal
    pv_status: PVStatus = PVStatus.NON_DISPONIBLE
    pv_url: Optional[str] = None
    pv_local_path: Optional[str] = None

    # Analyse
    prix_marche_estime: Optional[float] = None
    prix_m2_marche: Optional[float] = None
    decote_pourcentage: Optional[float] = None
    score_opportunite: Optional[float] = None

    # Métadonnées
    status: AuctionStatus = AuctionStatus.A_VENIR
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            "id": self.id,
            "source": self.source,
            "source_id": self.source_id,
            "url": self.url,
            "adresse": self.adresse,
            "code_postal": self.code_postal,
            "ville": self.ville,
            "department": self.department,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "type_bien": self.type_bien.value,
            "surface": self.surface,
            "nb_pieces": self.nb_pieces,
            "nb_chambres": self.nb_chambres,
            "etage": self.etage,
            "description": self.description,
            "description_detaillee": self.description_detaillee,
            "occupation": self.occupation,
            "cadastre": self.cadastre,
            "photos": self.photos,
            "documents": self.documents,
            "date_vente": self.date_vente.isoformat() if self.date_vente else None,
            "heure_vente": self.heure_vente,
            "dates_visite": [d.isoformat() for d in self.dates_visite],
            "date_jugement": self.date_jugement.isoformat() if self.date_jugement else None,
            "mise_a_prix": self.mise_a_prix,
            "prix_adjudication": self.prix_adjudication,
            "tribunal": self.tribunal,
            "lawyer_id": self.lawyer_id,
            "avocat_nom": self.avocat_nom,
            "avocat_cabinet": self.avocat_cabinet,
            "avocat_adresse": self.avocat_adresse,
            "avocat_telephone": self.avocat_telephone,
            "avocat_email": self.avocat_email,
            "avocat_site_web": self.avocat_site_web,
            "pv_status": self.pv_status.value,
            "pv_url": self.pv_url,
            "pv_local_path": self.pv_local_path,
            "prix_marche_estime": self.prix_marche_estime,
            "prix_m2_marche": self.prix_m2_marche,
            "decote_pourcentage": self.decote_pourcentage,
            "score_opportunite": self.score_opportunite,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class DVFTransaction:
    """Transaction immobilière DVF"""
    id: Optional[int] = None
    date_mutation: date = None
    nature_mutation: str = ""  # Vente, etc.
    valeur_fonciere: float = 0.0
    adresse: str = ""
    code_postal: str = ""
    commune: str = ""
    type_local: str = ""
    surface_reelle: Optional[float] = None
    nombre_pieces: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    prix_m2: Optional[float] = None


@dataclass
class AnalysisReport:
    """Rapport d'analyse d'une enchère"""
    auction_id: int
    date_analyse: datetime = field(default_factory=datetime.now)

    # Comparaison marché
    transactions_comparables: List[DVFTransaction] = field(default_factory=list)
    prix_m2_moyen_secteur: Optional[float] = None
    prix_estime: Optional[float] = None

    # Score
    decote: Optional[float] = None  # en %
    score: Optional[float] = None  # 0-100
    recommandation: str = ""  # "Bonne affaire", "Opportunité", "Prix marché", "Surévalué"

    # Détails
    points_forts: List[str] = field(default_factory=list)
    points_vigilance: List[str] = field(default_factory=list)
