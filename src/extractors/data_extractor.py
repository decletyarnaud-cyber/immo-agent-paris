"""
High-level data extraction from PV documents
"""
from pathlib import Path
from typing import Optional, Dict, Any
from loguru import logger

from .pdf_parser import PDFParser, ExtractedPVData
from .ocr_handler import HybridPDFExtractor, OCRHandler
from src.storage.models import Auction, PVStatus


class PVDataExtractor:
    """
    Extract and process data from PV (procès-verbal) documents
    """

    def __init__(self, use_ocr: bool = True):
        """
        Initialize the extractor

        Args:
            use_ocr: Whether to use OCR for image-based PDFs
        """
        self.pdf_parser = PDFParser()
        self.use_ocr = use_ocr

        if use_ocr:
            self.hybrid_extractor = HybridPDFExtractor()
        else:
            self.hybrid_extractor = None

    def extract_from_pdf(self, pdf_path: str, force_ocr: bool = False) -> ExtractedPVData:
        """
        Extract structured data from a PV PDF

        Args:
            pdf_path: Path to the PDF file
            force_ocr: Force OCR even if regular extraction works

        Returns:
            ExtractedPVData object with parsed information
        """
        if not Path(pdf_path).exists():
            logger.error(f"PDF file not found: {pdf_path}")
            return ExtractedPVData()

        # Check if OCR is needed
        if self.use_ocr and (force_ocr or self.pdf_parser.is_image_pdf(pdf_path)):
            logger.info(f"Using OCR for {pdf_path}")
            text = self.hybrid_extractor.extract_text(pdf_path, force_ocr=force_ocr)
            data = ExtractedPVData()
            data.raw_text = text
            data.page_count = self.pdf_parser.get_page_count(pdf_path)
            # Parse the OCR text
            self._parse_text_into_data(text, data)
            return data
        else:
            return self.pdf_parser.parse_pv(pdf_path)

    def _parse_text_into_data(self, text: str, data: ExtractedPVData):
        """Parse raw text into structured data fields"""
        # Reuse the parsing logic from PDFParser
        parser = PDFParser()
        parser._extract_address(text, data)
        parser._extract_property_details(text, data)
        parser._extract_copropriete_info(text, data)
        parser._extract_occupation_status(text, data)
        parser._extract_financial_info(text, data)
        parser._extract_dates(text, data)
        parser._extract_legal_info(text, data)
        parser._extract_description(text, data)

    def enrich_auction_with_pv(self, auction: Auction, pdf_path: str) -> Auction:
        """
        Enrich an auction object with data from its PV

        Args:
            auction: The Auction object to enrich
            pdf_path: Path to the PV PDF

        Returns:
            Enriched Auction object
        """
        pv_data = self.extract_from_pdf(pdf_path)

        if not pv_data.raw_text:
            logger.warning(f"Could not extract data from PV: {pdf_path}")
            return auction

        # Update auction with PV data (only if auction field is empty)
        if not auction.adresse and pv_data.adresse:
            auction.adresse = pv_data.adresse

        if not auction.code_postal and pv_data.code_postal:
            auction.code_postal = pv_data.code_postal
            auction.department = pv_data.code_postal[:2]

        if not auction.ville and pv_data.ville:
            auction.ville = pv_data.ville

        if not auction.surface and pv_data.surface:
            auction.surface = pv_data.surface

        if not auction.nb_pieces and pv_data.nb_pieces:
            auction.nb_pieces = pv_data.nb_pieces

        if not auction.nb_chambres and pv_data.nb_chambres:
            auction.nb_chambres = pv_data.nb_chambres

        if not auction.etage and pv_data.etage:
            auction.etage = pv_data.etage

        if not auction.mise_a_prix and pv_data.mise_a_prix:
            auction.mise_a_prix = pv_data.mise_a_prix

        # Enrich description
        if pv_data.description_bien:
            if auction.description:
                auction.description += f"\n\n{pv_data.description_bien}"
            else:
                auction.description = pv_data.description_bien

        # Add occupation status to description
        if pv_data.etat_occupation:
            status_text = f"État d'occupation: {pv_data.etat_occupation}"
            if pv_data.locataire_info:
                status_text += f" ({pv_data.locataire_info})"
            if pv_data.loyer_mensuel:
                status_text += f" - Loyer: {pv_data.loyer_mensuel}€/mois"

            if auction.description:
                auction.description += f"\n{status_text}"
            else:
                auction.description = status_text

        # Add copropriété info
        if pv_data.is_copropriete:
            copro_text = "Copropriété"
            if pv_data.lot_number:
                copro_text += f" - Lot n°{pv_data.lot_number}"
            if pv_data.charges_copropriete:
                copro_text += f" - Charges: {pv_data.charges_copropriete}€/an"

            if auction.description:
                auction.description += f"\n{copro_text}"
            else:
                auction.description = copro_text

        # Mark PV as processed
        auction.pv_local_path = pdf_path
        auction.pv_status = PVStatus.DISPONIBLE

        logger.info(f"Enriched auction with PV data: {auction.adresse}")
        return auction

    def get_extraction_summary(self, pv_data: ExtractedPVData) -> Dict[str, Any]:
        """
        Get a summary of extracted data for display

        Args:
            pv_data: ExtractedPVData object

        Returns:
            Dictionary with summary information
        """
        return {
            "address": {
                "full": f"{pv_data.adresse} {pv_data.code_postal} {pv_data.ville}".strip(),
                "adresse": pv_data.adresse,
                "code_postal": pv_data.code_postal,
                "ville": pv_data.ville,
            },
            "property": {
                "type": pv_data.type_bien,
                "surface": pv_data.surface,
                "pieces": pv_data.nb_pieces,
                "chambres": pv_data.nb_chambres,
                "etage": pv_data.etage,
            },
            "copropriete": {
                "is_copropriete": pv_data.is_copropriete,
                "lot": pv_data.lot_number,
                "charges": pv_data.charges_copropriete,
                "tantiemes": pv_data.tantiemes,
            },
            "occupation": {
                "status": pv_data.etat_occupation,
                "locataire": pv_data.locataire_info,
                "loyer": pv_data.loyer_mensuel,
            },
            "financier": {
                "mise_a_prix": pv_data.mise_a_prix,
                "frais": pv_data.frais_previsionnels,
                "creance": pv_data.montant_creance,
            },
            "dates": {
                "vente": pv_data.date_vente,
                "visites": pv_data.dates_visite,
            },
            "legal": {
                "tribunal": pv_data.tribunal,
                "avocat": pv_data.avocat,
                "rg": pv_data.numero_rg,
            },
            "diagnostics": pv_data.diagnostics,
            "pages": pv_data.page_count,
        }
