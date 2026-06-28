"""
Premium customer order-receipt PDF (ReportLab).

Honest wording: this is an **order receipt**, not a fiscal invoice (no VAT
number / fiscal fields), so it is labelled "Order receipt / Ricevuta ordine /
Reçu de commande". Localised EN/IT/FR from the order's stored language_code.

Security: renders only customer-facing data. NEVER includes internal Printify
ids/status or our cost fields (cost_production, cost_shipping, payment_fee).
"""
from __future__ import annotations

from io import BytesIO

from django.conf import settings
from django.contrib.staticfiles import finders
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# Brand palette (mirrors the storefront design tokens).
ESPRESSO = (0.110, 0.102, 0.090)   # #1c1a17
GOLD = (0.651, 0.510, 0.298)       # #a6824c
MUTED = (0.478, 0.451, 0.408)      # #7a7368
LINE = (0.86, 0.83, 0.78)
GREEN = (0.121, 0.478, 0.302)
AMBER = (0.851, 0.467, 0.024)

L = {
    "en": {
        "receipt": "Order receipt", "order": "Order", "date": "Date",
        "billed_to": "Billed to", "order_info": "Order info", "payment": "Payment",
        "status": "Status", "paid": "Paid", "pending": "Pending",
        "product": "Product", "qty": "Qty", "price": "Price", "total": "Total",
        "subtotal": "Subtotal", "shipping": "Shipping", "discount": "Discount",
        "tax": "Tax", "grand_total": "Grand total", "est_delivery": "Estimated delivery",
        "business_days": "business days",
        "disclaimer": "This is an order receipt, not a fiscal invoice.",
        "thanks": "Thank you for your order!",
    },
    "it": {
        "receipt": "Ricevuta ordine", "order": "Ordine", "date": "Data",
        "billed_to": "Intestato a", "order_info": "Dettagli ordine", "payment": "Pagamento",
        "status": "Stato", "paid": "Pagato", "pending": "In attesa",
        "product": "Prodotto", "qty": "Qtà", "price": "Prezzo", "total": "Totale",
        "subtotal": "Subtotale", "shipping": "Spedizione", "discount": "Sconto",
        "tax": "Tasse", "grand_total": "Totale", "est_delivery": "Consegna stimata",
        "business_days": "giorni lavorativi",
        "disclaimer": "Questa è una ricevuta d'ordine, non una fattura fiscale.",
        "thanks": "Grazie per il tuo ordine!",
    },
    "fr": {
        "receipt": "Reçu de commande", "order": "Commande", "date": "Date",
        "billed_to": "Facturé à", "order_info": "Détails commande", "payment": "Paiement",
        "status": "Statut", "paid": "Payé", "pending": "En attente",
        "product": "Produit", "qty": "Qté", "price": "Prix", "total": "Total",
        "subtotal": "Sous-total", "shipping": "Livraison", "discount": "Remise",
        "tax": "Taxes", "grand_total": "Total général", "est_delivery": "Livraison estimée",
        "business_days": "jours ouvrables",
        "disclaimer": "Ceci est un reçu de commande, pas une facture fiscale.",
        "thanks": "Merci pour votre commande !",
    },
}


def _labels(lang: str) -> dict:
    return L.get((lang or "en")[:2], L["en"])


def _logo():
    for name in ("images/brand/logo-glitchy-full.png", "images/brand/logo-glitchy-nav.png"):
        path = finders.find(name)
        if path:
            try:
                return ImageReader(path)
            except Exception:
                continue
    return None


