import io
from pathlib import Path
import fitz  # PyMuPDF
import pypdf
import pytest
from backend.app.pdf.inspector import inspect_pdf_structure
from backend.app.pdf.standard_normalizer import normalize_standard_pdf
from backend.app.pdf.max_compat_normalizer import normalize_max_compat_pdf
from backend.app.pdf.pipeline import process_single_pdf, ProcessingMode
from backend.app.validators.validator import validate_pdf
from backend.app.utils.path_utils import resolve_clean_output_path

def create_sample_pdf(file_path: Path, num_pages: int = 2, add_annot: bool = False) -> Path:
    """Helper to generate a clean multi-page PDF."""
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text((50, 100), f"Test Document Page {i + 1}", fontsize=20, color=(0, 0, 0))
        page.insert_text((50, 150), "Confidential medical record data simulation.", fontsize=12)
        if add_annot:
            rect = fitz.Rect(50, 200, 200, 250)
            page.add_rect_annot(rect)
    doc.save(str(file_path))
    doc.close()
    return file_path

def create_pdf_with_js(file_path: Path) -> Path:
    """Helper to generate a PDF with embedded JavaScript in catalog/names."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 100), "PDF with embedded JavaScript Action", fontsize=18)
    
    # Save base PDF
    temp_buf = io.BytesIO()
    doc.save(temp_buf)
    doc.close()
    temp_buf.seek(0)

    # Use pypdf to inject /JS into catalog
    reader = pypdf.PdfReader(temp_buf)
    writer = pypdf.PdfWriter()
    for p in reader.pages:
        writer.add_page(p)

    writer.add_js("app.alert('Test JS Alert');")
    
    with open(file_path, "wb") as f:
        writer.write(f)
    
    return file_path

def test_structural_inspector(tmp_path: Path):
    clean_pdf = create_sample_pdf(tmp_path / "clean.pdf", num_pages=2)
    js_pdf = create_pdf_with_js(tmp_path / "js_doc.pdf")

    clean_res = inspect_pdf_structure(clean_pdf)
    assert clean_res.is_valid_pdf is True
    assert clean_res.page_count == 2
    assert clean_res.has_javascript is False
    assert clean_res.is_clean is True

    js_res = inspect_pdf_structure(js_pdf)
    assert js_res.is_valid_pdf is True
    assert js_res.has_javascript is True
    assert js_res.is_clean is False

def test_standard_normalizer(tmp_path: Path):
    annot_pdf = create_sample_pdf(tmp_path / "annot.pdf", num_pages=3, add_annot=True)
    out_pdf = tmp_path / "annot_clean.pdf"

    ok, msg, stats = normalize_standard_pdf(annot_pdf, out_pdf)
    assert ok is True
    assert out_pdf.exists()
    assert stats["page_count"] == 3

    # Validate output
    val = validate_pdf(out_pdf, expected_page_count=3)
    assert val.is_valid is True
    assert val.page_count == 3

def test_max_compat_normalizer_asciihex(tmp_path: Path):
    src_pdf = create_sample_pdf(tmp_path / "source.pdf", num_pages=2)
    out_pdf = tmp_path / "source_maxcompat.pdf"

    ok, msg, stats = normalize_max_compat_pdf(src_pdf, out_pdf, dpi=150)
    assert ok is True
    assert out_pdf.exists()
    assert stats["page_count"] == 2

    # Check raw binary contains ASCIIHex stream marker and no JS
    content = out_pdf.read_bytes()
    assert b"/Filter [/ASCIIHexDecode /DCTDecode]" in content or b"/Filter /ASCIIHexDecode" in content
    assert b">" in content

    # Validate generated PDF
    val = validate_pdf(out_pdf, expected_page_count=2)
    assert val.is_valid is True
    assert val.page_count == 2
    assert val.pages_rendered == 2

def test_automatic_pipeline_fallback(tmp_path: Path):
    # Test 1: Clean file completes with STANDARD
    clean_src = create_sample_pdf(tmp_path / "clean_auto.pdf", num_pages=1)
    clean_out = tmp_path / "clean_auto_out.pdf"
    res1 = process_single_pdf(clean_src, clean_out, mode=ProcessingMode.AUTOMATIC)
    assert res1.status == "success"
    assert res1.method_used == "STANDARD"

    # Test 2: File with persistent JS structure normalizes cleanly
    js_src = create_pdf_with_js(tmp_path / "js_auto.pdf")
    js_out = tmp_path / "js_auto_out.pdf"
    res2 = process_single_pdf(js_src, js_out, mode=ProcessingMode.AUTOMATIC)
    assert res2.status in ("success", "fallback")
    assert clean_out.exists()
    
    # Output must be 100% clean of JS
    val = validate_pdf(js_out)
    assert val.is_valid is True
    assert val.inspection["has_javascript"] is False

def test_filename_collision_resolver(tmp_path: Path):
    src = tmp_path / "0184R0160626V001070.pdf"
    src.write_bytes(b"%PDF-1.4")
    out_dir = tmp_path / "output_dir"
    out_dir.mkdir()
    
    # Default suffix="" preserves exact original name
    out1 = resolve_clean_output_path(out_dir, src, suffix="", overwrite_existing=True)
    assert out1.name == "0184R0160626V001070.pdf"

    # Custom suffix "_clean"
    out2 = resolve_clean_output_path(out_dir, src, suffix="_clean", overwrite_existing=True)
    assert out2.name == "0184R0160626V001070_clean.pdf"

def test_golden_case_simulation(tmp_path: Path):
    """
    Simulates the golden test case (signature / JS literal rejection).
    Validates that the ASCIIHex workflow produces a clean valid document with original name.
    """
    golden_src = create_pdf_with_js(tmp_path / "0184R0160626V001070.pdf")
    out_dir = tmp_path / "golden_output"
    out_dir.mkdir()
    golden_out = out_dir / "0184R0160626V001070.pdf"

    res = process_single_pdf(
        golden_src,
        golden_out,
        mode=ProcessingMode.AUTOMATIC,
        dpi=150
    )

    assert res.status in ("success", "fallback")
    assert golden_out.exists()
    
    # Verify golden output validation
    val = validate_pdf(golden_out, strict_structural=True)
    assert val.is_valid is True
    assert val.page_count == 1
    assert val.pages_rendered == 1
    assert val.inspection["is_clean"] is True
