from pathlib import Path
import pytest
import asyncio
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.models.schemas import ProcessBatchRequest
from backend.app.services.batch_processor import BatchJobManager
from backend.app.pdf.pipeline import ProcessingMode
import fitz

client = TestClient(app)

def create_dummy_pdf(path: Path, text: str = "Test") -> Path:
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((50, 50), text)
    doc.save(str(path))
    doc.close()
    return path

def test_api_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "PDF Safe Normalizer"

def test_api_diagnostics():
    response = client.get("/api/system/diagnostics")
    assert response.status_code == 200
    data = response.json()
    assert "engines" in data
    assert data["engines"]["pymupdf"]["available"] is True
    assert data["engines"]["pypdf"]["available"] is True
    assert data["engines"]["pillow"]["available"] is True

def test_api_scan_directory(tmp_path: Path):
    create_dummy_pdf(tmp_path / "doc1.pdf")
    create_dummy_pdf(tmp_path / "doc2.PDF")
    (tmp_path / "._doc1.pdf").write_bytes(b"junk")
    (tmp_path / "notes.txt").write_text("info")

    response = client.post("/api/scan", json={"source_dir": str(tmp_path)})
    assert response.status_code == 200
    data = response.json()
    assert data["eligible_count"] == 2
    assert data["ignored_count"] == 2

@pytest.mark.asyncio
async def test_batch_processor_error_isolation(tmp_path: Path):
    src_dir = tmp_path / "src"
    out_dir = tmp_path / "out"
    src_dir.mkdir()
    out_dir.mkdir()

    # 3 valid PDFs
    create_dummy_pdf(src_dir / "001.pdf", "Valid PDF 1")
    create_dummy_pdf(src_dir / "002.pdf", "Valid PDF 2")
    create_dummy_pdf(src_dir / "003.pdf", "Valid PDF 3")
    
    # 1 corrupt fake PDF that will fail
    (src_dir / "004_corrupt.pdf").write_bytes(b"CORRUPT_NOT_A_PDF_STREAM_12345")

    mgr = BatchJobManager()
    req = ProcessBatchRequest(
        source_dir=str(src_dir),
        output_dir=str(out_dir),
        mode=ProcessingMode.AUTOMATIC,
        dpi=150
    )
    job = mgr.create_job(req)
    assert job.total_files == 4

    await mgr.run_job(job)

    # Batch must complete despite failure in 004_corrupt.pdf!
    assert job.status == "completed"
    assert job.processed_files == 4
    assert job.success_count + job.fallback_count == 3
    assert job.failed_count == 1

    # Verify clean outputs exist with original filenames
    assert (out_dir / "001.pdf").exists()
    assert (out_dir / "002.pdf").exists()
    assert (out_dir / "003.pdf").exists()
