from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from ..pdf.pipeline import ProcessingMode

class ScanRequest(BaseModel):
    source_dir: str
    recursive: bool = False

class ScanResponse(BaseModel):
    source_dir: str
    eligible_count: int
    eligible_files: List[Dict[str, Any]]
    total_eligible_size: int
    ignored_count: int
    ignored_files: List[Dict[str, Any]]

class ProcessBatchRequest(BaseModel):
    source_dir: str
    output_dir: str
    mode: ProcessingMode = ProcessingMode.AUTOMATIC
    dpi: int = Field(default=200, ge=72, le=600)
    jpeg_quality: int = Field(default=92, ge=50, le=100)
    recursive: bool = False
    filename_suffix: str = ""
    overwrite_existing: bool = True

class FileProcessResultItem(BaseModel):
    filename: str
    mode: str
    status: str  # success, fallback, failed
    method_used: str
    stage: str
    original_size: int
    output_size: int
    page_count: int
    processing_time_ms: float
    error: Optional[str] = None
    fallback_reason: Optional[str] = None
    details: Dict[str, Any] = {}

class BatchJobStatus(BaseModel):
    job_id: str
    source_dir: str
    output_dir: str
    mode: str
    status: str  # queued, running, completed, cancelled, failed
    total_files: int
    processed_files: int
    success_count: int
    fallback_count: int
    failed_count: int
    progress_percentage: float
    current_file: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    elapsed_seconds: float = 0.0
    results: List[FileProcessResultItem] = []
    error: Optional[str] = None

class InspectRequest(BaseModel):
    file_path: str

class BrowseDirectoryRequest(BaseModel):
    path: Optional[str] = None
