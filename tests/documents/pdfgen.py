import io
from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


@dataclass(frozen=True)
class Scan:
    text: str


def scan_image(text: str) -> Image.Image:
    img = Image.new("L", (1240, 1754), 255)
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=42)
    for i, line in enumerate(text.split("\n")):
        d.text((80, 100 + i * 70), line, fill=0, font=font)
    return img


def make_pdf(pages: Sequence[str | Scan], title: str = "t", password: str | None = None) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1, pageCompression=0)
    c.setTitle(title)
    if password:
        from reportlab.lib.pdfencrypt import StandardEncryption

        c._doc.encrypt = StandardEncryption(password)
    w, h = A4
    for p in pages:
        if isinstance(p, Scan):
            c.drawImage(ImageReader(scan_image(p.text)), 0, 0, width=w, height=h)
        else:
            c.setFont("Helvetica", 10)
            for i, line in enumerate(p.split("\n")):
                c.drawString(60, h - 60 - i * 13, line)
        c.showPage()
    c.save()
    return buf.getvalue()
