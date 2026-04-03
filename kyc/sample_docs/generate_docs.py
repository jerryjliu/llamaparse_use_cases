"""
KYC Sample Document Generator

Downloads real specimen documents and generates a synthetic utility bill
for the LlamaParse KYC tutorial.

Documents produced:
  1. drivers_license.pdf  — PA DMV REAL ID specimen (downloaded, converted)
  2. bank_statement.pdf   — Impact Bank dummy statement (downloaded)
  3. utility_bill.pdf     — Synthetic bill with complex layout (generated)

Usage:
    pip install reportlab requests Pillow
    python generate_docs.py
"""

import io
import math
from pathlib import Path

import requests
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

# ── Identity data (from PA DMV specimen) ─────────────────────────────
IDENTITY = {
    "full_name": "ANDREW JASON SAMPLE",
    "short_name": "ANDREW J. SAMPLE",  # abbreviated variant for utility bill
    "date_of_birth": "01/07/1973",
    "address_line1": "123 Main St, Apt 1",
    "city_state_zip": "Harrisburg, PA 17101",
    "dl_number": "99 999 999",
    "dl_expiration": "01/08/2026",
    "dl_class": "C",
}

OUT_DIR = Path(__file__).parent

# ── URLs ─────────────────────────────────────────────────────────────
DL_URL = (
    "https://s7d9.scene7.com/is/image/statepa/"
    "real%20id-compliant%20non-commercial%20drivers%20license-1"
    "?ts=1726663078486&dpr=off"
)
BANK_URL = "https://www.impact-bank.com/user/file/dummy_statement.pdf"


# ── Step 1: Download PA DMV DL specimen → PDF ────────────────────────

def download_drivers_license():
    out = OUT_DIR / "drivers_license.pdf"
    print(f"Downloading PA DMV DL specimen...")
    resp = requests.get(DL_URL, timeout=30)
    resp.raise_for_status()

    img = Image.open(io.BytesIO(resp.content))
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Save as PDF — one page, image fills the page
    img.save(str(out), "PDF", resolution=150)
    print(f"  -> {out.name} ({out.stat().st_size / 1024:.0f} KB)")


# ── Step 2: Download Impact Bank dummy statement ─────────────────────

def download_bank_statement():
    out = OUT_DIR / "bank_statement.pdf"
    print(f"Downloading Impact Bank dummy statement...")
    resp = requests.get(BANK_URL, timeout=30)
    resp.raise_for_status()

    out.write_bytes(resp.content)
    print(f"  -> {out.name} ({out.stat().st_size / 1024:.0f} KB)")


# ── Step 3: Generate synthetic utility bill ──────────────────────────

