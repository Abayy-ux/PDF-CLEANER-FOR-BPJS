from pathlib import Path
from typing import Dict, Any, List, Set
import fitz  # PyMuPDF
import pypdf
from ..utils.logger import app_logger

# Dangerous / active structure keys in PDF object dictionary tree
FORBIDDEN_OBJECT_KEYS = {
    "/JS",
    "/JavaScript",
    "/AA",
    "/OpenAction",
    "/Launch",
    "/EmbeddedFiles",
    "/EmbeddedFile",
    "/XFA",
    "/RichMedia",
    "/RichMediaSettings",
    "/RichMediaContent",
}

class PDFInspectionResult:
    def __init__(self, file_path: Path | str):
        self.file_path = str(file_path)
        self.is_valid_pdf: bool = False
        self.page_count: int = 0
        self.is_encrypted: bool = False
        self.has_javascript: bool = False
        self.has_open_action: bool = False
        self.has_additional_actions: bool = False
        self.has_launch_action: bool = False
        self.has_embedded_files: bool = False
        self.has_xfa: bool = False
        self.has_acroform: bool = False
        self.has_annotations: bool = False
        self.annotation_count: int = 0
        self.detected_issues: List[str] = []
        self.page_dimensions: List[Dict[str, float]] = []
        self.error_message: str | None = None

    @property
    def is_clean(self) -> bool:
        """Returns True if no forbidden or active structural elements were found."""
        return (
            self.is_valid_pdf
            and not self.has_javascript
            and not self.has_open_action
            and not self.has_additional_actions
            and not self.has_launch_action
            and not self.has_embedded_files
            and not self.has_xfa
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "is_valid_pdf": self.is_valid_pdf,
            "page_count": self.page_count,
            "is_encrypted": self.is_encrypted,
            "has_javascript": self.has_javascript,
            "has_open_action": self.has_open_action,
            "has_additional_actions": self.has_additional_actions,
            "has_launch_action": self.has_launch_action,
            "has_embedded_files": self.has_embedded_files,
            "has_xfa": self.has_xfa,
            "has_acroform": self.has_acroform,
            "has_annotations": self.has_annotations,
            "annotation_count": self.annotation_count,
            "is_clean": self.is_clean,
            "detected_issues": self.detected_issues,
            "page_dimensions": self.page_dimensions,
            "error_message": self.error_message,
        }

