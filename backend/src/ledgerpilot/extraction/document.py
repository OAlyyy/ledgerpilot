"""Load a PDF as either text or page images.

Digital PDFs have a text layer, and sending text is cheaper, faster and more
accurate than sending pixels. Scans have no text layer, so we render the pages
and use a vision-capable model. The decision is a simple threshold on the
amount of extractable text.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image

MIN_TEXT_CHARS = 40
RENDER_SCALE = 2.0  # 144 dpi: enough for small receipt fonts, still a modest image


@dataclass
class Document:
    path: Path
    text: str | None  # None means "no usable text layer"
    images: list[bytes] = field(default_factory=list)  # PNG per page, only for scans

    @property
    def method(self) -> str:
        return "text" if self.text is not None else "vision"


def load_document(path: Path, max_pages: int = 4) -> Document:
    with pdfplumber.open(path) as pdf:
        pages = pdf.pages[:max_pages]
        text = "\n\n".join(p.extract_text(layout=False) or "" for p in pages).strip()
    if len(text) >= MIN_TEXT_CHARS:
        return Document(path=path, text=text)
    return Document(path=path, text=None, images=_render(path, max_pages))


def _render(path: Path, max_pages: int) -> list[bytes]:
    pdf = pdfium.PdfDocument(str(path))
    images = []
    for i in range(min(len(pdf), max_pages)):
        buf = io.BytesIO()
        _crop_to_content(pdf[i].render(scale=RENDER_SCALE).to_pil().convert("L")).save(
            buf, format="PNG", optimize=True
        )
        images.append(buf.getvalue())
    pdf.close()
    return images


def _crop_to_content(img: Image.Image, margin: int = 24) -> Image.Image:
    """Cut away blank paper around the text.

    Vision models downscale every image to a fixed token budget. A receipt in the
    top third of an A4 page would otherwise get a third of the resolution, and
    small digits become unreadable.
    """
    ink = img.point(lambda p: 255 if p < 160 else 0)  # dark pixels = content
    box = ink.getbbox()
    if box is None:
        return img
    left, top, right, bottom = box
    return img.crop(
        (
            max(left - margin, 0),
            max(top - margin, 0),
            min(right + margin, img.width),
            min(bottom + margin, img.height),
        )
    )