def generate_utility_bill():
    out = OUT_DIR / "utility_bill.pdf"
    print("Generating synthetic utility bill...")

    W, H = letter  # 612 x 792
    c = canvas.Canvas(str(out), pagesize=letter)

    margin = 36  # 0.5"
    content_w = W - 2 * margin

    y = H - margin  # current y position (top-down)

    # ── Header bar ────────────────────────────────────────────────
    header_h = 50
    y -= header_h
    c.setFillColor(colors.HexColor("#1B4F72"))
    c.rect(margin, y, content_w, header_h, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin + 12, y + 28, "KEYSTONE POWER & GAS")
    c.setFont("Helvetica", 8)
    c.drawString(margin + 12, y + 14, "Serving Pennsylvania Since 1948")

    # Right side: "logo" placeholder
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(W - margin - 12, y + 30, "Account Number")
    c.setFont("Courier-Bold", 11)
    c.drawRightString(W - margin - 12, y + 16, "8847-2031-0074")

    y -= 8

    # ── Two-column boxes: Customer Info + Account Summary ─────────
    box_h = 72
    col_gap = 12
    col_w = (content_w - col_gap) / 2

    y -= box_h

    # Customer Info box (left)
    c.setStrokeColor(colors.HexColor("#AEB6BF"))
    c.setLineWidth(0.5)
    c.rect(margin, y, col_w, box_h, fill=0, stroke=1)

    c.setFillColor(colors.HexColor("#D5D8DC"))
    c.rect(margin, y + box_h - 14, col_w, 14, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.setFont("Helvetica-Bold", 7)
    c.drawString(margin + 6, y + box_h - 11, "CUSTOMER INFORMATION")

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin + 8, y + box_h - 28, IDENTITY["short_name"])
    c.setFont("Helvetica", 9)
    c.drawString(margin + 8, y + box_h - 40, IDENTITY["address_line1"])
    c.drawString(margin + 8, y + box_h - 51, IDENTITY["city_state_zip"])
    c.setFont("Helvetica", 7)
    c.drawString(margin + 8, y + box_h - 64, "Residential Customer Since 2015")

    # Account Summary box (right)
    rx = margin + col_w + col_gap
    c.setStrokeColor(colors.HexColor("#AEB6BF"))
    c.rect(rx, y, col_w, box_h, fill=0, stroke=1)

    c.setFillColor(colors.HexColor("#D5D8DC"))
    c.rect(rx, y + box_h - 14, col_w, 14, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.setFont("Helvetica-Bold", 7)
    c.drawString(rx + 6, y + box_h - 11, "ACCOUNT SUMMARY")

    summary_items = [
        ("Bill Date:", "February 1, 2026"),
        ("Due Date:", "February 22, 2026"),
        ("Amount Due:", "$151.34"),
        ("Previous Balance:", "$0.00 (Paid)"),
    ]
    c.setFillColor(colors.black)
    for i, (label, val) in enumerate(summary_items):
        ty = y + box_h - 28 - i * 13
        c.setFont("Helvetica", 8)
        c.drawString(rx + 8, ty, label)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(rx + 80, ty, val)

    y -= 10

    # ── Usage bar chart section ───────────────────────────────────
    chart_h = 72
    y -= chart_h

    c.setStrokeColor(colors.HexColor("#D5D8DC"))
    c.setLineWidth(0.3)
    c.rect(margin, y, content_w, chart_h, fill=0, stroke=1)

    c.setFillColor(colors.HexColor("#2C3E50"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin + 8, y + chart_h - 14, "YOUR ENERGY USAGE  (kWh)")

    # Draw 12 monthly bars
    months = ["Mar", "Apr", "May", "Jun", "Jul", "Aug",
              "Sep", "Oct", "Nov", "Dec", "Jan", "Feb"]
    usage = [520, 480, 410, 620, 780, 850, 720, 580, 490, 540, 610, 625]
    max_u = max(usage)
    bar_area_x = margin + 40
    bar_area_w = content_w - 56
    bar_w = bar_area_w / 12 - 4
    bar_max_h = chart_h - 30

    for i, (m, u) in enumerate(zip(months, usage)):
        bx = bar_area_x + i * (bar_w + 4)
        bh = (u / max_u) * bar_max_h * 0.85
        by = y + 4

        # Alternate colors for electric vs gas emphasis
        if i == 11:  # current month highlighted
            c.setFillColor(colors.HexColor("#E67E22"))
        else:
            c.setFillColor(colors.HexColor("#5DADE2"))
        c.rect(bx, by + 10, bar_w, bh, fill=1, stroke=0)

        c.setFillColor(colors.HexColor("#566573"))
        c.setFont("Helvetica", 5)
        c.drawCentredString(bx + bar_w / 2, by + 3, m)
        c.setFont("Helvetica", 4.5)
        c.drawCentredString(bx + bar_w / 2, by + bh + 12, str(u))

    y -= 6

    # ── Charges detail table ──────────────────────────────────────
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.setFont("Helvetica-Bold", 10)
    y -= 14
    c.drawString(margin, y, "CHARGES DETAIL")
    y -= 4

    # Table border
    table_x = margin
    table_w = content_w
    table_top = y

    def charge_row(label, kwh, amount, indent=0, bold=False, separator=False):
        nonlocal y
        y -= 13
        if separator:
            c.setStrokeColor(colors.HexColor("#AEB6BF"))
            c.setLineWidth(0.3)
            c.line(table_x + 6, y + 11, table_x + table_w - 6, y + 11)
            return

        font = "Helvetica-Bold" if bold else "Helvetica"
        c.setFont(font, 8)
        c.setFillColor(colors.black)
        c.drawString(table_x + 10 + indent, y, label)
        if kwh:
            c.setFont("Courier", 7)
            c.drawRightString(table_x + table_w - 100, y, kwh)
        c.setFont("Courier-Bold" if bold else "Courier", 8)
        c.drawRightString(table_x + table_w - 10, y, amount)

    # Section header: Electric Service
    y -= 15
    c.setFillColor(colors.HexColor("#EBF5FB"))
    c.rect(table_x, y - 2, table_w, 14, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1B4F72"))
    c.setFont("Helvetica-Bold", 8)
    c.drawString(table_x + 10, y + 1, "Electric Service")
    c.setFont("Helvetica", 6)
    c.drawRightString(table_x + table_w - 100, y + 1, "Usage")
    c.drawRightString(table_x + table_w - 10, y + 1, "Amount")

    # Tier rows (nested under Electric Service)
    charge_row("Baseline Allowance (0-350 kWh)", "350 kWh", "$52.15", indent=12)
    charge_row("Tier 1 (351-600 kWh)", "180 kWh", "$34.74", indent=12)
    charge_row("Tier 2 (601+ kWh)", "95 kWh", "$27.36", indent=12)
    charge_row("Electric Delivery Charges", "", "$18.42", indent=12)
    charge_row(separator=True, label="", kwh="", amount="")
    charge_row("Electric Subtotal", "625 kWh", "$132.67", bold=True)

    # Section header: Gas Service
    y -= 6
    c.setFillColor(colors.HexColor("#FEF9E7"))
    c.rect(table_x, y - 2, table_w, 14, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#7D6608"))
    c.setFont("Helvetica-Bold", 8)
    c.drawString(table_x + 10, y + 1, "Gas Service")

    charge_row("Gas Usage (22 therms @ $0.90)", "22 therms", "$19.80", indent=12)
    charge_row("Gas Delivery Charge", "", "$5.40", indent=12)
    charge_row(separator=True, label="", kwh="", amount="")
    charge_row("Gas Subtotal", "", "$25.20", bold=True)

    # Taxes & surcharges (different indentation style)
    y -= 6
    c.setFillColor(colors.HexColor("#F2F3F4"))
    c.rect(table_x, y - 2, table_w, 14, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.setFont("Helvetica-Bold", 8)
    c.drawString(table_x + 10, y + 1, "Taxes & Surcharges")

    # Footnote references in the charge descriptions
    y -= 13
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.black)
    c.drawString(table_x + 22, y, "State Tax Surcharge")
    # Superscript footnote
    c.setFont("Helvetica", 5)
    c.drawString(table_x + 110, y + 3, "1")
    c.setFont("Courier", 8)
    c.drawRightString(table_x + table_w - 10, y, "$3.42")

    y -= 13
    c.setFont("Helvetica", 8)
    c.drawString(table_x + 22, y, "Public Purpose Program")
    c.setFont("Helvetica", 5)
    c.drawString(table_x + 124, y + 3, "2")
    c.setFont("Courier", 8)
    c.drawRightString(table_x + table_w - 10, y, "$4.87")

    charge_row("Municipal Utility Tax (5%)", "", "$6.90", indent=12)
    charge_row("Franchise Fee", "", "$2.10", indent=12)
    charge_row(separator=True, label="", kwh="", amount="")

    # Subtotal taxes
    charge_row("Taxes & Surcharges Subtotal", "", "$17.29", bold=True)

    # Grand total with double line
    y -= 4
    c.setStrokeColor(colors.HexColor("#2C3E50"))
    c.setLineWidth(0.8)
    c.line(table_x + 6, y + 10, table_x + table_w - 6, y + 10)
    c.line(table_x + 6, y + 7, table_x + table_w - 6, y + 7)

    y -= 16
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.HexColor("#1B4F72"))
    c.drawString(table_x + 10, y, "TOTAL AMOUNT DUE")
    c.setFont("Courier-Bold", 11)
    c.drawRightString(table_x + table_w - 10, y, "$151.34")

    # Outer table border
    c.setStrokeColor(colors.HexColor("#AEB6BF"))
    c.setLineWidth(0.5)
    c.rect(table_x, y - 8, table_w, table_top - y + 8, fill=0, stroke=1)

    y -= 16

    # ── Message from utility ──────────────────────────────────────
    msg_h = 38
    y -= msg_h
    c.setFillColor(colors.HexColor("#EAFAF1"))
    c.setStrokeColor(colors.HexColor("#82E0AA"))
    c.setLineWidth(0.5)
    c.roundRect(margin, y, content_w, msg_h, 4, fill=1, stroke=1)

    c.setFillColor(colors.HexColor("#1E8449"))
    c.setFont("Helvetica-Bold", 7)
    c.drawString(margin + 8, y + msg_h - 12, "MESSAGE FROM YOUR UTILITY")
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.setFont("Helvetica", 7)
    c.drawString(margin + 8, y + msg_h - 24,
                 "Energy saving tip: Set your thermostat to 68\u00b0F during winter months to reduce heating costs by up to 10%.")
    c.drawString(margin + 8, y + msg_h - 34,
                 "Visit keystonepower.com/save for rebates on ENERGY STAR\u00ae appliances and home weatherization programs.")

    y -= 12

    # ── Dashed tear-off line ──────────────────────────────────────
    c.setStrokeColor(colors.HexColor("#566573"))
    c.setLineWidth(0.5)
    c.setDash(4, 3)
    c.line(margin, y, W - margin, y)
    c.setDash()  # reset

    c.setFont("Helvetica", 6)
    c.setFillColor(colors.HexColor("#566573"))
    c.drawCentredString(W / 2, y + 2, "- - -  DETACH HERE AND RETURN BOTTOM PORTION WITH YOUR PAYMENT  - - -")

    y -= 6

    # ── Payment stub ──────────────────────────────────────────────
    stub_top = y
    y -= 14
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#1B4F72"))
    c.drawString(margin + 8, y, "PAYMENT STUB")

    y -= 14
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.black)
    c.drawString(margin + 8, y, f"Account: 8847-2031-0074")
    c.drawString(margin + 180, y, f"Due Date: February 22, 2026")
    c.drawString(margin + 360, y, f"Amount Due: $151.34")

    y -= 14
    c.drawString(margin + 8, y, IDENTITY["short_name"])
    c.drawString(margin + 180, y, IDENTITY["address_line1"])
    c.drawString(margin + 300, y, IDENTITY["city_state_zip"])

    # Barcode placeholder (series of black/white bars)
    y -= 20
    bar_x = W - margin - 140
    c.setFillColor(colors.black)
    widths = [2, 1, 1, 3, 1, 2, 1, 1, 3, 2, 1, 1, 2, 3, 1, 2, 1, 3, 1, 1,
              2, 1, 3, 1, 2, 1, 1, 3, 2, 1, 1, 2, 1, 3, 1, 2, 1, 1, 2, 3]
    bx = bar_x
    for i, w in enumerate(widths):
        if i % 2 == 0:  # black bars on even indices
            c.rect(bx, y, w, 14, fill=1, stroke=0)
        bx += w

    # ── Footnotes (very small print) ──────────────────────────────
    y -= 18
    c.setFont("Helvetica", 5)
    c.setFillColor(colors.HexColor("#808B96"))
    c.drawString(margin + 8, y,
                 "\u00b9 Per PUC Docket No. M-2020-3019521. Rate effective January 1, 2026.")
    y -= 8
    c.drawString(margin + 8, y,
                 "\u00b2 Per 66 Pa. C.S. \u00a7 2808. Funds support energy efficiency, renewable energy, and low-income assistance programs.")
    y -= 8
    c.drawString(margin + 8, y,
                 "Keystone Power & Gas is a fictitious utility company created for demonstration purposes only.")

    # Stub border
    c.setStrokeColor(colors.HexColor("#AEB6BF"))
    c.setLineWidth(0.3)
    c.rect(margin, y - 4, content_w, stub_top - y + 4, fill=0, stroke=1)

    c.save()
    print(f"  -> {out.name} ({out.stat().st_size / 1024:.0f} KB)")


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("=" * 56)
    print("KYC Sample Document Generator")
    print("=" * 56)
    print()

    download_drivers_license()
    download_bank_statement()
    generate_utility_bill()

    print()
    print("Done! Generated files:")
    for f in sorted(OUT_DIR.glob("*.pdf")):
        print(f"  {f.name:30s} {f.stat().st_size / 1024:>8.0f} KB")


if __name__ == "__main__":
    main()