def inspect_pdf_structure(pdf_path: Path | str) -> PDFInspectionResult:
    """
    Performs deep structural inspection of PDF objects.
    Traverses PDF dictionary trees (Catalog, Names, AcroForm, Actions, Pages)
    without confusing binary image data with PDF keywords.
    """
    path = Path(pdf_path)
    result = PDFInspectionResult(path)

    if not path.exists() or path.stat().st_size == 0:
        result.error_message = "File does not exist or is 0 bytes."
        return result

    # 1. Primary inspection using PyMuPDF (fast & robust)
    try:
        doc = fitz.open(str(path))
        result.is_valid_pdf = True
        result.page_count = len(doc)
        result.is_encrypted = doc.is_encrypted

        if result.is_encrypted and doc.needs_pass:
            result.detected_issues.append("PDF is password protected / encrypted")
            doc.close()
            return result

        total_annots = 0
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            rect = page.rect
            result.page_dimensions.append({
                "page": page_idx + 1,
                "width": round(rect.width, 2),
                "height": round(rect.height, 2),
                "rotation": page.rotation
            })
            annots = list(page.annots())
            total_annots += len(annots)

        result.annotation_count = total_annots
        if total_annots > 0:
            result.has_annotations = True

        # Check embedded files via PyMuPDF
        if doc.embfile_count() > 0:
            result.has_embedded_files = True
            result.detected_issues.append(f"Contains {doc.embfile_count()} embedded file(s)")

        doc.close()
    except Exception as e:
        app_logger.warning(f"PyMuPDF could not fully parse {path.name}: {e}")
        result.is_valid_pdf = False
        result.error_message = f"PyMuPDF parser error: {str(e)}"
        return result

    # 2. Deep Dictionary Traversal using pypdf to check object keys
    try:
        reader = pypdf.PdfReader(str(path), strict=False)
        
        # Check Catalog / Root
        root = reader.trailer.get("/Root")
        if root:
            if hasattr(root, "get_object"):
                root = root.get_object()

            # Check /OpenAction
            if "/OpenAction" in root:
                result.has_open_action = True
                result.detected_issues.append("Document contains /OpenAction trigger")

            # Check /AA (Additional Actions)
            if "/AA" in root:
                result.has_additional_actions = True
                result.detected_issues.append("Document contains /AA (Additional Actions)")

            # Check /AcroForm
            if "/AcroForm" in root:
                result.has_acroform = True
                acro = root["/AcroForm"]
                if hasattr(acro, "get_object"):
                    acro = acro.get_object()
                if isinstance(acro, dict) and "/XFA" in acro:
                    result.has_xfa = True
                    result.detected_issues.append("Document contains /XFA dynamic XML form")

            # Check /Names dictionary (JavaScript, EmbeddedFiles)
            if "/Names" in root:
                names = root["/Names"]
                if hasattr(names, "get_object"):
                    names = names.get_object()
                if isinstance(names, dict):
                    if "/JavaScript" in names or "/JS" in names:
                        result.has_javascript = True
                        result.detected_issues.append("Document contains /JavaScript in /Names dictionary")
                    if "/EmbeddedFiles" in names or "/EmbeddedFile" in names:
                        result.has_embedded_files = True
                        result.detected_issues.append("Document contains /EmbeddedFiles in /Names dictionary")

        # Traverse objects in reader to identify any /JS, /JavaScript, /Launch, /AA objects
        visited_objects: Set[int] = set()
        
        def check_object_tree(obj: Any, depth: int = 0):
            if depth > 100:  # Prevent recursion cycles
                return
            if obj is None:
                return
            
            if hasattr(obj, "get_object"):
                obj_id = id(obj)
                if obj_id in visited_objects:
                    return
                visited_objects.add(obj_id)
                try:
                    obj = obj.get_object()
                except Exception:
                    return

            if isinstance(obj, dict):
                # Check keys
                for key in obj.keys():
                    key_str = str(key)
                    if key_str in ("/JS", "/JavaScript"):
                        result.has_javascript = True
                        if "Contains /JS or /JavaScript object" not in result.detected_issues:
                            result.detected_issues.append("Contains /JS or /JavaScript object")
                    elif key_str == "/Launch":
                        result.has_launch_action = True
                        if "Contains /Launch action" not in result.detected_issues:
                            result.detected_issues.append("Contains /Launch action")
                    elif key_str == "/AA" and not result.has_additional_actions:
                        result.has_additional_actions = True
                        if "Contains /AA (Additional Actions)" not in result.detected_issues:
                            result.detected_issues.append("Contains /AA (Additional Actions)")
                    elif key_str in ("/EmbeddedFile", "/EmbeddedFiles") and not result.has_embedded_files:
                        result.has_embedded_files = True
                        if "Contains /EmbeddedFile" not in result.detected_issues:
                            result.detected_issues.append("Contains /EmbeddedFile")
                    elif key_str == "/XFA" and not result.has_xfa:
                        result.has_xfa = True
                        if "Contains /XFA dynamic XML form" not in result.detected_issues:
                            result.detected_issues.append("Contains /XFA dynamic XML form")

                # Recurse into values
                for val in obj.values():
                    check_object_tree(val, depth + 1)

            elif isinstance(obj, list):
                for item in obj:
                    check_object_tree(item, depth + 1)

        # Inspect root object tree
        if root:
            check_object_tree(root)

        # Inspect page trees for page-level actions and widgets
        for page in reader.pages:
            try:
                page_obj = page.get_object() if hasattr(page, "get_object") else page
                if isinstance(page_obj, dict):
                    if "/AA" in page_obj:
                        result.has_additional_actions = True
                        if "Contains Page-level /AA" not in result.detected_issues:
                            result.detected_issues.append("Contains Page-level /AA")
                    if "/Annots" in page_obj:
                        annots_obj = page_obj["/Annots"]
                        check_object_tree(annots_obj, depth=1)
            except Exception:
                continue

    except Exception as e:
        app_logger.debug(f"Pypdf deep inspection note on {path.name}: {e}")

    return result
