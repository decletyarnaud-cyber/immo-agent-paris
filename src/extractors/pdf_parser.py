"""
PDF parsing and text extraction module
"""
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from loguru import logger

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


@dataclass
class ExtractedPVData:
    """Data extracted from a PV (procès-verbal) document"""
    # Basic info
    raw_text: str = ""
    page_count: int = 0

    # Property details
    adresse: str = ""
    code_postal: str = ""
    ville: str = ""
    type_bien: str = ""
    surface: Optional[float] = None
    nb_pieces: Optional[int] = None
    nb_chambres: Optional[int] = None
    etage: Optional[int] = None

    # Copropriété
    is_copropriete: bool = False
    lot_number: str = ""
    charges_copropriete: Optional[float] = None
    tantiemes: Optional[int] = None

    # État
    etat_occupation: str = ""  # libre, occupé, loué
    locataire_info: str = ""
    loyer_mensuel: Optional[float] = None

    # Financier
    mise_a_prix: Optional[float] = None
    frais_previsionnels: Optional[float] = None
    montant_creance: Optional[float] = None

    # Dates
    date_vente: str = ""
    dates_visite: List[str] = field(default_factory=list)

    # Legal
    tribunal: str = ""
    avocat: str = ""
    numero_rg: str = ""  # Numéro RG du dossier

    # Description
    description_bien: str = ""
    diagnostics: List[str] = field(default_factory=list)


