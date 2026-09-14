import asyncio
import uuid
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, AsyncGenerator
from ..models.schemas import BatchJobStatus, FileProcessResultItem, ProcessBatchRequest
from ..pdf.pipeline import process_single_pdf, ProcessingMode
from ..services.fs_scanner import scan_directory
from ..utils.path_utils import resolve_clean_output_path
from ..utils.logger import app_logger

class BatchJob:
    def __init__(self, job_id: str, request: ProcessBatchRequest, files_to_process: List[Path]):
        self.job_id = job_id
        self.request = request
        self.files_to_process = files_to_process
        self.source_dir = str(Path(request.source_dir).resolve())
        self.output_dir = str(Path(request.output_dir).resolve())
        self.mode = request.mode
        self.total_files = len(files_to_process)
        self.processed_files = 0
        self.success_count = 0
        self.fallback_count = 0
        self.failed_count = 0
        self.status = "queued"  # queued, running, completed, cancelled, failed
        self.current_file: Optional[str] = None
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.results: List[FileProcessResultItem] = []
        self.is_cancelled = False
        self.event_queue: asyncio.Queue = asyncio.Queue()

    @property
    def progress_percentage(self) -> float:
        if self.total_files == 0:
            return 100.0
        return round((self.processed_files / self.total_files) * 100.0, 1)

    @property
    def elapsed_seconds(self) -> float:
        if not self.start_time:
            return 0.0
        end = self.end_time or time.time()
        return round(end - self.start_time, 2)

    def to_status(self) -> BatchJobStatus:
        return BatchJobStatus(
            job_id=self.job_id,
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            mode=self.mode.value if hasattr(self.mode, "value") else str(self.mode),
            status=self.status,
            total_files=self.total_files,
            processed_files=self.processed_files,
            success_count=self.success_count,
            fallback_count=self.fallback_count,
            failed_count=self.failed_count,
            progress_percentage=self.progress_percentage,
            current_file=self.current_file,
            start_time=self.start_time,
            end_time=self.end_time,
            elapsed_seconds=self.elapsed_seconds,
            results=self.results,
        )

    async def push_event(self, event_type: str, data: Dict[str, Any]):
        await self.event_queue.put({"type": event_type, "data": data})

class BatchJobManager:
    def __init__(self):
        self.jobs: Dict[str, BatchJob] = {}

    def create_job(self, request: ProcessBatchRequest) -> BatchJob:
        job_id = str(uuid.uuid4())
        scan_res = scan_directory(request.source_dir, recursive=request.recursive)
        files = scan_res.eligible_files

        job = BatchJob(job_id, request, files)
        self.jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[BatchJob]:
        return self.jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if job and job.status in ("queued", "running"):
            job.is_cancelled = True
            job.status = "cancelled"
            job.end_time = time.time()
            return True
        return False

    async def run_job(self, job: BatchJob):
        job.status = "running"
        job.start_time = time.time()
        out_dir = Path(job.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        await job.push_event("job_started", job.to_status().model_dump())

        for idx, src_file in enumerate(job.files_to_process):
            if job.is_cancelled:
                job.status = "cancelled"
                break

            job.current_file = src_file.name
            await job.push_event("file_started", {
                "index": idx + 1,
                "total": job.total_files,
                "filename": src_file.name
            })

            # Determine output path (uses custom suffix or original filename)
            target_path = resolve_clean_output_path(
                out_dir, 
                src_file, 
                suffix=job.request.filename_suffix, 
                overwrite_existing=job.request.overwrite_existing
            )

            # Run single PDF process in thread pool to avoid blocking asyncio event loop
            try:
                result = await asyncio.to_thread(
                    process_single_pdf,
                    source_path=src_file,
                    target_path=target_path,
                    mode=job.mode,
                    dpi=job.request.dpi,
                    jpeg_quality=job.request.jpeg_quality
                )
            except Exception as e:
                app_logger.error(f"Unexpected error processing {src_file.name}: {e}")
                result = None

            job.processed_files += 1

            if result:
                item = FileProcessResultItem(
                    filename=result.filename,
                    mode=result.mode if isinstance(result.mode, str) else result.mode.value,
                    status=result.status,
                    method_used=result.method_used,
                    stage=result.stage,
                    original_size=result.original_size,
                    output_size=result.output_size,
                    page_count=result.page_count,
                    processing_time_ms=result.processing_time_ms,
                    error=result.error,
                    fallback_reason=result.fallback_reason,
                    details=result.details
                )
                job.results.append(item)

                if result.status == "success":
                    job.success_count += 1
                elif result.status == "fallback":
                    job.fallback_count += 1
                else:
                    job.failed_count += 1

                await job.push_event("file_completed", item.model_dump())
            else:
                job.failed_count += 1
                item = FileProcessResultItem(
                    filename=src_file.name,
                    mode=job.mode.value if hasattr(job.mode, "value") else str(job.mode),
                    status="failed",
                    method_used="FAILED",
                    stage="execution",
                    original_size=src_file.stat().st_size if src_file.exists() else 0,
                    output_size=0,
                    page_count=0,
                    processing_time_ms=0.0,
                    error="Internal pipeline unhandled exception"
                )
                job.results.append(item)
                await job.push_event("file_completed", item.model_dump())

            # Small yield to event loop
            await asyncio.sleep(0.01)

        if not job.is_cancelled:
            job.status = "completed"
        job.end_time = time.time()
        job.current_file = None

        await job.push_event("job_completed", job.to_status().model_dump())

batch_manager = BatchJobManager()
