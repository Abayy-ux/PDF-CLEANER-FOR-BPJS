from pathlib import Path
from typing import Dict, Any, Tuple
import fitz  # PyMuPDF
import pypdf
from ..utils.logger import app_logger

def normalize_standard_pdf(input_path: Path | str, output_path: Path | str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Standard Mode Normalizer.
    Removes dangerous/problematic PDF structures while preserving vector paths,
    fonts, visual layout, and text layers.
    
    Returns (success, message, metadata).
    """
    src = Path(input_path).resolve()
    dst = Path(output_path).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    stats = {
        "method": "STANDARD",
        "original_size": src.stat().st_size if src.exists() else 0,
        "output_size": 0,
        "page_count": 0,
        "removed_structures": [],
    }

    temp_intermediate = dst.with_name(f"{dst.stem}_std_temp{dst.suffix}")

    try:
        # Step 1: Open with PyMuPDF for structural scrubbing
        doc = fitz.open(str(src))
        stats["page_count"] = len(doc)

        if doc.is_encrypted and doc.needs_pass:
            doc.close()
            return False, "Cannot normalize password-protected PDF", stats

        # Remove embedded files
        if doc.embfile_count() > 0:
            stats["removed_structures"].append(f"{doc.embfile_count()} Embedded Files")
            # In PyMuPDF, embfile_del can be called or scrub handles it

        # Remove / neutralize annotations and widgets from all pages
        total_annots_removed = 0
        for page in doc:
            # Delete annotations
            annots = list(page.annots())
            for annot in annots:
                try:
                    page.delete_annot(annot)
                    total_annots_removed += 1
                except Exception:
                    pass

            # Delete form widgets / fields
            widgets = list(page.widgets())
            for widget in widgets:
                try:
                    page.delete_widget(widget)
                    total_annots_removed += 1
                except Exception:
                    pass

        if total_annots_removed > 0:
            stats["removed_structures"].append(f"{total_annots_removed} Annotations/Widgets")

        # PyMuPDF doc.scrub removes javascript, embedded files, metadata scripts, etc.
        try:
            doc.scrub(
                attached_files=True,
                clean_pages=True,
                embedded_files=True,
                javascript_actions=True,
                reset_fields=True,
                reset_responses=True,
                xml_metadata=True,
            )
            stats["removed_structures"].append("Scrubbed Active Actions & JS")
        except Exception as scrub_err:
            app_logger.debug(f"PyMuPDF scrub note: {scrub_err}")

        # Save scrubbed intermediate
        doc.save(
            str(temp_intermediate),
            garbage=4,
            deflate=True,
            clean=True,
            linear=False
        )
        doc.close()

        # Step 2: Use pypdf to do deep catalog-level cleaning and strip any remaining /OpenAction, /AA, /Names, /AcroForm
        reader = pypdf.PdfReader(str(temp_intermediate), strict=False)
        writer = pypdf.PdfWriter()

        # Copy all pages
        for page in reader.pages:
            # Clean page-level /AA or /Annots if any remain
            if "/AA" in page:
                del page["/AA"]
                stats["removed_structures"].append("Page /AA")
            if "/Annots" in page:
                del page["/Annots"]
            writer.add_page(page)

        # Sanitize root catalog
        root = writer.root_object
        keys_to_remove = ["/OpenAction", "/AA", "/Names", "/AcroForm", "/JavaScript", "/JS", "/Launch", "/XFA", "/PieceInfo"]
        for key in keys_to_remove:
            if key in root:
                del root[key]
                stats["removed_structures"].append(f"Catalog {key}")

        # Deduplicate removed structures list
        stats["removed_structures"] = list(dict.fromkeys(stats["removed_structures"]))

        with open(dst, "wb") as f_out:
            writer.write(f_out)

        # Cleanup temp file
        if temp_intermediate.exists():
            temp_intermediate.unlink(missing_ok=True)

        stats["output_size"] = dst.stat().st_size
        return True, "Standard normalization completed successfully", stats

    except Exception as e:
        app_logger.error(f"Standard normalization failed for {src.name}: {e}")
        if temp_intermediate.exists():
            temp_intermediate.unlink(missing_ok=True)
        if dst.exists():
            dst.unlink(missing_ok=True)
        return False, f"Standard normalization error: {str(e)}", stats
