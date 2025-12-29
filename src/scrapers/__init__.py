"""
Scrapers for various auction sources
"""
from .base_scraper import BaseScraper
from .licitor import LicitorScraper
from .encheres_publiques import EncherePubliquesScraper
from .vench import VenchScraper
from .lawyer_sites import LawyerSiteScraper, EmailTemplateGenerator

__all__ = [
    "BaseScraper",
    "LicitorScraper",
    "EncherePubliquesScraper",
    "VenchScraper",
    "LawyerSiteScraper",
    "EmailTemplateGenerator",
]
