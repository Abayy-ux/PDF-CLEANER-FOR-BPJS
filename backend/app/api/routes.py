import asyncio
import json
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pathlib import Path
from ..models.schemas import (
    ScanRequest,
    ScanResponse,
    ProcessBatchRequest,
    BatchJobStatus,
    InspectRequest,
)
from ..services.fs_scanner import scan_directory
from ..services.batch_processor import batch_manager
from ..pdf.inspector import inspect_pdf_structure
from ..utils.logger import app_logger

router = APIRouter(prefix="/api", tags=["PDF Normalizer"])

@router.post("/scan", response_model=ScanResponse)
def scan_folder(req: ScanRequest) -> ScanResponse:
    """Scans directory for eligible PDF files and categorizes ignored files."""
    path = Path(req.source_dir).resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {req.source_dir}")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {req.source_dir}")

    result = scan_directory(path, recursive=req.recursive)
    dict_res = result.to_dict()
    return ScanResponse(
        source_dir=str(path),
        eligible_count=dict_res["eligible_count"],
        eligible_files=dict_res["eligible_files"],
        total_eligible_size=dict_res["total_eligible_size"],
        ignored_count=dict_res["ignored_count"],
        ignored_files=dict_res["ignored_files"],
    )

@router.post("/process", response_model=BatchJobStatus)
async def start_batch_process(req: ProcessBatchRequest, background_tasks: BackgroundTasks) -> BatchJobStatus:
    """Initializes and starts an asynchronous batch PDF normalization job."""
    src = Path(req.source_dir).resolve()
    if not src.exists() or not src.is_dir():
        raise HTTPException(status_code=400, detail="Invalid source directory")

    job = batch_manager.create_job(req)
    if job.total_files == 0:
        raise HTTPException(status_code=400, detail="No eligible PDF files found in source directory")

    # Run batch processing in background task
    background_tasks.add_task(batch_manager.run_job, job)
    return job.to_status()

@router.get("/jobs/{job_id}", response_model=BatchJobStatus)
def get_job_status(job_id: str) -> BatchJobStatus:
    """Fetches current snapshot status of a batch job."""
    job = batch_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_status()

@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    """Cancels an active or queued batch normalization job."""
    ok = batch_manager.cancel_job(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled or was not found")
    return {"message": "Job cancellation requested", "job_id": job_id}

@router.get("/jobs/{job_id}/stream")
async def stream_job_events(job_id: str):
    """
    Server-Sent Events (SSE) stream for real-time progress and live file log updates.
    """
    job = batch_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        # Send initial full status
        init_data = json.dumps({"type": "init", "data": job.to_status().model_dump()})
        yield f"data: {init_data}\n\n"

        while True:
            try:
                # Wait for next event with a timeout for heartbeat ping
                event = await asyncio.wait_for(job.event_queue.get(), timeout=15.0)
                yield f"data: {json.dumps(event)}\n\n"

                if event.get("type") in ("job_completed", "job_cancelled"):
                    break
            except asyncio.TimeoutError:
                # Heartbeat to keep connection alive
                yield f": heartbeat\n\n"
                if job.status in ("completed", "cancelled", "failed"):
                    break
            except asyncio.CancelledError:
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.post("/inspect")
def inspect_single_pdf(req: InspectRequest):
    """Performs deep structural inspection on a single PDF file."""
    path = Path(req.file_path).resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="PDF file not found")
    
    result = inspect_pdf_structure(path)
    return result.to_dict()