class PDFParser:
    """Parse PDF documents and extract structured data"""

    def __init__(self):
        self.preferred_library = "pdfplumber" if HAS_PDFPLUMBER else ("pymupdf" if HAS_PYMUPDF else None)
        if not self.preferred_library:
            logger.warning("No PDF library available. Install pdfplumber or PyMuPDF.")

    def extract_text(self, pdf_path: str) -> str:
        """Extract all text from PDF"""
        if not Path(pdf_path).exists():
            logger.error(f"PDF file not found: {pdf_path}")
            return ""

        if self.preferred_library == "pdfplumber":
            return self._extract_with_pdfplumber(pdf_path)
        elif self.preferred_library == "pymupdf":
            return self._extract_with_pymupdf(pdf_path)
        else:
            return ""

    def _extract_with_pdfplumber(self, pdf_path: str) -> str:
        """Extract text using pdfplumber"""
        text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            logger.error(f"Error extracting text with pdfplumber: {e}")
        return text

    def _extract_with_pymupdf(self, pdf_path: str) -> str:
        """Extract text using PyMuPDF"""
        text = ""
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                text += page.get_text() + "\n"
            doc.close()
        except Exception as e:
            logger.error(f"Error extracting text with PyMuPDF: {e}")
        return text

    def get_page_count(self, pdf_path: str) -> int:
        """Get number of pages in PDF"""
        if self.preferred_library == "pdfplumber" and HAS_PDFPLUMBER:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    return len(pdf.pages)
            except:
                pass
        elif self.preferred_library == "pymupdf" and HAS_PYMUPDF:
            try:
                doc = fitz.open(pdf_path)
                count = len(doc)
                doc.close()
                return count
            except:
                pass
        return 0

    def is_image_pdf(self, pdf_path: str) -> bool:
        """Check if PDF is primarily image-based (needs OCR)"""
        text = self.extract_text(pdf_path)
        # If very little text extracted, likely an image PDF
        return len(text.strip()) < 100

    def parse_pv(self, pdf_path: str) -> ExtractedPVData:
        """Parse a PV document and extract structured data"""
        data = ExtractedPVData()

        text = self.extract_text(pdf_path)
        if not text:
            return data

        data.raw_text = text
        data.page_count = self.get_page_count(pdf_path)

        # Parse different sections
        self._extract_address(text, data)
        self._extract_property_details(text, data)
        self._extract_copropriete_info(text, data)
        self._extract_occupation_status(text, data)
        self._extract_financial_info(text, data)
        self._extract_dates(text, data)
        self._extract_legal_info(text, data)
        self._extract_description(text, data)

        return data

    def _extract_address(self, text: str, data: ExtractedPVData):
        """Extract address information"""
        # Look for address patterns
        patterns = [
            r"(?:situé|sis|se trouvant)\s+(?:au|à)\s+(.+?)(?:\s*\d{5})",
            r"(?:adresse|localisation)\s*:?\s*(.+?)(?:\s*\d{5})",
            r"(\d+[,\s]+(?:rue|avenue|boulevard|chemin|allée|impasse|place)[^,\n]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data.adresse = match.group(1).strip()
                break

        # Postal code
        cp_match = re.search(r"\b(13\d{3}|83\d{3})\b", text)
        if cp_match:
            data.code_postal = cp_match.group(1)

        # City
        city_match = re.search(
            r"(?:13\d{3}|83\d{3})\s+([A-ZÀ-Ü][a-zà-ü\-]+(?:\s+[A-ZÀ-Ü]?[a-zà-ü\-]+)*)",
            text
        )
        if city_match:
            data.ville = city_match.group(1)

    def _extract_property_details(self, text: str, data: ExtractedPVData):
        """Extract property type, surface, rooms"""
        text_lower = text.lower()

        # Type
        if "appartement" in text_lower or "studio" in text_lower:
            data.type_bien = "appartement"
        elif "maison" in text_lower or "villa" in text_lower:
            data.type_bien = "maison"
        elif "local" in text_lower and "commercial" in text_lower:
            data.type_bien = "local_commercial"
        elif "terrain" in text_lower:
            data.type_bien = "terrain"
        elif "parking" in text_lower or "garage" in text_lower:
            data.type_bien = "parking"

        # Surface
        surface_patterns = [
            r"surface\s+(?:habitable|totale)?\s*(?:de\s+)?(\d+(?:[.,]\d+)?)\s*m[²2]",
            r"(\d+(?:[.,]\d+)?)\s*m[²2]\s+(?:environ|de surface)",
            r"d'une\s+surface\s+de\s+(\d+(?:[.,]\d+)?)\s*m[²2]",
        ]
        for pattern in surface_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data.surface = float(match.group(1).replace(",", "."))
                break

        # Rooms
        pieces_match = re.search(r"(\d+)\s*pièces?\s*(?:principales?)?", text, re.IGNORECASE)
        if pieces_match:
            data.nb_pieces = int(pieces_match.group(1))

        chambres_match = re.search(r"(\d+)\s*chambres?", text, re.IGNORECASE)
        if chambres_match:
            data.nb_chambres = int(chambres_match.group(1))

        # Floor
        etage_match = re.search(r"(?:au\s+)?(\d+)(?:e|ème|er)?\s*étage", text, re.IGNORECASE)
        if etage_match:
            data.etage = int(etage_match.group(1))

    def _extract_copropriete_info(self, text: str, data: ExtractedPVData):
        """Extract copropriété information"""
        if "copropriété" in text.lower():
            data.is_copropriete = True

            # Lot number
            lot_match = re.search(r"lot\s*n?°?\s*(\d+)", text, re.IGNORECASE)
            if lot_match:
                data.lot_number = lot_match.group(1)

            # Charges
            charges_match = re.search(
                r"charges\s+(?:annuelles|de copropriété)?\s*:?\s*([\d\s,\.]+)\s*€",
                text, re.IGNORECASE
            )
            if charges_match:
                data.charges_copropriete = self._parse_price(charges_match.group(1))

            # Tantièmes
            tantiemes_match = re.search(r"(\d+)\s*/?\s*(?:\d+)?\s*tantièmes?", text, re.IGNORECASE)
            if tantiemes_match:
                data.tantiemes = int(tantiemes_match.group(1))

    def _extract_occupation_status(self, text: str, data: ExtractedPVData):
        """Extract occupation status"""
        text_lower = text.lower()

        if "libre" in text_lower and "occupation" in text_lower:
            data.etat_occupation = "libre"
        elif "occupé" in text_lower or "loué" in text_lower:
            data.etat_occupation = "occupé"

            # Try to get tenant info
            locataire_match = re.search(
                r"(?:locataire|occupant)\s*:?\s*([^\n]+)",
                text, re.IGNORECASE
            )
            if locataire_match:
                data.locataire_info = locataire_match.group(1).strip()

            # Rent
            loyer_match = re.search(
                r"loyer\s+(?:mensuel)?\s*:?\s*([\d\s,\.]+)\s*€",
                text, re.IGNORECASE
            )
            if loyer_match:
                data.loyer_mensuel = self._parse_price(loyer_match.group(1))

    def _extract_financial_info(self, text: str, data: ExtractedPVData):
        """Extract financial information"""
        # Mise à prix
        map_match = re.search(
            r"mise\s+[àa]\s+prix\s*:?\s*([\d\s,\.]+)\s*(?:€|euros?)",
            text, re.IGNORECASE
        )
        if map_match:
            data.mise_a_prix = self._parse_price(map_match.group(1))

        # Frais prévisionnels
        frais_match = re.search(
            r"frais\s+(?:prévisionnels|estimés)\s*:?\s*([\d\s,\.]+)\s*(?:€|euros?)",
            text, re.IGNORECASE
        )
        if frais_match:
            data.frais_previsionnels = self._parse_price(frais_match.group(1))

        # Montant créance
        creance_match = re.search(
            r"(?:créance|montant\s+dû)\s*:?\s*([\d\s,\.]+)\s*(?:€|euros?)",
            text, re.IGNORECASE
        )
        if creance_match:
            data.montant_creance = self._parse_price(creance_match.group(1))

    def _extract_dates(self, text: str, data: ExtractedPVData):
        """Extract dates"""
        # Sale date
        vente_match = re.search(
            r"(?:vente|adjudication|audience)\s+(?:le\s+)?(\d{1,2}[/\-]\d{1,2}[/\-]\d{4}|\d{1,2}\s+\w+\s+\d{4})",
            text, re.IGNORECASE
        )
        if vente_match:
            data.date_vente = vente_match.group(1)

        # Visit dates
        visite_section = re.search(
            r"visite[s]?\s*:?\s*([^\n]+(?:\n[^\n]*visite[^\n]*)*)",
            text, re.IGNORECASE
        )
        if visite_section:
            dates = re.findall(
                r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{4}|\d{1,2}\s+\w+\s+\d{4})",
                visite_section.group(1)
            )
            data.dates_visite = dates

    def _extract_legal_info(self, text: str, data: ExtractedPVData):
        """Extract legal information"""
        # Tribunal
        tribunal_match = re.search(
            r"tribunal\s+(?:judiciaire|de grande instance)\s+(?:de\s+)?([a-zà-ü\-]+)",
            text, re.IGNORECASE
        )
        if tribunal_match:
            data.tribunal = f"Tribunal Judiciaire de {tribunal_match.group(1).title()}"

        # Avocat
        avocat_match = re.search(
            r"(?:Maître|Me|M[eaî]tre)\s+([A-ZÀ-Ü][a-zà-ü]+(?:\s+[A-ZÀ-Ü][a-zà-ü]+)*)",
            text
        )
        if avocat_match:
            data.avocat = f"Me {avocat_match.group(1)}"

        # RG number
        rg_match = re.search(r"(?:RG|n°)\s*(\d{2}/\d+)", text)
        if rg_match:
            data.numero_rg = rg_match.group(1)

    def _extract_description(self, text: str, data: ExtractedPVData):
        """Extract description and diagnostics"""
        # Try to find description section
        desc_patterns = [
            r"(?:description|désignation)\s*:?\s*(.{100,500})",
            r"(?:le bien|l'immeuble)\s+(?:comprend|se compose)\s+(.{100,500})",
        ]

        for pattern in desc_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                data.description_bien = match.group(1).strip()[:500]
                break

        # Diagnostics
        diag_keywords = ["DPE", "amiante", "plomb", "électricité", "gaz", "termites"]
        for keyword in diag_keywords:
            if keyword.lower() in text.lower():
                # Try to get the value
                diag_match = re.search(
                    rf"{keyword}\s*:?\s*([A-G]|\w+)",
                    text, re.IGNORECASE
                )
                if diag_match:
                    data.diagnostics.append(f"{keyword}: {diag_match.group(1)}")
                else:
                    data.diagnostics.append(keyword)

    def _parse_price(self, text: str) -> Optional[float]:
        """Parse price from text"""
        cleaned = re.sub(r"[^\d,.]", "", text.replace(" ", ""))
        cleaned = cleaned.replace(",", ".")
        if cleaned.count(".") > 1:
            parts = cleaned.rsplit(".", 1)
            cleaned = parts[0].replace(".", "") + "." + parts[1]
        try:
            return float(cleaned)
        except ValueError:
            return None
