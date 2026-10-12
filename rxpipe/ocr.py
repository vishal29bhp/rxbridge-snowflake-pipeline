"""Turning a file into text, offline.

Two independent ways to read the same document, so the verifier is not just
the extractor run twice (the same reader repeats the same mistakes):

  read_primary   - PDF text layer if there is one; otherwise OCR (Tesseract, page mode 6)
  read_secondary - always renders/cleans the image and OCRs it (Tesseract, page mode 4)

A scanned PDF or a phone photo has no text layer, so both paths OCR it, but with
different preprocessing and page-segmentation settings.
"""

from __future__ import annotations

import io

from PIL import Image, ImageFilter, ImageOps

MIN_TEXT_CHARS_PER_PAGE = 40  # below this, the "text layer" is empty or junk


class UnreadableDocument(Exception):
    """Raised for corrupt, empty or encrypted files. The extract stage retries, then quarantines."""


def _tesseract(img: Image.Image, psm: int) -> str:
    import pytesseract

    return pytesseract.image_to_string(img, config=f"--psm {psm}")


def _prepare(img: Image.Image, binarise: bool) -> Image.Image:
    img = ImageOps.exif_transpose(img).convert("L")  # respect phone rotation, greyscale
    if img.width < 1500:  # small photos OCR badly; upscale
        scale = 1500 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    if binarise:
        img = img.filter(ImageFilter.MedianFilter(3)).point(lambda p: 255 if p > 160 else 0)
    return img


def _pdf_pages_as_images(data: bytes, dpi: int = 200) -> list[Image.Image]:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except Exception as exc:
        raise UnreadableDocument(f"cannot open PDF: {exc}") from exc
    if len(pdf) == 0:
        raise UnreadableDocument("PDF has no pages")
    return [page.render(scale=dpi / 72).to_pil() for page in pdf]


def _pdf_text_layer(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [p.extract_text() or "" for p in reader.pages]
    except Exception as exc:
        raise UnreadableDocument(f"cannot open PDF: {exc}") from exc
    if not pages:
        raise UnreadableDocument("PDF has no pages")
    return "\n".join(pages), len(pages)


def _open_image(data: bytes) -> list[Image.Image]:
    try:
        img = Image.open(io.BytesIO(data))
        frames = []
        for i in range(getattr(img, "n_frames", 1)):  # multi-page TIFF scans
            img.seek(i)
            frames.append(img.copy())
        return frames
    except Exception as exc:
        raise UnreadableDocument(f"cannot open image: {exc}") from exc


def read_primary(data: bytes, mime: str) -> tuple[str, str]:
    """Returns (text, method). method is 'text_layer' or 'ocr'."""
    if mime == "application/pdf":
        text, n_pages = _pdf_text_layer(data)
        if len(text.strip()) >= MIN_TEXT_CHARS_PER_PAGE * n_pages:
            return text, "text_layer"
        images = _pdf_pages_as_images(data)  # scanned PDF: no usable text layer
    else:
        images = _open_image(data)
    return "\n".join(_tesseract(_prepare(im, binarise=False), psm=6) for im in images), "ocr"


def read_secondary(data: bytes, mime: str) -> str:
    images = _pdf_pages_as_images(data) if mime == "application/pdf" else _open_image(data)
    return "\n".join(_tesseract(_prepare(im, binarise=True), psm=4) for im in images)
