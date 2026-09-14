import os
import shutil
import subprocess
import platform
import sys
from typing import Dict, Any, Optional
import fitz
import pypdf
import PIL
from ..config import settings
from ..utils.logger import app_logger

def detect_ghostscript() -> Dict[str, Any]:
    """
    Cross-platform Ghostscript detection.
    Checks common binary names: gs, gswin64c, gswin32c, or env variable GHOSTSCRIPT_PATH.
    """
    candidates = ["gs", "gswin64c", "gswin32c"]
    env_gs = os.environ.get("GHOSTSCRIPT_PATH")
    if env_gs:
        candidates.insert(0, env_gs)

    for candidate in candidates:
        bin_path = shutil.which(candidate)
        if bin_path:
            try:
                proc = subprocess.run(
                    [bin_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                version_str = proc.stdout.strip() or proc.stderr.strip()
                return {
                    "available": True,
                    "binary_path": bin_path,
                    "version": version_str or "detected",
                    "command": candidate
                }
            except Exception as e:
                app_logger.debug(f"Ghostscript invocation error for {candidate}: {e}")

    return {
        "available": False,
        "binary_path": None,
        "version": None,
        "note": "Ghostscript not found in system PATH. Native PyMuPDF & Pillow engines active."
    }

def get_system_diagnostics() -> Dict[str, Any]:
    """
    Returns full system diagnostics and engine readiness.
    """
    gs_info = detect_ghostscript()
    return {
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "os_platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "cpu_cores": os.cpu_count() or 1,
        "engines": {
            "pymupdf": {
                "available": True,
                "version": getattr(fitz, "__version__", "installed"),
            },
            "pypdf": {
                "available": True,
                "version": getattr(pypdf, "__version__", "installed"),
            },
            "pillow": {
                "available": True,
                "version": getattr(PIL, "__version__", "installed"),
            },
            "ghostscript": gs_info,
        },
        "default_binding": f"{settings.HOST}:{settings.PORT}",
        "is_ready": True
    }
