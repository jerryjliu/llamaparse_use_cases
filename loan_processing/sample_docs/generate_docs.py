"""
Loan Processing Sample Document Generator

Downloads real fillable forms and generates synthetic documents
for the LlamaParse loan income verification tutorial.

Documents produced:
  1. loan_application.pdf  — Fannie Mae 1003 URLA (downloaded, AcroForm filled)
  2. w2.pdf                — IRS W-2 via eForms.com (downloaded, AcroForm filled)
  3. pay_stub.pdf          — Synthetic ADP-style stub (generated with reportlab)
  4. bank_statement.pdf    — Synthetic statement with transactions (generated with reportlab)

Usage:
    pip install pypdf reportlab requests
    python generate_docs.py
"""

import io
from pathlib import Path

import requests
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

# ── Synthetic identity ───────────────────────────────────────────────
IDENTITY = {
    "full_name": "SARAH M. CHEN",
    "first_name": "SARAH M.",
    "last_name": "CHEN",
    "ssn": "078-05-1120",
    "dob": "03/15/1988",
    "address_line1": "456 Oak Avenue",
    "address_unit": "Apt 2B",
    "city": "Austin",
    "state": "TX",
    "zip": "78701",
    "phone": "(512) 555-0147",
    "email": "sarah.chen@email.com",
}

EMPLOYER = {
    "name_formal": "Horizon Technologies, Inc.",
    "name_short": "HORIZON TECH INC",
    "ein": "74-3285619",
    "address": "1200 Congress Ave",
    "city": "Austin",
    "state": "TX",
    "zip": "78701",
    "position": "Senior Software Engineer",
    "start_date": "06/2021",
}

# Financial figures
ANNUAL_SALARY_CURRENT = 72_000.00   # current (post-raise)
ANNUAL_SALARY_PRIOR = 68_500.00     # W-2 (prior year)
BIWEEKLY_GROSS = ANNUAL_SALARY_CURRENT / 26  # $2,769.23
MONTHLY_INCOME = ANNUAL_SALARY_CURRENT / 12  # $6,000.00

# W-2 prior-year withholding (consistent with current pay stub rates)
# Federal withholding ~12% — aligns with current $310/biweekly on $72K (~11.2%)
# Slight difference is normal: prior year had different W-4 allowances + lower bracket math
W2_FEDERAL_TAX = 8_220.00  # ~12% of $68,500

# Pay stub deductions (per period)
DEDUCTIONS = {
    "Federal Income Tax": 310.00,
    "Social Security": 171.69,
    "Medicare": 40.15,
    "Health Insurance": 87.50,
    "401(k)": 110.00,
}
TOTAL_DEDUCTIONS = sum(DEDUCTIONS.values())  # $719.34
NET_PAY = BIWEEKLY_GROSS - TOTAL_DEDUCTIONS  # $2,049.89

OUT_DIR = Path(__file__).parent

# ── URLs ─────────────────────────────────────────────────────────────
FORM_1003_URL = "https://www.worthington.bank/pdf/Fillable%201003-URLA%203.1.21.pdf"
FORM_1003_BACKUP = "https://www.nmsigroup.com/Uploaded/Forms/Uniform%20Residential%20Loan%20Application%20(Form%201003)%20PDF%20Fillable.pdf"

W2_URL = "https://eforms.com/download/2023/08/IRS-Form-W2.pdf"

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


# =====================================================================
# Step 1: Download + fill 1003 Loan Application
# =====================================================================

