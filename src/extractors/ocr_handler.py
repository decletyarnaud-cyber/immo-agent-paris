"""
OCR handler for image-based PDF documents
"""
import os
import tempfile
from pathlib import Path
from typing import Optional, List
from loguru import logger

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    import fitz  # PyMuPDF for PDF to image conversion
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


class OCRHandler:
    """Handle OCR for image-based PDFs"""

    def __init__(self, tesseract_path: Optional[str] = None):
        """
        Initialize OCR handler

        Args:
            tesseract_path: Path to tesseract executable (optional)
        """
        self.available = HAS_TESSERACT and HAS_PYMUPDF

        if tesseract_path and HAS_TESSERACT:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

        if not self.available:
            missing = []
            if not HAS_TESSERACT:
                missing.append("pytesseract")
            if not HAS_PYMUPDF:
                missing.append("PyMuPDF")
            logger.warning(f"OCR not available. Missing: {', '.join(missing)}")

    def is_available(self) -> bool:
        """Check if OCR is available"""
        return self.available

    def pdf_to_images(self, pdf_path: str, dpi: int = 200) -> List[Image.Image]:
        """
        Convert PDF pages to images

        Args:
            pdf_path: Path to PDF file
            dpi: Resolution for conversion

        Returns:
            List of PIL Image objects
        """
        if not HAS_PYMUPDF:
            logger.error("PyMuPDF not available for PDF to image conversion")
            return []

        images = []
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                # Convert page to image
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
                # Convert to PIL Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img)
            doc.close()
        except Exception as e:
            logger.error(f"Error converting PDF to images: {e}")

        return images

    def ocr_image(self, image: Image.Image, lang: str = "fra") -> str:
        """
        Perform OCR on a single image

        Args:
            image: PIL Image object
            lang: Language for OCR (fra = French)

        Returns:
            Extracted text
        """
        if not HAS_TESSERACT:
            logger.error("Tesseract not available for OCR")
            return ""

        try:
            # Preprocess image for better OCR
            image = self._preprocess_image(image)
            text = pytesseract.image_to_string(image, lang=lang)
            return text
        except Exception as e:
            logger.error(f"Error performing OCR: {e}")
            return ""

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocess image for better OCR results

        Args:
            image: PIL Image object

        Returns:
            Preprocessed image
        """
        # Convert to grayscale
        if image.mode != 'L':
            image = image.convert('L')

        # Increase contrast (simple thresholding)
        # This can be enhanced with more sophisticated preprocessing

        return image

    def ocr_pdf(self, pdf_path: str, lang: str = "fra") -> str:
        """
        Perform OCR on entire PDF

        Args:
            pdf_path: Path to PDF file
            lang: Language for OCR

        Returns:
            Extracted text from all pages
        """
        if not self.available:
            logger.error("OCR not available")
            return ""

        images = self.pdf_to_images(pdf_path)
        if not images:
            return ""

        all_text = []
        for i, image in enumerate(images):
            logger.debug(f"OCR processing page {i + 1}/{len(images)}")
            text = self.ocr_image(image, lang)
            if text:
                all_text.append(f"--- Page {i + 1} ---\n{text}")

        return "\n\n".join(all_text)

    def ocr_pdf_with_progress(self, pdf_path: str, lang: str = "fra", callback=None) -> str:
        """
        Perform OCR on PDF with progress callback

        Args:
            pdf_path: Path to PDF file
            lang: Language for OCR
            callback: Function to call with progress (page_num, total_pages)

        Returns:
            Extracted text
        """
        if not self.available:
            return ""

        images = self.pdf_to_images(pdf_path)
        if not images:
            return ""

        all_text = []
        total = len(images)

        for i, image in enumerate(images):
            if callback:
                callback(i + 1, total)

            text = self.ocr_image(image, lang)
            if text:
                all_text.append(f"--- Page {i + 1} ---\n{text}")

        return "\n\n".join(all_text)


class HybridPDFExtractor:
    """
    Hybrid PDF text extractor that uses regular extraction
    first, then falls back to OCR for image-based pages
    """

    def __init__(self, ocr_handler: Optional[OCRHandler] = None):
        self.ocr_handler = ocr_handler or OCRHandler()

        try:
            import pdfplumber
            self.has_pdfplumber = True
        except ImportError:
            self.has_pdfplumber = False

    def extract_text(self, pdf_path: str, force_ocr: bool = False) -> str:
        """
        Extract text from PDF, using OCR if needed

        Args:
            pdf_path: Path to PDF file
            force_ocr: Always use OCR even if text extraction works

        Returns:
            Extracted text
        """
        if force_ocr:
            return self.ocr_handler.ocr_pdf(pdf_path)

        # Try regular text extraction first
        regular_text = self._extract_regular(pdf_path)

        # Check if we got enough text
        if len(regular_text.strip()) > 200:
            return regular_text

        # Fall back to OCR
        logger.info(f"Regular extraction yielded little text, trying OCR for {pdf_path}")
        ocr_text = self.ocr_handler.ocr_pdf(pdf_path)

        # Return the one with more content
        if len(ocr_text) > len(regular_text):
            return ocr_text
        return regular_text

    def _extract_regular(self, pdf_path: str) -> str:
        """Extract text using regular methods"""
        if not self.has_pdfplumber:
            return ""

        import pdfplumber

        text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            logger.error(f"Error in regular text extraction: {e}")

        return text

    def needs_ocr(self, pdf_path: str) -> bool:
        """
        Check if a PDF likely needs OCR

        Args:
            pdf_path: Path to PDF file

        Returns:
            True if OCR is recommended
        """
        regular_text = self._extract_regular(pdf_path)
        # If we get less than 100 chars per page on average, probably needs OCR
        if not self.has_pdfplumber:
            return True

        import pdfplumber
        try:
            with pdfplumber.open(pdf_path) as pdf:
                page_count = len(pdf.pages)
        except:
            return True

        if page_count == 0:
            return True

        chars_per_page = len(regular_text) / page_count
        return chars_per_page < 100
