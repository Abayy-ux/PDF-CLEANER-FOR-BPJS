from pathlib import Path
import os
import re

def resolve_clean_output_path(
    output_dir: Path | str, 
    source_path: Path | str, 
    suffix: str = "", 
    overwrite_existing: bool = True
) -> Path:
    """
    Generates an output path in output_dir.
    By default (suffix=""), preserves the exact original filename (e.g. 0184R0160626V001070.pdf).
    If overwrite_existing is False and file exists, increments safely (0184R0160626V001070_1.pdf).
    """
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    
    src = Path(source_path)
    stem = src.stem
    ext = src.suffix
    if not ext:
        ext = ".pdf"
    
    base_name = f"{stem}{suffix}{ext}"
    candidate = out_dir / base_name
    
    # If overwrite is allowed and output is not the exact same file as input source
    if overwrite_existing and candidate.resolve() != src.resolve():
        return candidate

    if not candidate.exists():
        return candidate
    
    counter = 1
    while True:
        candidate = out_dir / f"{stem}{suffix}_{counter}{ext}"
        if not candidate.exists():
            return candidate
        counter += 1

def format_file_size(num_bytes: int) -> str:
    """Formats raw byte count into human-readable size."""
    if num_bytes < 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024.0 or unit == "GB":
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{int(num_bytes)} B"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} GB"

def is_safe_path(base_dir: Path | str, target_path: Path | str) -> bool:
    """Checks if target_path is within base_dir or accessible."""
    try:
        base = Path(base_dir).resolve()
        target = Path(target_path).resolve()
        return target.exists() and (base in target.parents or target == base)
    except Exception:
        return False
