"""Private (link only) store listings: the link, its QR code, a printable sign.

A private listing is left off /store and sold only to people who open its
own link, e.g. by scanning the QR code at an in-person event.
"""

from io import BytesIO

import segno

from services.store_checkout import _site_url

PRIVATE_PATH = "/store/p/"


def private_url(token: str) -> str:
    """Full link to a private listing's page."""
    return _site_url(f"{PRIVATE_PATH}{token}")


def qr_png(url: str, scale: int = 16) -> bytes:
    """Black-on-white QR code PNG with a quiet zone, big enough to print."""
    buf = BytesIO()
    # Error level Q survives a scuffed or partly covered print
    segno.make(url, error="q", micro=False).save(
        buf, kind="png", scale=scale, border=4, dark="#000000", light="#ffffff",
    )
    return buf.getvalue()


def _fit(c, text: str, font: str, size: float, width: float) -> float:
    """Largest font size up to `size` that fits `text` in `width`."""
    while size > 8 and c.stringWidth(text, font, size) > width:
        size -= 1
    return size


def sign_pdf(product: dict, url: str, storefront_name: str = "") -> bytes:
    """One Letter page: name, price, a large QR code and the link."""
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    page_w, page_h = letter
    c.setTitle(f"{product.get('name', 'Listing')} QR code")
    text_w = page_w - 1.5 * inch
    y = page_h - 1.2 * inch

    if storefront_name:
        c.setFont("Helvetica", 14)
        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.drawCentredString(page_w / 2, y, storefront_name)
        y -= 0.55 * inch

    name = product.get("name") or "Listing"
    size = _fit(c, name, "Helvetica-Bold", 34, text_w)
    c.setFont("Helvetica-Bold", size)
    c.setFillColorRGB(0, 0, 0)
    c.drawCentredString(page_w / 2, y, name)
    y -= 0.6 * inch

    price = product.get("price_cents")
    if price is not None:
        c.setFont("Helvetica-Bold", 26)
        c.drawCentredString(page_w / 2, y, f"${price / 100:,.2f}")
        y -= 0.3 * inch

    qr_size = 4.6 * inch
    widget = QrCodeWidget(url, barLevel="Q")
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(qr_size, qr_size,
                      transform=[qr_size / (x1 - x0), 0, 0, qr_size / (y1 - y0), 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, c, (page_w - qr_size) / 2, y - qr_size)
    y -= qr_size + 0.45 * inch

    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(page_w / 2, y, "Scan to buy")
    y -= 0.4 * inch
    c.setFont("Helvetica", _fit(c, url, "Helvetica", 12, text_w))
    c.setFillColorRGB(0.25, 0.25, 0.25)
    c.drawCentredString(page_w / 2, y, url)
    y -= 0.3 * inch
    c.setFont("Helvetica", 11)
    c.drawCentredString(page_w / 2, y, "Ships to US addresses only.")

    c.showPage()
    c.save()
    return buf.getvalue()
