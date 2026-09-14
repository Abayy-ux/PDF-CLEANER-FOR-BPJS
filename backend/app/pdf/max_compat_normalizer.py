from pathlib import Path
from typing import Dict, Any, Tuple, List
import io
import fitz  # PyMuPDF
from PIL import Image
from .asciihex import encode_asciihex
from ..utils.logger import app_logger

class CleanAsciiHexPdfBuilder:
    """
    Constructs a pristine, valid PDF 1.4+ file from rendered page images.
    Each page contains exactly one Image XObject encoded with ASCIIHex.
    Contains zero annotations, zero JavaScript, zero form fields, and zero active actions.
    """
    def __init__(self):
        self.objects: List[bytes] = []
        self.offsets: List[int] = []

    def _add_object(self, obj_bytes: bytes) -> int:
        obj_num = len(self.objects) + 1
        self.objects.append(obj_bytes)
        return obj_num

    def build_pdf(self, page_data_list: List[Dict[str, Any]]) -> bytes:
        """
        page_data_list elements:
        {
          "width_pts": float,
          "height_pts": float,
          "pixel_width": int,
          "pixel_height": int,
          "hex_stream": bytes,
          "is_dct": bool
        }
        """
        out = io.BytesIO()
        out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

        # Object references to be populated
        total_pages = len(page_data_list)
        
        # Object 1: Catalog
        # Object 2: Pages
        # For each page:
        #   Obj (2 + i*3 + 1): Page Object
        #   Obj (2 + i*3 + 2): Content Stream
        #   Obj (2 + i*3 + 3): Image XObject

        page_obj_nums = [2 + i * 3 + 1 for i in range(total_pages)]

        # Object 1: Catalog
        catalog_obj = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        
        # Object 2: Pages
        kids_refs = " ".join(f"{num} 0 R" for num in page_obj_nums)
        pages_obj = f"2 0 obj\n<< /Type /Pages /Kids [{kids_refs}] /Count {total_pages} >>\nendobj\n".encode("ascii")

        raw_objects: List[bytes] = [catalog_obj, pages_obj]

        for i, page_data in enumerate(page_data_list):
            page_obj_num = 2 + i * 3 + 1
            content_obj_num = 2 + i * 3 + 2
            image_obj_num = 2 + i * 3 + 3

            w_pts = page_data["width_pts"]
            h_pts = page_data["height_pts"]
            px_w = page_data["pixel_width"]
            px_h = page_data["pixel_height"]
            hex_stream = page_data["hex_stream"]
            is_dct = page_data["is_dct"]

            # Content stream to paint image over entire page MediaBox
            content_stream_data = (
                f"q\n{w_pts:.4f} 0 0 {h_pts:.4f} 0 0 cm\n/Im0 Do\nQ\n"
            ).encode("ascii")
            content_len = len(content_stream_data)

            content_obj = (
                f"{content_obj_num} 0 obj\n"
                f"<< /Length {content_len} >>\n"
                f"stream\n"
            ).encode("ascii") + content_stream_data + b"endstream\nendobj\n"

            # Image XObject with ASCIIHexDecode (and DCTDecode if JPEG compressed)
            if is_dct:
                filter_entry = "/Filter [/ASCIIHexDecode /DCTDecode]"
            else:
                filter_entry = "/Filter /ASCIIHexDecode"

            stream_len = len(hex_stream)
            image_header = (
                f"{image_obj_num} 0 obj\n"
                f"<< /Type /XObject\n"
                f"   /Subtype /Image\n"
                f"   /Width {px_w}\n"
                f"   /Height {px_h}\n"
                f"   /ColorSpace /DeviceRGB\n"
                f"   /BitsPerComponent 8\n"
                f"   {filter_entry}\n"
                f"   /Length {stream_len}\n"
                f">>\n"
                f"stream\n"
            ).encode("ascii")
            image_obj = image_header + hex_stream + b"endstream\nendobj\n"

            # Page Object
            page_obj = (
                f"{page_obj_num} 0 obj\n"
                f"<< /Type /Page\n"
                f"   /Parent 2 0 R\n"
                f"   /MediaBox [0 0 {w_pts:.4f} {h_pts:.4f}]\n"
                f"   /Resources <<\n"
                f"     /ProcSet [/PDF /ImageC /ImageB /ImageI]\n"
                f"     /XObject << /Im0 {image_obj_num} 0 R >>\n"
                f"   >>\n"
                f"   /Contents {content_obj_num} 0 R\n"
                f">>\n"
                f"endobj\n"
            ).encode("ascii")

            raw_objects.extend([page_obj, content_obj, image_obj])

        # Write objects and track offsets
        offsets = [0]  # Object 0 dummy
        for obj in raw_objects:
            offsets.append(out.tell())
            out.write(obj)

        # Cross-reference table
        xref_start = out.tell()
        total_count = len(offsets)
        out.write(f"xref\n0 {total_count}\n".encode("ascii"))
        out.write(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            out.write(f"{off:010d} 00000 n \n".encode("ascii"))

        # Trailer
        trailer = (
            f"trailer\n"
            f"<< /Size {total_count}\n"
            f"   /Root 1 0 R\n"
            f">>\n"
            f"startxref\n"
            f"{xref_start}\n"
            f"%%EOF\n"
        ).encode("ascii")
        out.write(trailer)

        return out.getvalue()

def normalize_max_compat_pdf(
    input_path: Path | str, 
    output_path: Path | str, 
    dpi: int = 200,
    jpeg_quality: int = 92
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Maximum Compatibility Mode Normalizer.
    1. Renders each page to high-quality image preserving dimensions and orientation.
    2. Encodes each rendered page image using ASCIIHex.
    3. Builds a clean, simplified 1-image/page PDF structure with zero active features.
    
    Returns (success, message, metadata).
    """
    src = Path(input_path).resolve()
    dst = Path(output_path).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    stats = {
        "method": "FALLBACK / ASCIIHEX",
        "original_size": src.stat().st_size if src.exists() else 0,
        "output_size": 0,
        "page_count": 0,
        "dpi": dpi,
        "rendered_pages": 0,
    }

    try:
        doc = fitz.open(str(src))
        total_pages = len(doc)
        stats["page_count"] = total_pages

        if total_pages == 0:
            doc.close()
            return False, "Source PDF has 0 pages", stats

        page_data_list = []

        for page_idx in range(total_pages):
            page = doc[page_idx]
            rect = page.rect
            width_pts = float(rect.width)
            height_pts = float(rect.height)

            # Render page at exact DPI with high visual fidelity
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            img_bytes = pix.tobytes("jpeg", jpg_quality=jpeg_quality)

            # Encode image bytes into ASCIIHex stream
            hex_stream = encode_asciihex(img_bytes)

            page_data_list.append({
                "width_pts": width_pts,
                "height_pts": height_pts,
                "pixel_width": pix.width,
                "pixel_height": pix.height,
                "hex_stream": hex_stream,
                "is_dct": True,
            })
            stats["rendered_pages"] += 1

        doc.close()

        # Build clean PDF bytes
        builder = CleanAsciiHexPdfBuilder()
        clean_pdf_bytes = builder.build_pdf(page_data_list)

        with open(dst, "wb") as f_out:
            f_out.write(clean_pdf_bytes)

        stats["output_size"] = dst.stat().st_size
        return True, "Maximum Compatibility ASCIIHex normalization completed successfully", stats

    except Exception as e:
        app_logger.error(f"Max compat normalization failed for {src.name}: {e}")
        if dst.exists():
            dst.unlink(missing_ok=True)
        return False, f"Maximum compatibility normalization error: {str(e)}", stats