def build_receipt_pdf(order, items) -> bytes:
    """Return the receipt PDF as bytes for `order` (+ its OrderProduct items)."""
    t = _labels(getattr(order, "language_code", "en"))
    sym = getattr(settings, "STORE_CURRENCY_SYMBOL", "€")
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    x = 18 * mm
    right = width - x

    def money(v):
        return f"{sym} {float(v or 0):.2f}"

    # ---- Header: logo + receipt title -------------------------------------
    y = height - 18 * mm
    logo = _logo()
    if logo:
        try:
            iw, ih = logo.getSize()
            h = 12 * mm
            w = h * (iw / ih)
            c.drawImage(logo, x, y - h + 3 * mm, width=w, height=h, mask="auto",
                        preserveAspectRatio=True)
        except Exception:
            pass
    c.setFillColorRGB(*ESPRESSO)
    c.setFont("Helvetica-Bold", 18)
    c.drawRightString(right, y, t["receipt"].upper())
    c.setFillColorRGB(*MUTED)
    c.setFont("Helvetica", 9.5)
    c.drawRightString(right, y - 6 * mm, f"{t['order']} #{order.order_number}")
    c.drawRightString(right, y - 11 * mm,
                      f"{t['date']}: {order.created_at.strftime('%Y-%m-%d %H:%M')}")

    # gold rule
    y -= 18 * mm
    c.setStrokeColorRGB(*GOLD)
    c.setLineWidth(1.4)
    c.line(x, y, right, y)
    y -= 10 * mm

    # ---- Two columns: billed to / order info ------------------------------
    col2 = x + 95 * mm
    c.setFillColorRGB(*GOLD)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x, y, t["billed_to"].upper())
    c.drawString(col2, y, t["order_info"].upper())
    y -= 6 * mm
    c.setFillColorRGB(*ESPRESSO)
    c.setFont("Helvetica", 9.5)
    addr2 = f" {order.address_line_2}" if order.address_line_2 else ""
    billed = [
        f"{order.first_name} {order.last_name}",
        f"{order.address_line_1}{addr2}".strip(),
        f"{order.postal_code} {order.city}, {order.state}".strip(", "),
        order.country,
        f"{order.email}",
        f"{order.phone}",
    ]
    by = y
    for line in billed:
        if line:
            c.drawString(x, by, line[:60])
            by -= 5 * mm

    paid = order.payment_id is not None
    method = order.payment.payment_method if order.payment_id and order.payment else "—"
    info = [
        (t["order"], f"#{order.order_number}"),
        (t["date"], order.created_at.strftime("%Y-%m-%d")),
        (t["payment"], method or "—"),
    ]
    iy = y
    for k, v in info:
        c.setFillColorRGB(*MUTED)
        c.drawString(col2, iy, f"{k}:")
        c.setFillColorRGB(*ESPRESSO)
        c.drawString(col2 + 26 * mm, iy, str(v)[:28])
        iy -= 5 * mm
    # status pill
    c.setFillColorRGB(*MUTED)
    c.drawString(col2, iy, f"{t['status']}:")
    c.setFillColorRGB(*(GREEN if paid else AMBER))
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(col2 + 26 * mm, iy, t["paid"] if paid else t["pending"])
    c.setFont("Helvetica", 9.5)

    y = min(by, iy) - 8 * mm

    # ---- Items table ------------------------------------------------------
    qx = x + 118 * mm
    px = x + 138 * mm
    c.setFillColorRGB(*MUTED)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x, y, t["product"].upper())
    c.drawRightString(qx, y, t["qty"].upper())
    c.drawRightString(px, y, t["price"].upper())
    c.drawRightString(right, y, t["total"].upper())
    y -= 3 * mm
    c.setStrokeColorRGB(*LINE)
    c.setLineWidth(0.6)
    c.line(x, y, right, y)
    y -= 6 * mm

    c.setFillColorRGB(*ESPRESSO)
    c.setFont("Helvetica", 9.5)
    for it in items:
        if y < 40 * mm:
            c.showPage()
            y = height - 25 * mm
            c.setFont("Helvetica", 9.5)
        line_total = float(it.product_price) * int(it.quantity)
        c.setFillColorRGB(*ESPRESSO)
        c.drawString(x, y, it.product.product_name[:52])
        c.drawRightString(qx, y, str(it.quantity))
        c.drawRightString(px, y, money(it.product_price))
        c.drawRightString(right, y, money(line_total))
        y -= 5 * mm
        vars_qs = it.variations.all()
        if vars_qs.exists():
            vs = ", ".join(f"{v.variation_category}: {v.variation_value}" for v in vars_qs)[:80]
            c.setFillColorRGB(*MUTED)
            c.setFont("Helvetica-Oblique", 8.5)
            c.drawString(x + 3 * mm, y, vs)
            c.setFont("Helvetica", 9.5)
            y -= 5 * mm
        else:
            y -= 1 * mm

    y -= 2 * mm
    c.setStrokeColorRGB(*LINE)
    c.line(x, y, right, y)
    y -= 8 * mm

    # ---- Totals -----------------------------------------------------------
    subtotal = float(order.items_subtotal) or (
        float(order.order_total) - float(order.tax) - float(order.shipping_cost))

    def total_line(label, value, bold=False, color=ESPRESSO):
        nonlocal y
        c.setFillColorRGB(*MUTED)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10 if bold else 9.5)
        c.drawRightString(right - 38 * mm, y, f"{label}:")
        c.setFillColorRGB(*color)
        c.drawRightString(right, y, money(value))
        y -= 6 * mm

    total_line(t["subtotal"], subtotal)
    if order.shipping_cost:
        total_line(t["shipping"], order.shipping_cost)
    else:
        c.setFillColorRGB(*MUTED)
        c.drawRightString(right - 38 * mm, y, f"{t['shipping']}:")
        c.setFillColorRGB(*GREEN)
        c.drawRightString(right, y, "Free")
        y -= 6 * mm
    if getattr(order, "discount", 0):
        total_line(t["discount"], -abs(float(order.discount)))
    total_line(t["tax"], order.tax)
    y -= 1 * mm
    c.setStrokeColorRGB(*GOLD)
    c.setLineWidth(1.0)
    c.line(right - 70 * mm, y, right, y)
    y -= 7 * mm
    total_line(t["grand_total"], order.order_total, bold=True, color=ESPRESSO)

    # estimated delivery (if captured at checkout)
    if order.shipping_min_days and order.shipping_max_days:
        c.setFillColorRGB(*MUTED)
        c.setFont("Helvetica", 9)
        c.drawRightString(right, y,
                          f"{t['est_delivery']}: {order.shipping_min_days}–"
                          f"{order.shipping_max_days} {t['business_days']}")
        y -= 6 * mm

    # ---- Footer -----------------------------------------------------------
    c.setFillColorRGB(*ESPRESSO)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, 24 * mm, t["thanks"])
    c.setFillColorRGB(*MUTED)
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(x, 18 * mm, t["disclaimer"])
    site = getattr(settings, "SITE_NAME", "Glitchy")
    c.drawRightString(right, 18 * mm, site)

    c.showPage()
    c.save()
    return buf.getvalue()