def generate_loan_application():
    out = OUT_DIR / "loan_application.pdf"
    print("Downloading 1003 Uniform Residential Loan Application...")

    pdf_bytes = None
    for url in [FORM_1003_URL, FORM_1003_BACKUP]:
        try:
            resp = requests.get(url, timeout=30, headers=HEADERS)
            if resp.status_code == 200 and len(resp.content) > 10_000:
                pdf_bytes = resp.content
                print(f"  Downloaded from {url[:60]}...")
                break
        except Exception as e:
            print(f"  Failed {url[:60]}...: {e}")

    if not pdf_bytes:
        raise RuntimeError("Could not download 1003 form from any source")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.append(reader)

    # Page 0 — Section 1: Borrower Information
    name_field = (
        "Name Alternate Names  First Middle Last Suffix "
        "List any names by which you are known or any names "
        "under which credit was previously received "
        "First Middle Last Suffix"
    )
    writer.update_page_form_field_values(writer.pages[0], {
        name_field: "SARAH    M.    CHEN",
        "Social Security Number": IDENTITY["ssn"],
        "mmddyyyy": IDENTITY["dob"],
        "Total Number of Borrowers": "1",
        "Phone": IDENTITY["phone"],
        "Email": IDENTITY["email"],
        "Street": IDENTITY["address_line1"],
        "Unit": IDENTITY["address_unit"],
        "City": IDENTITY["city"],
        "State": IDENTITY["state"],
        "ZIP": IDENTITY["zip"],
        "Country": "US",
        "How Long at Current Address": "4",
        "Years": "8",
        # Employment
        "Employer or Business Name": EMPLOYER["name_formal"],
        "Phone_4": "(512) 555-3200",
        "Street_4": EMPLOYER["address"],
        "City_4": EMPLOYER["city"],
        "State_4": EMPLOYER["state"],
        "ZIP_4": EMPLOYER["zip"],
        "Country_4": "US",
        "Position or Title": EMPLOYER["position"],
        "Start Date": EMPLOYER["start_date"],
        "How long in this line of work": "8",
    })

    # Page 1 — Section 1 continued: Income
    writer.update_page_form_field_values(writer.pages[1], {
        "Income": f"{MONTHLY_INCOME:,.2f}",
    })

    # Page 2 — Section 2: Assets (one checking account for context)
    writer.update_page_form_field_values(writer.pages[2], {
        "Account Type  use list aboveRow1": "Checking",
        "Financial InstitutionRow1": "Lone Star National Bank",
        "Account NumberRow1": "****4738",
        "fill_47": "11,889",
    })

    # Page 4 — Section 4: Loan and Property Information
    writer.update_page_form_field_values(writer.pages[4], {
        "Loan Amount": "280,000",
        "Street_7": "789 Elm Street",
        "City_10": "Austin",
        "State_10": "TX",
        "ZIP_10": "78704",
        "County": "Travis",
        "Number of Units": "1",
        "Property Value": "350,000",
        "For Purchase Only": "350,000",
        "Amount": "70,000",
    })

    with open(out, "wb") as f:
        writer.write(f)
    print(f"  -> {out.name} ({out.stat().st_size / 1024:.0f} KB)")


# =====================================================================
# Step 2: Download + fill W-2
# =====================================================================

