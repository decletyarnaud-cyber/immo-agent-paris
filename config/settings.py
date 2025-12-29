"""
Configuration settings for Immo-Agent Paris
"""
from pathlib import Path
import os

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
LAWYERS_DIR = DATA_DIR / "lawyers"
EXPORTS_DIR = DATA_DIR / "exports"

# Database
DATABASE_PATH = DATA_DIR / "immo_agent.db"

# Geographic scope - Paris et petite couronne
DEPARTMENTS = ["75", "92", "93", "94"]  # Paris, Hauts-de-Seine, Seine-Saint-Denis, Val-de-Marne

CITIES = {
    # Paris (75)
    "paris": {
        "codes_postaux": [f"750{i:02d}" for i in range(1, 21)],
        "department": "75"
    },
    # Hauts-de-Seine (92)
    "boulogne-billancourt": {"codes_postaux": ["92100"], "department": "92"},
    "nanterre": {"codes_postaux": ["92000"], "department": "92"},
    "courbevoie": {"codes_postaux": ["92400"], "department": "92"},
    "colombes": {"codes_postaux": ["92700"], "department": "92"},
    "asnieres-sur-seine": {"codes_postaux": ["92600"], "department": "92"},
    "rueil-malmaison": {"codes_postaux": ["92500"], "department": "92"},
    "levallois-perret": {"codes_postaux": ["92300"], "department": "92"},
    "issy-les-moulineaux": {"codes_postaux": ["92130"], "department": "92"},
    "neuilly-sur-seine": {"codes_postaux": ["92200"], "department": "92"},
    "antony": {"codes_postaux": ["92160"], "department": "92"},
    "clamart": {"codes_postaux": ["92140"], "department": "92"},
    "montrouge": {"codes_postaux": ["92120"], "department": "92"},
    "meudon": {"codes_postaux": ["92190", "92360"], "department": "92"},
    "suresnes": {"codes_postaux": ["92150"], "department": "92"},
    "puteaux": {"codes_postaux": ["92800"], "department": "92"},
    "gennevilliers": {"codes_postaux": ["92230"], "department": "92"},
    "clichy": {"codes_postaux": ["92110"], "department": "92"},
    "malakoff": {"codes_postaux": ["92240"], "department": "92"},
    "vanves": {"codes_postaux": ["92170"], "department": "92"},
    "chatillon": {"codes_postaux": ["92320"], "department": "92"},
    # Seine-Saint-Denis (93)
    "saint-denis": {"codes_postaux": ["93200", "93210"], "department": "93"},
    "montreuil": {"codes_postaux": ["93100"], "department": "93"},
    "aubervilliers": {"codes_postaux": ["93300"], "department": "93"},
    "aulnay-sous-bois": {"codes_postaux": ["93600"], "department": "93"},
    "drancy": {"codes_postaux": ["93700"], "department": "93"},
    "noisy-le-grand": {"codes_postaux": ["93160"], "department": "93"},
    "pantin": {"codes_postaux": ["93500"], "department": "93"},
    "bondy": {"codes_postaux": ["93140"], "department": "93"},
    "epinay-sur-seine": {"codes_postaux": ["93800"], "department": "93"},
    "sevran": {"codes_postaux": ["93270"], "department": "93"},
    "le-blanc-mesnil": {"codes_postaux": ["93150"], "department": "93"},
    "bobigny": {"codes_postaux": ["93000"], "department": "93"},
    "saint-ouen": {"codes_postaux": ["93400"], "department": "93"},
    "rosny-sous-bois": {"codes_postaux": ["93110"], "department": "93"},
    "livry-gargan": {"codes_postaux": ["93190"], "department": "93"},
    "la-courneuve": {"codes_postaux": ["93120"], "department": "93"},
    "bagnolet": {"codes_postaux": ["93170"], "department": "93"},
    "le-pre-saint-gervais": {"codes_postaux": ["93310"], "department": "93"},
    "les-lilas": {"codes_postaux": ["93260"], "department": "93"},
    # Val-de-Marne (94)
    "creteil": {"codes_postaux": ["94000"], "department": "94"},
    "vitry-sur-seine": {"codes_postaux": ["94400"], "department": "94"},
    "saint-maur-des-fosses": {"codes_postaux": ["94100", "94210"], "department": "94"},
    "champigny-sur-marne": {"codes_postaux": ["94500"], "department": "94"},
    "ivry-sur-seine": {"codes_postaux": ["94200"], "department": "94"},
    "maisons-alfort": {"codes_postaux": ["94700"], "department": "94"},
    "fontenay-sous-bois": {"codes_postaux": ["94120"], "department": "94"},
    "villejuif": {"codes_postaux": ["94800"], "department": "94"},
    "vincennes": {"codes_postaux": ["94300"], "department": "94"},
    "alfortville": {"codes_postaux": ["94140"], "department": "94"},
    "choisy-le-roi": {"codes_postaux": ["94600"], "department": "94"},
    "le-kremlin-bicetre": {"codes_postaux": ["94270"], "department": "94"},
    "cachan": {"codes_postaux": ["94230"], "department": "94"},
    "charenton-le-pont": {"codes_postaux": ["94220"], "department": "94"},
    "nogent-sur-marne": {"codes_postaux": ["94130"], "department": "94"},
    "joinville-le-pont": {"codes_postaux": ["94340"], "department": "94"},
    "saint-mande": {"codes_postaux": ["94160"], "department": "94"},
    "thiais": {"codes_postaux": ["94320"], "department": "94"},
    "orly": {"codes_postaux": ["94310"], "department": "94"},
}

