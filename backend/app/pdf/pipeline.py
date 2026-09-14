from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import time
import enum
from .standard_normalizer import normalize_standard_pdf
from .max_compat_normalizer import normalize_max_compat_pdf
from ..validators.validator import validate_pdf, ValidationResult
from ..utils.logger import app_logger

class ProcessingMode(str, enum.Enum):
    AUTOMATIC = "automatic"
    STANDARD = "standard"
    MAX_COMPAT = "max_compat"

class PipelineResult:
    def __init__(self, filename: str, mode: ProcessingMode):
        self.filename = filename
        self.mode = mode
        self.status: str = "pending"  # success, fallback, failed
        self.method_used: str = "UNKNOWN"
        self.stage: str = "init"
        self.original_size: int = 0
        self.output_size: int = 0
        self.page_count: int = 0
        self.processing_time_ms: float = 0.0
        self.error: Optional[str] = None
        self.fallback_reason: Optional[str] = None
        self.details: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filename": self.filename,
            "mode": self.mode.value if hasattr(self.mode, "value") else str(self.mode),
            "status": self.status,
            "method_used": self.method_used,
            "stage": self.stage,
            "original_size": self.original_size,
            "output_size": self.output_size,
            "page_count": self.page_count,
            "processing_time_ms": round(self.processing_time_ms, 2),
            "error": self.error,
            "fallback_reason": self.fallback_reason,
            "details": self.details,
        }

def process_single_pdf(
    source_path: Path | str,
    target_path: Path | str,
    mode: ProcessingMode = ProcessingMode.AUTOMATIC,
    dpi: int = 200,
    jpeg_quality: int = 92
) -> PipelineResult:
    """
    Core normalization pipeline processing a single PDF.
    Handles Automatic (Standard -> Validate -> Fallback ASCIIHex -> Validate),
    Standard, and Maximum Compatibility modes.
    """
    src = Path(source_path).resolve()
    dst = Path(target_path).resolve()
    result = PipelineResult(src.name, mode)
    start_time = time.perf_counter()

    if not src.exists():
        result.status = "failed"
        result.stage = "input_check"
        result.error = f"Source file does not exist: {src}"
        result.processing_time_ms = (time.perf_counter() - start_time) * 1000
        return result

    result.original_size = src.stat().st_size

    # Mode 1: Maximum Compatibility Direct
    if mode == ProcessingMode.MAX_COMPAT:
        result.stage = "max_compat"
        ok, msg, stats = normalize_max_compat_pdf(src, dst, dpi=dpi, jpeg_quality=jpeg_quality)
        result.page_count = stats.get("page_count", 0)
        result.output_size = stats.get("output_size", 0)
        result.details = stats

        if not ok:
            result.status = "failed"
            result.error = msg
            result.method_used = "FAILED"
        else:
            # Validate output
            val_res = validate_pdf(dst, expected_page_count=result.page_count, strict_structural=True)
            if val_res.is_valid:
                result.status = "fallback"
                result.method_used = "FALLBACK / ASCIIHEX"
            else:
                result.status = "failed"
                result.stage = "validation"
                result.error = f"Max compat validation failed: {val_res.error_message}"
                result.method_used = "FAILED"

        result.processing_time_ms = (time.perf_counter() - start_time) * 1000
        return result

    # Mode 2: Standard Direct
    if mode == ProcessingMode.STANDARD:
        result.stage = "standard"
        ok, msg, stats = normalize_standard_pdf(src, dst)
        result.page_count = stats.get("page_count", 0)
        result.output_size = stats.get("output_size", 0)
        result.details = stats

        if not ok:
            result.status = "failed"
            result.error = msg
            result.method_used = "FAILED"
        else:
            val_res = validate_pdf(dst, expected_page_count=result.page_count, strict_structural=True)
            if val_res.is_valid:
                result.status = "success"
                result.method_used = "STANDARD"
            else:
                result.status = "failed"
                result.stage = "validation"
                result.error = f"Standard validation failed: {val_res.error_message}"
                result.method_used = "FAILED"

        result.processing_time_ms = (time.perf_counter() - start_time) * 1000
        return result

    # Mode 3: Automatic (Standard -> Validate -> Fallback if fail)
    result.stage = "standard_attempt"
    std_temp = dst.with_name(f"{dst.stem}_candidate{dst.suffix}")
    std_ok, std_msg, std_stats = normalize_standard_pdf(src, std_temp)

    if std_ok:
        val_res = validate_pdf(std_temp, expected_page_count=std_stats.get("page_count"), strict_structural=True)
        if val_res.is_valid:
            # Standard normalization succeeded and passed all structural and rendering checks!
            if std_temp != dst:
                if dst.exists():
                    dst.unlink(missing_ok=True)
                std_temp.rename(dst)
            result.status = "success"
            result.method_used = "STANDARD"
            result.page_count = std_stats.get("page_count", 0)
            result.output_size = dst.stat().st_size
            result.details = std_stats
            result.processing_time_ms = (time.perf_counter() - start_time) * 1000
            return result
        else:
            result.fallback_reason = f"Standard output failed validation: {val_res.error_message}"
            app_logger.info(f"Auto-fallback triggered for {src.name}: {result.fallback_reason}")
    else:
        result.fallback_reason = f"Standard normalization failed: {std_msg}"
        app_logger.info(f"Auto-fallback triggered for {src.name}: {result.fallback_reason}")

    # Cleanup temp standard candidate if it exists
    if std_temp.exists():
        std_temp.unlink(missing_ok=True)

    # Trigger Fallback: Maximum Compatibility Mode
    result.stage = "fallback_max_compat"
    fb_ok, fb_msg, fb_stats = normalize_max_compat_pdf(src, dst, dpi=dpi, jpeg_quality=jpeg_quality)
    result.page_count = fb_stats.get("page_count", 0)
    result.output_size = fb_stats.get("output_size", 0)
    result.details = fb_stats

    if not fb_ok:
        result.status = "failed"
        result.stage = "fallback_execution"
        result.error = fb_msg
        result.method_used = "FAILED"
    else:
        fb_val = validate_pdf(dst, expected_page_count=result.page_count, strict_structural=True)
        if fb_val.is_valid:
            result.status = "fallback"
            result.method_used = "FALLBACK / ASCIIHEX"
        else:
            result.status = "failed"
            result.stage = "fallback_validation"
            result.error = f"Fallback output failed validation: {fb_val.error_message}"
            result.method_used = "FAILED"

    result.processing_time_ms = (time.perf_counter() - start_time) * 1000
    return result
