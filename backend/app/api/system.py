from fastapi import APIRouter, HTTPException
from pathlib import Path
import os
from typing import Dict, Any, List
from ..services.system_diag import get_system_diagnostics
from ..models.schemas import BrowseDirectoryRequest
from ..utils.logger import app_logger

router = APIRouter(prefix="/api/system", tags=["System"])

@router.get("/diagnostics")
def system_diagnostics() -> Dict[str, Any]:
    """Returns system configuration and engine diagnostics."""
    return get_system_diagnostics()

@router.get("/default-paths")
def get_default_paths() -> Dict[str, str]:
    """Returns suggested default directories (current working dir, home, desktop, documents)."""
    cwd = Path.cwd()
    home = Path.home()
    return {
        "current_dir": str(cwd.resolve()),
        "home_dir": str(home.resolve()),
        "documents_dir": str((home / "Documents").resolve()) if (home / "Documents").exists() else str(home),
        "desktop_dir": str((home / "Desktop").resolve()) if (home / "Desktop").exists() else str(home),
    }

@router.post("/browse")
def browse_directory(req: BrowseDirectoryRequest) -> Dict[str, Any]:
    """
    Lists subdirectories for the folder browser picker in the UI.
    Allows user to navigate local filesystem safely.
    """
    target = Path(req.path).resolve() if req.path else Path.cwd().resolve()

    if not target.exists():
        target = Path.home().resolve()

    if not target.is_dir():
        target = target.parent

    try:
        subdirs: List[Dict[str, Any]] = []
        # Add parent folder option if not root
        parent_path = target.parent if target.parent != target else None

        for item in sorted(target.iterdir(), key=lambda x: x.name.lower()):
            if item.is_dir() and not item.name.startswith("."):
                try:
                    subdirs.append({
                        "name": item.name,
                        "path": str(item.resolve()),
                    })
                except PermissionError:
                    continue

        return {
            "current_path": str(target),
            "parent_path": str(parent_path) if parent_path else None,
            "directories": subdirs,
        }
    except Exception as e:
        app_logger.error(f"Error browsing directory {target}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