# All postal codes to monitor
ALL_POSTAL_CODES = []
for city_data in CITIES.values():
    ALL_POSTAL_CODES.extend(city_data["codes_postaux"])

# Sources configuration
SOURCES = {
    "licitor": {
        "base_url": "https://www.licitor.com",
        "search_url": "https://www.licitor.com/ventes-judiciaires-immobilieres",
        "enabled": True,
        "priority": 1
    },
    "encheres_publiques": {
        "base_url": "https://www.encheres-publiques.com",
        "search_url": "https://www.encheres-publiques.com/ventes/immobilier",
        "enabled": True,
        "priority": 2
    },
    "vench": {
        "base_url": "https://www.vench.fr",
        "search_url": "https://www.vench.fr/liste-des-ventes-au-tribunal-judiciaire-paris.html",
        "enabled": True,
        "priority": 3
    }
}

# Tribunaux
TRIBUNAUX = {
    "tj_paris": {
        "nom": "Tribunal Judiciaire de Paris",
        "ville": "Paris",
        "department": "75"
    },
    "tj_bobigny": {
        "nom": "Tribunal Judiciaire de Bobigny",
        "ville": "Bobigny",
        "department": "93"
    },
    "tj_nanterre": {
        "nom": "Tribunal Judiciaire de Nanterre",
        "ville": "Nanterre",
        "department": "92"
    },
    "tj_creteil": {
        "nom": "Tribunal Judiciaire de Créteil",
        "ville": "Créteil",
        "department": "94"
    }
}

# Scraping settings
SCRAPING = {
    "delay_between_requests": 1.5,  # seconds
    "max_retries": 3,
    "timeout": 30,
    "user_agent": "ImmoAgent/1.0 (Contact: immo-agent@example.com)"
}

# DVF API settings
DVF = {
    "base_url": "https://api.cquest.org/dvf",
    "data_gouv_url": "https://files.data.gouv.fr/geo-dvf/latest/csv",
    "years_to_fetch": 5
}

# Analysis settings
ANALYSIS = {
    "good_deal_threshold": 0.20,  # 20% below market
    "opportunity_threshold": 0.30,  # 30% below market
    "comparison_radius_km": 1.0  # Compare with sales within 1km
}

# Streamlit settings
WEB = {
    "host": "localhost",
    "port": 8502,  # Different port from Marseille
    "title": "Immo-Agent - Enchères Judiciaires Paris & Petite Couronne"
}
