from pathlib import Path
from typing import List, Dict, Any, Tuple
from ..config import settings
from ..utils.logger import app_logger

class FileScanResult:
    def __init__(self):
        self.eligible_files: List[Path] = []
        self.ignored_files: List[Dict[str, Any]] = []
        self.total_eligible_size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eligible_count": len(self.eligible_files),
            "eligible_files": [
                {
                    "path": str(f.resolve()),
                    "name": f.name,
                    "size": f.stat().st_size if f.exists() else 0
                }
                for f in self.eligible_files
            ],
            "total_eligible_size": self.total_eligible_size,
            "ignored_count": len(self.ignored_files),
            "ignored_files": self.ignored_files,
        }

def is_eligible_pdf(file_path: Path, check_exists: bool = False) -> Tuple[bool, str]:
    """
    Checks whether a file should be processed as a PDF.
    Returns (is_eligible, reason_if_ignored).
    """
    name = file_path.name
    lower_name = name.lower()

    # Check AppleDouble files starting with ._
    if name.startswith("._"):
        return False, "macOS AppleDouble metadata file"

    # Check other hidden prefixes
    if name.startswith(".") and not name.startswith(".."):
        return False, "Hidden system file"

    # Check known junk file names
    if lower_name in settings.IGNORED_FILES:
        return False, f"System metadata file ({name})"

    # Check office temp lock files
    if name.startswith("~$"):
        return False, "Temporary lock file"

    # Check extension
    if not lower_name.endswith(".pdf"):
        return False, f"Non-PDF file extension ({file_path.suffix or 'none'})"

    # If check_exists is True, ensure it's a regular file
    if check_exists and file_path.exists() and not file_path.is_file():
        return False, "Not a regular file"

    return True, ""

def scan_directory(source_dir: Path | str, recursive: bool = False) -> FileScanResult:
    """
    Scans source_dir for PDF files, filtering out AppleDouble, .DS_Store, Thumbs.db, non-PDFs.
    """
    src = Path(source_dir).resolve()
    result = FileScanResult()

    if not src.exists() or not src.is_dir():
        app_logger.warning(f"Scan directory does not exist or is not a directory: {src}")
        return result

    try:
        iterator = src.rglob("*") if recursive else src.iterdir()
        for item in iterator:
            if item.is_dir():
                continue
            
            eligible, reason = is_eligible_pdf(item)
            if eligible:
                try:
                    size = item.stat().st_size
                    result.eligible_files.append(item)
                    result.total_eligible_size += size
                except Exception as e:
                    result.ignored_files.append({
                        "name": item.name,
                        "path": str(item),
                        "reason": f"Unreadable file: {str(e)}"
                    })
            else:
                result.ignored_files.append({
                    "name": item.name,
                    "path": str(item),
                    "reason": reason
                })

        # Sort eligible files naturally by filename
        result.eligible_files.sort(key=lambda p: p.name.lower())
        app_logger.info(f"Scanned {src}: {len(result.eligible_files)} eligible PDFs, {len(result.ignored_files)} ignored.")
    except Exception as e:
        app_logger.error(f"Error scanning directory {src}: {e}")

    return result
