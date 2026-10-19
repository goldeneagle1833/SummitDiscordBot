"""PDF order confirmation (invoice) a buyer downloads from My Orders.

Built from the order as stored at checkout: items, prices, shipping, tax
and the address Stripe collected. Refunded orders carry a REFUNDED mark.
"""

from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from services.store_checkout import _site_url

# Orders the buyer actually paid for; unpaid checkouts have nothing to confirm
INVOICE_STATUSES = ("paid", "shipped", "delivered", "refunded")

STATUS_LABELS = {
    "paid": "Paid",
    "shipped": "Shipped",
    "delivered": "Delivered",
    "refunded": "Refunded",
}

GOLD = colors.HexColor("#b8860b")
GREY = colors.HexColor("#666666")
LINE = colors.HexColor("#d0d0d0")


def _money(cents: int | None, currency: str = "USD") -> str:
    cents = cents or 0
    return f"${cents / 100:,.2f}" if currency == "USD" else f"{cents / 100:,.2f} {currency}"


def _date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return f"{dt:%B} {dt.day}, {dt.year}"
    except ValueError:
        return iso[:10]


def _p(text: str, style) -> Paragraph:
    return Paragraph(escape(str(text or "")), style)


def build_invoice_pdf(order: dict, storefront: dict | None) -> bytes:
    """Render the order as a one-page (or longer) letter-size PDF."""
    currency = order.get("currency") or "USD"
    seller = (storefront or {}).get("name") or "Summit Store"
    contact = (storefront or {}).get("contact_email")

    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=14)
    small = ParagraphStyle("small", parent=body, fontSize=9, leading=12, textColor=GREY)
    label = ParagraphStyle("label", parent=small, fontName="Helvetica-Bold")
    title = ParagraphStyle("title", parent=styles["Title"], fontSize=20, leading=24,
                           alignment=0, spaceAfter=2)
    right = ParagraphStyle("right", parent=body, alignment=2)
    stamp = ParagraphStyle("stamp", parent=body, fontName="Helvetica-Bold",
                           fontSize=14, textColor=colors.HexColor("#c0392b"))

    story = [
        _p(seller, ParagraphStyle("seller", parent=body, fontName="Helvetica-Bold",
                                  fontSize=12, textColor=GOLD)),
        _p("Order confirmation", title),
    ]
    if contact:
        story.append(_p(contact, small))
    story.append(_p(_site_url("/store/orders"), small))
    story.append(Spacer(1, 0.25 * inch))

    if order["status"] == "refunded":
        story += [_p("REFUNDED", stamp), Spacer(1, 0.1 * inch)]

    # Order facts on the left, ship-to on the right
    facts = [
        [_p("Order number", label), _p(order["order_number"], body)],
        [_p("Order date", label), _p(_date(order.get("created_at")), body)],
        [_p("Paid", label), _p(_date(order.get("paid_at")), body)],
        [_p("Status", label), _p(STATUS_LABELS.get(order["status"], order["status"]), body)],
        [_p("Payment", label), _p("Card via Stripe", body)],
    ]
    if order.get("tracking_number"):
        carrier = order.get("tracking_carrier") or "Tracking"
        facts.append([_p(carrier, label), _p(order["tracking_number"], body)])
    city_line = " ".join(filter(None, [
        ", ".join(filter(None, [order.get("ship_city"), order.get("ship_state")])),
        order.get("ship_postal"),
    ]))
    ship_lines = [order.get("ship_name"), order.get("ship_line1"),
                  order.get("ship_line2"), city_line]
    ship_to = [_p("Ship to", label)] + [_p(line, body) for line in ship_lines if line]
    if order.get("email"):
        ship_to.append(_p(order["email"], small))

    facts_table = Table(facts, colWidths=[1.1 * inch, 2.4 * inch])
    facts_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    header = Table([[facts_table, ship_to]], colWidths=[3.75 * inch, 3.25 * inch])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [header, Spacer(1, 0.3 * inch)]

    # Items
    label_right = ParagraphStyle("labelright", parent=label, alignment=2)
    rows = [[_p("Item", label), _p("Qty", label),
             _p("Price", label_right), _p("Total", label_right)]]
    for item in order.get("items", []):
        line_total = item["unit_price_cents"] * item["quantity"]
        rows.append([
            _p(item["product_name"], body),
            _p(item["quantity"], body),
            _p(_money(item["unit_price_cents"], currency), right),
            _p(_money(line_total, currency), right),
        ])
    items_table = Table(rows, colWidths=[4.1 * inch, 0.6 * inch, 1.15 * inch, 1.15 * inch],
                        repeatRows=1)
    items_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [items_table, Spacer(1, 0.15 * inch)]

    # Totals
    totals = [["Subtotal", _money(order.get("subtotal_cents"), currency)],
              ["Shipping", _money(order.get("shipping_cents"), currency)]]
    if order.get("tax_cents"):
        totals.append(["Tax", _money(order["tax_cents"], currency)])
    totals.append(["Total", _money(order.get("total_cents"), currency)])
    if order["status"] == "refunded":
        totals.append(["Refunded", "-" + _money(order.get("total_cents"), currency)])
    total_row = 3 if order.get("tax_cents") else 2
    bold_right = ParagraphStyle("boldright", parent=right, fontName="Helvetica-Bold")
    totals_table = Table(
        [[_p(k, bold_right if i == total_row else right),
          _p(v, bold_right if i == total_row else right)]
         for i, (k, v) in enumerate(totals)],
        colWidths=[5.85 * inch, 1.15 * inch],
    )
    totals_table.setStyle(TableStyle([
        ("LINEABOVE", (0, total_row), (-1, total_row), 1, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [totals_table, Spacer(1, 0.4 * inch)]

    story.append(_p("Thank you for your order. US shipping only.", small))
    if (storefront or {}).get("shipping_note"):
        story.append(_p(storefront["shipping_note"], small))

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        title=f"Order {order['order_number']}", author=seller,
    )
    doc.build(story)
    return buf.getvalue()
