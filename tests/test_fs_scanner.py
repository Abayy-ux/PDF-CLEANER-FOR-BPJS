from pathlib import Path
import pytest
from backend.app.services.fs_scanner import scan_directory, is_eligible_pdf

def test_ignored_macos_and_system_files(tmp_path: Path):
    # Setup test directory with mix of valid and ignored files
    (tmp_path / "001.pdf").write_bytes(b"%PDF-1.4 test 1")
    (tmp_path / "002.PDF").write_bytes(b"%PDF-1.4 test 2")
    (tmp_path / "003.Pdf").write_bytes(b"%PDF-1.4 test 3")
    
    # Ignored files
    (tmp_path / "._001.pdf").write_bytes(b"AppleDouble resource fork")
    (tmp_path / "._002.PDF").write_bytes(b"AppleDouble resource fork")
    (tmp_path / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
    (tmp_path / "Thumbs.db").write_bytes(b"thumbs binary")
    (tmp_path / "notes.txt").write_text("plain text")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / ".hidden.pdf").write_bytes(b"%PDF hidden")

    res = scan_directory(tmp_path)
    
    eligible_names = [f.name for f in res.eligible_files]
    assert sorted(eligible_names) == ["001.pdf", "002.PDF", "003.Pdf"]
    assert len(res.eligible_files) == 3
    assert res.to_dict()["eligible_count"] == 3
    assert res.to_dict()["ignored_count"] == 7

def test_is_eligible_pdf_rules():
    assert is_eligible_pdf(Path("sample.pdf"))[0] is True
    assert is_eligible_pdf(Path("REPORT.PDF"))[0] is True
    
    # AppleDouble
    ok, reason = is_eligible_pdf(Path("._sample.pdf"))
    assert ok is False
    assert "AppleDouble" in reason

    # .DS_Store
    ok, reason = is_eligible_pdf(Path(".DS_Store"))
    assert ok is False

    # Thumbs.db
    ok, reason = is_eligible_pdf(Path("Thumbs.db"))
    assert ok is False

    # Non-PDF
    ok, reason = is_eligible_pdf(Path("data.csv"))
    assert ok is False