def generate_w2():
    out = OUT_DIR / "w2.pdf"
    print("Downloading W-2 form (eForms.com AcroForm version)...")

    resp = requests.get(W2_URL, timeout=30, headers=HEADERS)
    resp.raise_for_status()

    reader = PdfReader(io.BytesIO(resp.content))
    writer = PdfWriter()
    writer.append(reader)

    # W-2 field mapping — short field names on copy pages
    # Each copy uses the same f2_XX numbering scheme:
    #   f2_01 = Box a (SSN)           f2_09 = Box 1 (Wages)
    #   f2_02 = Box b (EIN)           f2_10 = Box 2 (Federal tax)
    #   f2_03 = Box c (Employer)      f2_11 = Box 3 (SS wages)
    #   f2_04 = Box d (Control #)     f2_12 = Box 4 (SS tax)
    #   f2_05 = Box e (First name)    f2_13 = Box 5 (Medicare wages)
    #   f2_06 = Box e (Last name)     f2_14 = Box 6 (Medicare tax)
    #   f2_07 = Box f (Address ln1)   f2_15 = Box 7 (SS tips)
    #   f2_08 = Box f (Address ln2)   f2_16 = Box 8 (Allocated tips)

    w2_data = {
        "f2_01[0]": IDENTITY["ssn"],
        "f2_02[0]": EMPLOYER["ein"],
        "f2_03[0]": (
            f"{EMPLOYER['name_formal']}\n"
            f"{EMPLOYER['address']}\n"
            f"{EMPLOYER['city']}, {EMPLOYER['state']} {EMPLOYER['zip']}"
        ),
        "f2_04[0]": "2025-W2-00471",                # Control number
        "f2_05[0]": IDENTITY["first_name"],           # First name + MI
        "f2_06[0]": IDENTITY["last_name"],             # Last name
        "f2_07[0]": f"{IDENTITY['address_line1']}, {IDENTITY['address_unit']}",
        "f2_08[0]": f"{IDENTITY['city']}, {IDENTITY['state']} {IDENTITY['zip']}",
        "f2_09[0]": f"{ANNUAL_SALARY_PRIOR:.2f}",     # Box 1 — Wages
        "f2_10[0]": f"{W2_FEDERAL_TAX:.2f}",              # Box 2 — Federal tax
        "f2_11[0]": f"{ANNUAL_SALARY_PRIOR:.2f}",     # Box 3 — SS wages
        "f2_12[0]": f"{ANNUAL_SALARY_PRIOR * 0.062:.2f}",  # Box 4 — SS tax
        "f2_13[0]": f"{ANNUAL_SALARY_PRIOR:.2f}",     # Box 5 — Medicare wages
        "f2_14[0]": f"{ANNUAL_SALARY_PRIOR * 0.0145:.2f}",  # Box 6 — Medicare tax
        # Box 12a — Code DD (employer health insurance)
        "f2_17[0]": "DD",
        "f2_18[0]": "6800.00",
    }

    # Fill Copy B (page 3) — employee's federal filing copy
    writer.update_page_form_field_values(writer.pages[3], w2_data)
    # Also fill Copy C (page 5) — employee's records copy
    writer.update_page_form_field_values(writer.pages[5], w2_data)

    with open(out, "wb") as f:
        writer.write(f)
    print(f"  -> {out.name} ({out.stat().st_size / 1024:.0f} KB)")


# =====================================================================
# Step 3: Generate synthetic pay stub (ADP-style)
# =====================================================================

