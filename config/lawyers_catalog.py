"""
Catalogue des sites d'avocats avec pages d'enchères immobilières
Région Paris / Petite Couronne (75, 92, 93, 94)
"""

# Format: clé = nom normalisé pour matching, valeur = infos du cabinet
LAWYERS_CATALOG = {
    # Paris - à compléter avec les cabinets locaux
    # Les avocats parisiens seront ajoutés au fur et à mesure du scraping
}


def find_lawyer_info(avocat_nom: str = None, cabinet: str = None) -> dict:
    """
    Trouve les infos d'un avocat/cabinet dans le catalogue

    Args:
        avocat_nom: Nom de l'avocat (ex: "Philippe Cornet")
        cabinet: Nom du cabinet (ex: "SELARL Mascaron Avocats")

    Returns:
        Dict avec infos du cabinet ou None
    """
    if not avocat_nom and not cabinet:
        return None

    search_text = f"{avocat_nom or ''} {cabinet or ''}".lower()

    for key, info in LAWYERS_CATALOG.items():
        # Match par clé
        if key in search_text:
            return info

        # Match par nom de cabinet
        if info.get("cabinet") and info["cabinet"].lower() in search_text:
            return info

        # Match par nom d'avocat
        for avocat in info.get("avocats", []):
            if avocat.lower() in search_text:
                return info

    return None


def get_encheres_url(avocat_nom: str = None, cabinet: str = None) -> str:
    """
    Retourne l'URL de la page enchères du cabinet si connue
    """
    info = find_lawyer_info(avocat_nom, cabinet)
    if info:
        return info.get("page_encheres") or info.get("site")
    return None


def get_all_encheres_pages() -> list:
    """
    Retourne toutes les pages d'enchères connues pour scraping
    """
    pages = []
    for key, info in LAWYERS_CATALOG.items():
        if info.get("page_encheres"):
            pages.append({
                "cabinet": info["cabinet"],
                "url": info["page_encheres"],
                "ville": info.get("ville"),
            })
    return pages
