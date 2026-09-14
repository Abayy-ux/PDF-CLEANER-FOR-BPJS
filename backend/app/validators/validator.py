from pathlib import Path
from typing import Dict, Any, List, Optional
import fitz  # PyMuPDF
from ..pdf.inspector import inspect_pdf_structure, PDFInspectionResult
from ..utils.logger import app_logger

class ValidationResult:
    def __init__(self, file_path: Path | str):
        self.file_path = str(file_path)
        self.is_valid: bool = False
        self.stage_failed: Optional[str] = None
        self.error_message: Optional[str] = None
        self.page_count: int = 0
        self.pages_rendered: int = 0
        self.issues: List[str] = []
        self.inspection: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "is_valid": self.is_valid,
            "stage_failed": self.stage_failed,
            "error_message": self.error_message,
            "page_count": self.page_count,
            "pages_rendered": self.pages_rendered,
            "issues": self.issues,
            "inspection": self.inspection,
        }

def validate_pdf(
    pdf_path: Path | str, 
    expected_page_count: Optional[int] = None,
    strict_structural: bool = True
) -> ValidationResult:
    """
    Comprehensive 5-stage PDF validation:
    Stage 1: File existence and non-zero size
    Stage 2: PDF parser loadable and xref/trailer integrity
    Stage 3: Page count > 0 (and matches expected if provided)
    Stage 4: Every single page can be rendered/read without exceptions
    Stage 5: Structural safety check (no active /JS, /OpenAction, /AA, /Launch, /EmbeddedFiles, /XFA)
    """
    path = Path(pdf_path)
    result = ValidationResult(path)

    # --- Stage 1: File Existence & Size ---
    if not path.exists():
        result.stage_failed = "file_exists"
        result.error_message = f"File does not exist: {path.name}"
        return result

    size = path.stat().st_size
    if size == 0:
        result.stage_failed = "file_size"
        result.error_message = f"File is empty (0 bytes): {path.name}"
        return result

    # --- Stage 2: Parser & Header/Trailer Integrity ---
    doc = None
    try:
        doc = fitz.open(str(path))
        if doc.is_encrypted and doc.needs_pass:
            result.stage_failed = "encryption"
            result.error_message = "File is password protected"
            doc.close()
            return result
    except Exception as e:
        result.stage_failed = "pdf_parser"
        result.error_message = f"Cannot parse PDF structure: {str(e)}"
        if doc:
            doc.close()
        return result

    # --- Stage 3: Page Count ---
    page_count = len(doc)
    result.page_count = page_count
    if page_count == 0:
        result.stage_failed = "page_count"
        result.error_message = "PDF contains 0 pages"
        doc.close()
        return result

    if expected_page_count is not None and page_count != expected_page_count:
        result.stage_failed = "page_count_mismatch"
        result.error_message = f"Page count mismatch: expected {expected_page_count}, got {page_count}"
        doc.close()
        return result

    # --- Stage 4: Page Rendering / Readability ---
    try:
        for page_idx in range(page_count):
            page = doc[page_idx]
            # Render low-res thumbnail to verify page stream is renderable and not corrupt
            pix = page.get_pixmap(dpi=72)
            if pix.width == 0 or pix.height == 0:
                result.stage_failed = "page_render"
                result.error_message = f"Page {page_idx + 1} rendered with 0 dimensions"
                doc.close()
                return result
            result.pages_rendered += 1
    except Exception as e:
        result.stage_failed = "page_render"
        result.error_message = f"Rendering error on page {result.pages_rendered + 1}: {str(e)}"
        doc.close()
        return result
    finally:
        if doc:
            doc.close()

    # --- Stage 5: Structural Inspection ---
    inspection = inspect_pdf_structure(path)
    result.inspection = inspection.to_dict()

    if strict_structural and not inspection.is_clean:
        result.stage_failed = "structural_safety"
        result.issues = inspection.detected_issues
        result.error_message = f"Structural validation failed: {', '.join(inspection.detected_issues)}"
        return result

    result.is_valid = True
    return result
