"""Make a clean PDF look like a phone photo / cheap scan of a paper receipt.

The output is an image-only PDF: no text layer, so extraction has to go
through a vision model (or OCR). That is the point of the scan scenario.
"""

from __future__ import annotations

import io
import random
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageEnhance, ImageFilter


def degrade_to_scan(pdf_path: Path, rng: random.Random) -> None:
    pdf = pdfium.PdfDocument(str(pdf_path))
    pages: list[Image.Image] = []
    for page in pdf:
        img = page.render(scale=1.5).to_pil().convert("L")  # ~108 dpi greyscale
        img = img.rotate(
            rng.uniform(-2.5, 2.5), expand=True, fillcolor=235, resample=Image.Resampling.BICUBIC
        )
        img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.6, 1.2)))
        img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.7, 0.9))
        img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.9, 1.05))
        img = _add_noise(img, rng, amount=rng.randint(8, 18))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=rng.randint(30, 45))  # compression artefacts
        pages.append(Image.open(io.BytesIO(buf.getvalue())).convert("L"))
    pdf.close()
    pages[0].save(pdf_path, format="PDF", save_all=True, append_images=pages[1:], resolution=108)


def _add_noise(img: Image.Image, rng: random.Random, amount: int) -> Image.Image:
    """Salt-and-pepper-ish sensor noise, deterministic for a given rng."""
    noise = Image.frombytes(
        "L", img.size, bytes(rng.randint(128 - amount, 128 + amount) for _ in range(img.width * img.height))
    )
    return Image.blend(img, noise, alpha=0.12)