def generate_pay_stub():
    out = OUT_DIR / "pay_stub.pdf"
    print("Generating synthetic pay stub...")

    W, H = letter
    c = canvas.Canvas(str(out), pagesize=letter)
    margin = 36
    content_w = W - 2 * margin
    y = H - margin

    pay_periods_ytd = 6  # 6th pay period of 2026
    ytd_gross = BIWEEKLY_GROSS * pay_periods_ytd

    # ── Company header bar ────────────────────────────────────────
    header_h = 44
    y -= header_h
    c.setFillColor(colors.HexColor("#1A3C5E"))
    c.rect(margin, y, content_w, header_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin + 12, y + 24, EMPLOYER["name_short"])
    c.setFont("Helvetica", 8)
    c.drawString(margin + 12, y + 10,
                 f"{EMPLOYER['address']}, {EMPLOYER['city']}, {EMPLOYER['state']} {EMPLOYER['zip']}")
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(W - margin - 12, y + 26, "EARNINGS STATEMENT")
    c.setFont("Courier", 7)
    c.drawRightString(W - margin - 12, y + 12, f"EIN: {EMPLOYER['ein']}")
    y -= 6

    # ── Employee info + pay period boxes ──────────────────────────
    box_h = 68
    col_gap = 10
    col_w = (content_w - col_gap) / 2
    y -= box_h

    # Left box — employee
    c.setStrokeColor(colors.HexColor("#C0C0C0"))
    c.setLineWidth(0.5)
    c.rect(margin, y, col_w, box_h, fill=0, stroke=1)

    c.setFillColor(colors.HexColor("#E8EDF2"))
    c.rect(margin, y + box_h - 14, col_w, 14, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1A3C5E"))
    c.setFont("Helvetica-Bold", 7)
    c.drawString(margin + 6, y + box_h - 11, "EMPLOYEE INFORMATION")

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin + 8, y + box_h - 28,
                 f"{IDENTITY['last_name']}, {IDENTITY['first_name']}")
    c.setFont("Helvetica", 8)
    c.drawString(margin + 8, y + box_h - 40,
                 f"{IDENTITY['address_line1']}, {IDENTITY['address_unit']}")
    c.drawString(margin + 8, y + box_h - 51,
                 f"{IDENTITY['city']}, {IDENTITY['state']} {IDENTITY['zip']}")
    c.setFont("Courier", 7)
    c.drawString(margin + 8, y + box_h - 63,
                 f"SSN: XXX-XX-{IDENTITY['ssn'][-4:]}")

    # Right box — pay period
    rx = margin + col_w + col_gap
    c.setStrokeColor(colors.HexColor("#C0C0C0"))
    c.rect(rx, y, col_w, box_h, fill=0, stroke=1)

    c.setFillColor(colors.HexColor("#E8EDF2"))
    c.rect(rx, y + box_h - 14, col_w, 14, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1A3C5E"))
    c.setFont("Helvetica-Bold", 7)
    c.drawString(rx + 6, y + box_h - 11, "PAY INFORMATION")

    pay_info = [
        ("Pay Period:", "03/01/2026 - 03/14/2026"),
        ("Pay Date:", "03/20/2026"),
        ("Pay Frequency:", "Biweekly"),
        ("Employee ID:", "HT-04582"),
    ]
    c.setFillColor(colors.black)
    for i, (label, val) in enumerate(pay_info):
        ty = y + box_h - 28 - i * 12
        c.setFont("Helvetica", 7.5)
        c.drawString(rx + 8, ty, label)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(rx + 90, ty, val)

    y -= 10

    # ── Earnings table ────────────────────────────────────────────
    y -= 14
    c.setFillColor(colors.HexColor("#1A3C5E"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin, y, "EARNINGS")
    y -= 2

    # Table header
    table_h = 14
    y -= table_h
    c.setFillColor(colors.HexColor("#E8EDF2"))
    c.rect(margin, y, content_w, table_h, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1A3C5E"))
    c.setFont("Helvetica-Bold", 7)
    cols = [margin + 8, margin + 140, margin + 220, margin + 320, margin + 420]
    headers = ["Description", "Rate", "Hours", "Current", "YTD"]
    for cx, h in zip(cols, headers):
        c.drawString(cx, y + 4, h)

    # Regular earnings row
    y -= 16
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    c.drawString(cols[0], y, "Regular")
    c.setFont("Courier", 8)
    c.drawString(cols[1], y, f"${BIWEEKLY_GROSS:,.2f}")
    c.drawString(cols[2], y, "80.00")
    c.drawString(cols[3], y, f"${BIWEEKLY_GROSS:,.2f}")
    c.drawString(cols[4], y, f"${ytd_gross:,.2f}")

    # Separator and total
    y -= 4
    c.setStrokeColor(colors.HexColor("#C0C0C0"))
    c.setLineWidth(0.3)
    c.line(margin + 8, y, W - margin - 8, y)
    y -= 14
    c.setFont("Helvetica-Bold", 8)
    c.drawString(cols[0], y, "Gross Pay")
    c.setFont("Courier-Bold", 8)
    c.drawString(cols[3], y, f"${BIWEEKLY_GROSS:,.2f}")
    c.drawString(cols[4], y, f"${ytd_gross:,.2f}")

    y -= 16

    # ── Deductions table ──────────────────────────────────────────
    c.setFillColor(colors.HexColor("#1A3C5E"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin, y, "DEDUCTIONS")
    y -= 2

    # Table header
    y -= table_h
    c.setFillColor(colors.HexColor("#E8EDF2"))
    c.rect(margin, y, content_w, table_h, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1A3C5E"))
    c.setFont("Helvetica-Bold", 7)
    ded_cols = [margin + 8, margin + 200, margin + 320, margin + 420]
    ded_headers = ["Description", "Statutory", "Current", "YTD"]
    for cx, h in zip(ded_cols, ded_headers):
        c.drawString(cx, y + 4, h)

    # Deduction rows
    c.setFillColor(colors.black)
    for desc, amount in DEDUCTIONS.items():
        y -= 14
        statutory = "Yes" if desc in ("Federal Income Tax", "Social Security", "Medicare") else ""
        c.setFont("Helvetica", 8)
        c.drawString(ded_cols[0], y, desc)
        c.setFont("Courier", 7)
        c.drawString(ded_cols[1], y, statutory)
        c.setFont("Courier", 8)
        c.drawString(ded_cols[2], y, f"${amount:,.2f}")
        c.drawString(ded_cols[3], y, f"${amount * pay_periods_ytd:,.2f}")

    # Separator and total deductions
    y -= 4
    c.setStrokeColor(colors.HexColor("#C0C0C0"))
    c.line(margin + 8, y, W - margin - 8, y)
    y -= 14
    c.setFont("Helvetica-Bold", 8)
    c.drawString(ded_cols[0], y, "Total Deductions")
    c.setFont("Courier-Bold", 8)
    c.drawString(ded_cols[2], y, f"${TOTAL_DEDUCTIONS:,.2f}")
    c.drawString(ded_cols[3], y, f"${TOTAL_DEDUCTIONS * pay_periods_ytd:,.2f}")

    y -= 24

    # ── Net Pay summary box ───────────────────────────────────────
    net_box_h = 48
    y -= net_box_h
    c.setFillColor(colors.HexColor("#F0F7ED"))
    c.setStrokeColor(colors.HexColor("#4CAF50"))
    c.setLineWidth(1)
    c.roundRect(margin, y, content_w, net_box_h, 4, fill=1, stroke=1)

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#2E7D32"))
    c.drawString(margin + 12, y + net_box_h - 18, "NET PAY")

    c.setFont("Courier-Bold", 14)
    c.drawString(margin + 12, y + 8, f"${NET_PAY:,.2f}")

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawRightString(W - margin - 12, y + net_box_h - 18, "YTD Net Pay")
    ytd_net = NET_PAY * pay_periods_ytd
    c.setFont("Courier-Bold", 11)
    c.setFillColor(colors.HexColor("#2E7D32"))
    c.drawRightString(W - margin - 12, y + 8, f"${ytd_net:,.2f}")

    y -= 16

    # ── Advice / disclaimer ───────────────────────────────────────
    c.setFont("Helvetica", 6)
    c.setFillColor(colors.HexColor("#999999"))
    c.drawString(margin, y,
                 "This is a sample earnings statement generated for demonstration purposes only.")
    y -= 10
    c.drawString(margin, y,
                 f"Horizon Technologies, Inc. is a fictitious company. EIN {EMPLOYER['ein']} is not a real employer identification number.")

    c.save()
    print(f"  -> {out.name} ({out.stat().st_size / 1024:.0f} KB)")


# =====================================================================
# Step 4: Generate synthetic bank statement
# =====================================================================

def generate_bank_statement():
    out = OUT_DIR / "bank_statement.pdf"
    print("Generating synthetic bank statement...")

    W, H = letter
    c = canvas.Canvas(str(out), pagesize=letter)
    margin = 36
    content_w = W - 2 * margin
    y = H - margin

    opening_balance = 8450.32

    # Transaction data
    transactions = [
        ("03/01", "ONLINE PMT RENT - APT 2B",              -1350.00),
        ("03/03", "POS PURCHASE H-E-B GROCERY #1247",      -87.42),
        ("03/05", "AUTOPAY SPECTRUM INTERNET",              -79.99),
        ("03/06", "ACH DEPOSIT HORIZON TECH DIR DEP",       NET_PAY),
        ("03/07", "POS PURCHASE SHELL OIL 57442",           -45.23),
        ("03/08", "ZELLE FROM MICHAEL CHEN",                 800.00),
        ("03/09", "AMAZON.COM AMZN.COM/BILL",               -34.99),
        ("03/11", "POS PURCHASE STARBUCKS #8823",            -6.75),
        ("03/12", "POS PURCHASE TRADER JOES #756",          -62.18),
        ("03/14", "AUTOPAY AT&T WIRELESS",                  -89.00),
        ("03/16", "RECURRING PMT NETFLIX.COM",              -15.99),
        ("03/18", "POS PURCHASE TARGET STORE #1293",        -43.67),
        ("03/20", "ACH DEPOSIT HORIZON TECH DIR DEP",       NET_PAY),
        ("03/21", "POS PURCHASE H-E-B GROCERY #1247",      -92.31),
        ("03/22", "VENMO CASHOUT TRANSFER",                  750.00),
        ("03/25", "POS PURCHASE COSTCO WHSE #445",         -156.88),
        ("03/27", "AUTOPAY AUSTIN ENERGY",                 -112.45),
        ("03/29", "RECURRING PMT SPOTIFY USA",              -10.99),
        ("03/31", "POS PURCHASE CVS PHARMACY #7821",        -23.45),
    ]

    total_deposits = sum(t[2] for t in transactions if t[2] > 0)
    total_withdrawals = sum(-t[2] for t in transactions if t[2] < 0)
    closing_balance = opening_balance + total_deposits - total_withdrawals

    # ── Bank header ───────────────────────────────────────────────
    header_h = 50
    y -= header_h
    c.setFillColor(colors.HexColor("#0D2137"))
    c.rect(margin, y, content_w, header_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin + 12, y + 28, "LONE STAR NATIONAL BANK")
    c.setFont("Helvetica", 7)
    c.drawString(margin + 12, y + 14,
                 "Member FDIC  |  500 Congress Avenue, Austin, TX 78701  |  (512) 555-8000")
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(W - margin - 12, y + 30, "CHECKING ACCOUNT STATEMENT")
    c.setFont("Courier", 8)
    c.drawRightString(W - margin - 12, y + 14, "Account: ****4738")
    y -= 8

    # ── Two-column: account holder + statement summary ────────────
    box_h = 62
    col_gap = 12
    col_w = (content_w - col_gap) / 2
    y -= box_h

    # Left — account holder
    c.setStrokeColor(colors.HexColor("#C0C0C0"))
    c.setLineWidth(0.5)
    c.rect(margin, y, col_w, box_h, fill=0, stroke=1)
    c.setFillColor(colors.HexColor("#E8EDF2"))
    c.rect(margin, y + box_h - 14, col_w, 14, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#0D2137"))
    c.setFont("Helvetica-Bold", 7)
    c.drawString(margin + 6, y + box_h - 11, "ACCOUNT HOLDER")
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin + 8, y + box_h - 28, IDENTITY["full_name"])
    c.setFont("Helvetica", 8)
    c.drawString(margin + 8, y + box_h - 40,
                 f"{IDENTITY['address_line1']}, {IDENTITY['address_unit']}")
    c.drawString(margin + 8, y + box_h - 51,
                 f"{IDENTITY['city']}, {IDENTITY['state']} {IDENTITY['zip']}")

    # Right — statement summary
    rx = margin + col_w + col_gap
    c.setStrokeColor(colors.HexColor("#C0C0C0"))
    c.rect(rx, y, col_w, box_h, fill=0, stroke=1)
    c.setFillColor(colors.HexColor("#E8EDF2"))
    c.rect(rx, y + box_h - 14, col_w, 14, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#0D2137"))
    c.setFont("Helvetica-Bold", 7)
    c.drawString(rx + 6, y + box_h - 11, "STATEMENT SUMMARY")

    summary_items = [
        ("Statement Period:", "March 1 - March 31, 2026"),
        ("Opening Balance:", f"${opening_balance:,.2f}"),
        ("Closing Balance:", f"${closing_balance:,.2f}"),
    ]
    c.setFillColor(colors.black)
    for i, (label, val) in enumerate(summary_items):
        ty = y + box_h - 28 - i * 13
        c.setFont("Helvetica", 8)
        c.drawString(rx + 8, ty, label)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(rx + 120, ty, val)

    y -= 10

    # ── Account summary bar ───────────────────────────────────────
    bar_h = 30
    y -= bar_h
    c.setFillColor(colors.HexColor("#F5F7FA"))
    c.setStrokeColor(colors.HexColor("#C0C0C0"))
    c.setLineWidth(0.3)
    c.rect(margin, y, content_w, bar_h, fill=1, stroke=1)

    third = content_w / 3
    items = [
        ("Total Deposits", f"${total_deposits:,.2f}"),
        ("Total Withdrawals", f"${total_withdrawals:,.2f}"),
        ("Ending Balance", f"${closing_balance:,.2f}"),
    ]
    for i, (label, val) in enumerate(items):
        cx = margin + third * i + 12
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawString(cx, y + bar_h - 11, label)
        c.setFont("Courier-Bold", 9)
        c.setFillColor(colors.HexColor("#0D2137"))
        c.drawString(cx, y + 5, val)

    y -= 12

    # ── Transaction table ─────────────────────────────────────────
    c.setFillColor(colors.HexColor("#0D2137"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin, y, "TRANSACTION DETAIL")
    y -= 4

    # Table header
    th = 14
    y -= th
    c.setFillColor(colors.HexColor("#E8EDF2"))
    c.rect(margin, y, content_w, th, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#0D2137"))
    c.setFont("Helvetica-Bold", 7)

    date_x = margin + 8
    desc_x = margin + 60
    debit_x = margin + 330
    credit_x = margin + 410
    bal_x = margin + 485

    c.drawString(date_x, y + 4, "DATE")
    c.drawString(desc_x, y + 4, "DESCRIPTION")
    c.drawRightString(debit_x + 50, y + 4, "DEBIT")
    c.drawRightString(credit_x + 50, y + 4, "CREDIT")
    c.drawRightString(bal_x + 50, y + 4, "BALANCE")

    # Transaction rows
    running_balance = opening_balance
    c.setFillColor(colors.black)
    for i, (date, desc, amount) in enumerate(transactions):
        y -= 14
        running_balance += amount

        # Alternating row background
        if i % 2 == 0:
            c.setFillColor(colors.HexColor("#FAFAFA"))
            c.rect(margin, y - 2, content_w, 14, fill=1, stroke=0)

        c.setFillColor(colors.black)
        c.setFont("Courier", 7.5)
        c.drawString(date_x, y, date)
        c.setFont("Helvetica", 7.5)
        c.drawString(desc_x, y, desc[:45])
        c.setFont("Courier", 7.5)
        if amount < 0:
            c.setFillColor(colors.HexColor("#C0392B"))
            c.drawRightString(debit_x + 50, y, f"${-amount:,.2f}")
        else:
            c.setFillColor(colors.HexColor("#27AE60"))
            c.drawRightString(credit_x + 50, y, f"${amount:,.2f}")
        c.setFillColor(colors.black)
        c.drawRightString(bal_x + 50, y, f"${running_balance:,.2f}")

    # Bottom border
    y -= 4
    c.setStrokeColor(colors.HexColor("#C0C0C0"))
    c.setLineWidth(0.5)
    c.line(margin, y, W - margin, y)

    y -= 18

    # ── Disclaimer ────────────────────────────────────────────────
    c.setFont("Helvetica", 6)
    c.setFillColor(colors.HexColor("#999999"))
    c.drawString(margin, y,
                 "Lone Star National Bank is a fictitious institution created for demonstration purposes only.")
    y -= 8
    c.drawString(margin, y,
                 "Account number and all transaction data shown are synthetic and do not represent real financial activity.")

    c.save()
    print(f"  -> {out.name} ({out.stat().st_size / 1024:.0f} KB)")


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("=" * 56)
    print("Loan Processing Sample Document Generator")
    print("=" * 56)
    print()

    generate_loan_application()
    generate_w2()
    generate_pay_stub()
    generate_bank_statement()

    print()
    print("Done! Generated files:")
    for f in sorted(OUT_DIR.glob("*.pdf")):
        print(f"  {f.name:30s} {f.stat().st_size / 1024:>8.0f} KB")


if __name__ == "__main__":
    main()
