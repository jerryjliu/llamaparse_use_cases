"""
Insurance Claims Sample Document Generator

Downloads real forms and generates synthetic documents for the
LlamaParse auto claims coverage verification tutorial.

Documents produced:
  1. acord2_filled.pdf        — ACORD 2 Auto Loss Notice (downloaded, AcroForm filled)
  2. declarations_page.pdf    — Auto Insurance Declarations Page (synthetic, reportlab)
  3. accident_report.pdf      — Missouri Form 1140 Accident Report (downloaded, AcroForm filled)
  4. repair_estimate.pdf      — FL DACS Body Shop Estimate (downloaded, AcroForm filled)

Usage:
    pip install pypdf reportlab requests
    python generate_docs.py
    python generate_docs.py --verify   # re-read and confirm AcroForm values
"""

import io
import sys
from pathlib import Path

import requests
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

# ── Synthetic identity (built around the real repair estimate) ────────

IDENTITY = {
    "full_name": "MICHAEL R. TORRES",
    "first_name": "MICHAEL",
    "middle_initial": "R.",
    "last_name": "TORRES",
    "dob": "06/23/1982",
    "address": "789 Cedar Lane",
    "city": "Roswell",
    "state": "GA",
    "zip": "30076",
    "phone": "(678) 555-0147",
    "email": "m.torres@email.com",
    "dl_number": "054823971",
    "dl_state": "GA",
}

POLICY = {
    "number": "AUTO-2016-0847291",
    "carrier": "SUMMIT MUTUAL INSURANCE CO.",
    "effective": "01/15/2016",
    "expiration": "01/15/2017",
    "naic_code": "12345",
    "agent_name": "Robert J. Whitfield",
    "agent_agency": "Whitfield Insurance Agency",
    "agent_address": "450 Marietta Street NW, Suite 200",
    "agent_city_state_zip": "Atlanta, GA 30313",
    "agent_phone": "(404) 555-8820",
}

VEHICLE = {
    "year": "2015",
    "make": "Lexus",
    "model": "RC 350",
    "vin": "JTHHE5BC7F5006073",
    "body": "2D Coupe",
    "plate": "ABC1234",
    "plate_state": "GA",
    "use": "Pleasure",
    "garaging": "789 Cedar Lane, Roswell, GA 30076",
}

ACCIDENT = {
    "date": "02/15/2016",
    "time": "3:45",
    "time_pm": True,
    "location": "Intersection of Alpharetta Hwy and Holcomb Bridge Rd",
    "city": "Roswell",
    "state": "GA",
    "zip": "30076",
    "county": "Fulton",
    "description": (
        "Insured vehicle was stopped at a red light at the intersection of "
        "Alpharetta Hwy and Holcomb Bridge Rd. Vehicle 2 failed to stop and "
        "struck insured vehicle from behind on the left rear side. Moderate "
        "damage to insured vehicle rear quarter panel and bumper. No injuries."
    ),
    "description_alt": (
        "Vehicle 1 (Torres) was at a complete stop waiting for the traffic "
        "signal at Alpharetta Hwy and Holcomb Bridge Rd. Vehicle 2 (Chen) "
        "approached from behind and was unable to stop in time, colliding "
        "with the rear of Vehicle 1. Damage to rear bumper, left quarter "
        "panel, and tail light assembly of Vehicle 1. No injuries to either "
        "driver. Police were notified."
    ),
    "police_agency": "Roswell Police Department",
    "report_number": "RPD-2016-008847",
}

OTHER_DRIVER = {
    "first_name": "DAVID",
    "middle_initial": "L.",
    "last_name": "CHEN",
    "full_name": "DAVID L. CHEN",
    "dob": "11/02/1990",
    "address": "2245 Old Alabama Rd",
    "city_state": "Roswell, GA",
    "zip": "30076",
    "phone": "(770) 555-3892",
    "dl_number": "061947285",
    "dl_state": "GA",
    "vehicle_year": "2018",
    "vehicle_make": "Toyota",
    "vehicle_model": "Camry",
    "vehicle_plate": "DEF5678",
    "vehicle_plate_state": "GA",
    "insurance_company": "STATE FARM MUTUAL",
    "insurance_policy": "SF-9284-7361",
}

COVERAGE = [
    {"name": "Bodily Injury Liability",   "limits": "$100,000 / $300,000", "deductible": "\u2014",   "premium": "$312.00"},
    {"name": "Property Damage Liability",  "limits": "$50,000",            "deductible": "\u2014",   "premium": "$189.00"},
    {"name": "Collision",                  "limits": "$50,000",            "deductible": "$500",     "premium": "$267.00"},
    {"name": "Comprehensive",              "limits": "$50,000",            "deductible": "$250",     "premium": "$134.00"},
    {"name": "Uninsured Motorist",         "limits": "$100,000 / $300,000", "deductible": "\u2014",   "premium": "$78.00"},
    {"name": "Medical Payments",           "limits": "$5,000",             "deductible": "\u2014",   "premium": "$45.00"},
]

OUT_DIR = Path(__file__).parent
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# ── URLs ─────────────────────────────────────────────────────────────
ACORD2_URL = "https://myfloridacfo.com/docs-sf/rehabilitation-and-liquidation-libraries/rehab-static/acord-form-2-automobile-loss-notice.pdf"
MO1140_URL = "https://dor.mo.gov/forms/1140.pdf"
FL_DACS_ESTIMATE_URL = "https://ccmedia.fdacs.gov/content/download/116436/file/Sample-Body-Shop-Estimate-and-Invoice.pdf"

# Repair estimate line items (for FL DACS form)
# Note: includes a "front bumper" item on a rear-end collision — a subtle
# discrepancy that Claude should flag as potentially unrelated to the loss.
ESTIMATE_LINES = [
    # (description, part_no, qty, body_hrs, frame_hrs, paint_hrs, part_cost)
    ("Rear bumper cover - R&I, refinish",    "52159-24070", "1", "2.0", "",    "2.5", "$1,285.00"),
    ("Rear bumper energy absorber - replace", "52615-24050", "1", "0.8", "",    "",    "$425.00"),
    ("Rear bumper reinforcement - replace",   "52171-24020", "1", "1.2", "",    "",    "$510.00"),
    ("L rear quarter panel - repair, refin",  "",            "",  "4.5", "",    "3.5", ""),
    ("Tail light assembly LH (LED) - repl",   "81561-24130", "1", "0.5", "",    "",    "$875.00"),
    ("Rear body panel - pull, straighten",    "",            "",  "",    "2.5", "",    ""),
    ("Trunk lid - R&I, inspect, adjust",      "",            "",  "1.0", "",    "",    ""),
    ("Front bumper cover - inspect, refin",   "",            "",  "0.5", "",    "1.5", "$180.00"),
    ("Blend R rear quarter, rear door",       "",            "",  "",    "",    "2.0", ""),
    ("Misc hardware, clips, fasteners",       "",            "1", "",    "",    "",    "$125.00"),
]

ESTIMATE_TOTALS = {
    "body_hours": "10.5",
    "mech_hours": "2.5",
    "paint_hours": "9.5",
    "body_rate": "$65.00",
    "mech_rate": "$75.00",
    "paint_rate": "$60.00",
    "body_labor": "$682.50",      # 10.5 × $65
    "mech_labor": "$187.50",      # 2.5 × $75
    "paint_labor": "$570.00",     # 9.5 × $60
    "labor_total": "$1,440.00",   # $682.50 + $187.50 + $570.00
    "parts_total": "$3,400.00",
    "paint_supplies": "$285.00",
    "body_supplies": "$125.00",
    "shop_supplies": "$65.00",
    "subtotal": "$5,315.00",      # $1,440 + $3,400 + $285 + $125 + $65
    "tax": "$238.00",             # 7% on parts only: $3,400 × 0.07
    "total": "$5,553.00",         # $5,315 + $238
    "estimate_date": "03/08/2016",
}


# =====================================================================
# Step 1: Download + fill ACORD 2 Auto Loss Notice
# =====================================================================

def download_and_fill_acord2():
    out = OUT_DIR / "acord2_filled.pdf"
    print("Downloading ACORD 2 Auto Loss Notice...")

    resp = requests.get(ACORD2_URL, timeout=30, headers=HEADERS)
    resp.raise_for_status()
    print(f"  Downloaded ({len(resp.content) / 1024:.0f} KB)")

    reader = PdfReader(io.BytesIO(resp.content))
    writer = PdfWriter()
    writer.append(reader)

    # All fields use update_page_form_field_values on all pages at once
    # _A suffix = insured/first vehicle, _B suffix = other party/second vehicle
    acord2_fields = {
        # ── Producer / Agency ──
        "Producer_FullName_A": POLICY["agent_agency"],
        "Producer_MailingAddress_LineOne_A": POLICY["agent_address"],
        "Producer_MailingAddress_CityName_A": "Atlanta",
        "Producer_MailingAddress_StateOrProvinceCode_A": "GA",
        "Producer_MailingAddress_PostalCode_A": "30313",
        "Producer_ContactPerson_FullName_A": POLICY["agent_name"],
        "Producer_ContactPerson_PhoneNumber_A": POLICY["agent_phone"],
        "Form_CompletionDate_A": "02/16/2016",

        # ── Insurer ──
        "Insurer_FullName_A": POLICY["carrier"],
        "Insurer_NAICCode_A": POLICY["naic_code"],

        # ── Policy ──
        "Policy_PolicyNumberIdentifier_A": POLICY["number"],

        # ── Named Insured ──
        "NamedInsured_FullName_A": IDENTITY["full_name"],
        "NamedInsured_MailingAddress_LineOne_A": IDENTITY["address"],
        "NamedInsured_MailingAddress_CityName_A": IDENTITY["city"],
        "NamedInsured_MailingAddress_StateOrProvinceCode_A": IDENTITY["state"],
        "NamedInsured_MailingAddress_PostalCode_A": IDENTITY["zip"],
        "NamedInsured_Primary_PhoneNumber_A": IDENTITY["phone"],
        "NamedInsured_Primary_EmailAddress_A": IDENTITY["email"],
        "NamedInsured_BirthDate_A": IDENTITY["dob"],

        # ── Loss details ──
        "Loss_IncidentDate_A": ACCIDENT["date"],
        "Loss_IncidentTime_A": ACCIDENT["time"],
        "Loss_IncidentDescription_A": ACCIDENT["description"],
        "Loss_AuthorityContactedName_A": ACCIDENT["police_agency"],
        "Loss_ReportIdentifier_A": ACCIDENT["report_number"],

        # ── Loss location ──
        "LossLocation_LocationDescription_A": ACCIDENT["location"],
        "LossLocation_PhysicalAddress_CityName_A": ACCIDENT["city"],
        "LossLocation_PhysicalAddress_StateOrProvinceCode_A": ACCIDENT["state"],
        "LossLocation_PhysicalAddress_PostalCode_A": ACCIDENT["zip"],
        "LossLocation_PhysicalAddress_CountryCode_A": "US",

        # ── Insured vehicle (Vehicle A) ──
        "Vehicle_ModelYear_A": VEHICLE["year"],
        "Vehicle_ManufacturersName_A": VEHICLE["make"],
        "Vehicle_ModelName_A": VEHICLE["model"],
        "Vehicle_VINIdentifier_A": VEHICLE["vin"],
        "Vehicle_BodyCode_A": VEHICLE["body"],
        "Vehicle_Registration_LicensePlateIdentifier_A": VEHICLE["plate"],
        "Vehicle_Registration_StateOrProvinceCode_A": VEHICLE["plate_state"],

        # ── Insured vehicle driver (A) ──
        "Driver_GivenName_A": IDENTITY["first_name"],
        "Driver_OtherGivenNameInitial_A": IDENTITY["middle_initial"],
        "Driver_Surname_A": IDENTITY["last_name"],
        "Driver_BirthDate_A": IDENTITY["dob"],
        "Driver_MailingAddress_LineOne_A": IDENTITY["address"],
        "Driver_MailingAddress_CityName_A": IDENTITY["city"],
        "Driver_MailingAddress_StateOrProvinceCode_A": IDENTITY["state"],
        "Driver_MailingAddress_PostalCode_A": IDENTITY["zip"],
        "Driver_Primary_PhoneNumber_A": IDENTITY["phone"],
        "Driver_LicenseNumberIdentifier_A": IDENTITY["dl_number"],
        "Driver_LicensedStateOrProvinceCode_A": IDENTITY["dl_state"],
        "Driver_RelationshipCode_A": "Insured",
        "LossInsuredVehicleDriver_PurposeOfUse_A": "Personal",

        # ── Damage description (Vehicle A) ──
        "LossProperty_DamageDescription_A": "Rear bumper, left rear quarter panel, tail light assembly damaged",
        "LossProperty_EstimatedDamageAmount_A": "$8,000",

        # ── Other vehicle (Vehicle B) ──
        "Vehicle_ModelYear_B": OTHER_DRIVER["vehicle_year"],
        "Vehicle_ManufacturersName_B": OTHER_DRIVER["vehicle_make"],
        "Vehicle_ModelName_B": OTHER_DRIVER["vehicle_model"],
        "Vehicle_Registration_LicensePlateIdentifier_B": OTHER_DRIVER["vehicle_plate"],
        "Vehicle_Registration_StateOrProvinceCode_B": OTHER_DRIVER["vehicle_plate_state"],

        # ── Other driver (B) ──
        "Driver_GivenName_B": OTHER_DRIVER["first_name"],
        "Driver_OtherGivenNameInitial_B": OTHER_DRIVER["middle_initial"],
        "Driver_Surname_B": OTHER_DRIVER["last_name"],
        "Driver_MailingAddress_LineOne_B": OTHER_DRIVER["address"],
        "Driver_MailingAddress_CityName_B": "Roswell",
        "Driver_MailingAddress_StateOrProvinceCode_B": "GA",
        "Driver_MailingAddress_PostalCode_B": OTHER_DRIVER["zip"],
        "Driver_Primary_PhoneNumber_B": OTHER_DRIVER["phone"],

        # ── Other vehicle owner (B) ──
        "LossPropertyOwner_FullName_B": OTHER_DRIVER["full_name"],
        "LossPropertyOwner_MailingAddress_LineOne_B": OTHER_DRIVER["address"],
        "LossPropertyOwner_MailingAddress_CityName_B": "Roswell",
        "LossPropertyOwner_MailingAddress_StateOrProvinceCode_B": "GA",
        "LossPropertyOwner_MailingAddress_PostalCode_B": OTHER_DRIVER["zip"],

        # ── Other insurance (B) ──
        "OtherInsurance_InsurerFullName_B": OTHER_DRIVER["insurance_company"],
        "OtherInsurance_PolicyNumberIdentifier_B": OTHER_DRIVER["insurance_policy"],

        # ── Remarks ──
        "AutomobileLossNotice_ACORDForm_RemarkText_A": (
            "Two-vehicle rear-end collision at signalized intersection. "
            "Insured vehicle was stationary. No injuries reported by either party. "
            "Police report filed: " + ACCIDENT["report_number"]
        ),
    }

    # Fill fields across all pages
    for page in writer.pages:
        writer.update_page_form_field_values(page, acord2_fields)

    # Ensure NeedAppearances is set so viewers regenerate field visuals
    from pypdf.generic import BooleanObject, NameObject
    if "/AcroForm" in writer._root_object:
        writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)

    with open(out, "wb") as f:
        writer.write(f)
    print(f"  -> {out.name} ({out.stat().st_size / 1024:.0f} KB)")


# =====================================================================
# Step 2: Generate synthetic declarations page
# =====================================================================

def generate_declarations_page():
    out = OUT_DIR / "declarations_page.pdf"
    print("Generating synthetic auto insurance declarations page...")

    W, H = letter
    c = canvas.Canvas(str(out), pagesize=letter)
    margin = 54  # ~0.75 inch — more formal margins
    content_w = W - 2 * margin
    y = H - margin

    # ── Colors — distinct from KYC/loan synthetic docs ────────────
    GREEN_DARK = colors.HexColor("#1B5E20")   # forest green brand
    MAROON = colors.HexColor("#8B1A1A")        # burgundy accent
    CHARCOAL = colors.HexColor("#2D2D2D")      # body text
    TAN_LIGHT = colors.HexColor("#F5F0E8")     # section backgrounds
    TAN_MED = colors.HexColor("#E8DFD0")       # table alternating rows
    RULE_COLOR = colors.HexColor("#3E7B27")    # green rules

    # ── Header — serif, formal letter style ──────────────────────
    # Shield icon placeholder (simple shape)
    shield_x = margin
    shield_y = y - 32
    c.setFillColor(GREEN_DARK)
    c.setStrokeColor(GREEN_DARK)
    c.setLineWidth(1.5)
    # Draw a simple shield shape
    p = c.beginPath()
    p.moveTo(shield_x + 12, shield_y + 32)
    p.lineTo(shield_x, shield_y + 20)
    p.lineTo(shield_x, shield_y + 8)
    p.lineTo(shield_x + 12, shield_y)
    p.lineTo(shield_x + 24, shield_y + 8)
    p.lineTo(shield_x + 24, shield_y + 20)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    # "SM" initials inside shield
    c.setFillColor(colors.white)
    c.setFont("Times-Bold", 9)
    c.drawCentredString(shield_x + 12, shield_y + 12, "SM")

    # Company name
    c.setFillColor(GREEN_DARK)
    c.setFont("Times-Bold", 18)
    c.drawString(shield_x + 32, y - 14, "SUMMIT MUTUAL INSURANCE CO.")
    c.setFont("Times-Roman", 8)
    c.setFillColor(CHARCOAL)
    c.drawString(shield_x + 32, y - 26, "A Member of the Summit Financial Group  \u2022  Established 1952")

    # Green rule under header
    y -= 38
    c.setStrokeColor(RULE_COLOR)
    c.setLineWidth(2)
    c.line(margin, y, W - margin, y)
    y -= 2
    c.setLineWidth(0.5)
    c.line(margin, y, W - margin, y)

    # "PERSONAL AUTO DECLARATIONS" in maroon
    y -= 18
    c.setFillColor(MAROON)
    c.setFont("Times-Bold", 14)
    c.drawCentredString(W / 2, y, "PERSONAL AUTO DECLARATIONS")

    y -= 24

    # ── Named Insured + Policy Info bordered box ─────────────────
    box_h = 72
    c.setStrokeColor(CHARCOAL)
    c.setLineWidth(0.5)
    c.rect(margin, y - box_h, content_w, box_h, fill=0, stroke=1)

    # Left column — Named Insured
    col_w = content_w / 2
    inner_y = y - 4

    c.setFillColor(CHARCOAL)
    c.setFont("Times-Bold", 7)
    c.drawString(margin + 8, inner_y - 10, "NAMED INSURED")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin + 8, inner_y - 24, IDENTITY["full_name"])
    c.setFont("Helvetica", 9)
    c.drawString(margin + 8, inner_y - 36, IDENTITY["address"])
    c.drawString(margin + 8, inner_y - 48, f"{IDENTITY['city']}, {IDENTITY['state']} {IDENTITY['zip']}")

    # Divider
    c.setStrokeColor(colors.HexColor("#CCCCCC"))
    c.setLineWidth(0.3)
    c.line(margin + col_w, y - 4, margin + col_w, y - box_h + 4)

    # Right column — Policy Info
    rx = margin + col_w + 12
    c.setFillColor(CHARCOAL)
    c.setFont("Times-Bold", 7)
    c.drawString(rx, inner_y - 10, "POLICY INFORMATION")

    info_items = [
        ("Policy Number:", POLICY["number"]),
        ("Effective Date:", POLICY["effective"]),
        ("Expiration Date:", POLICY["expiration"]),
    ]
    for i, (label, val) in enumerate(info_items):
        ly = inner_y - 24 - i * 14
        c.setFont("Helvetica", 8)
        c.drawString(rx, ly, label)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(rx + 95, ly, val)

    y -= box_h + 16

    # ── Vehicle Schedule ─────────────────────────────────────────
    c.setFillColor(GREEN_DARK)
    c.setFont("Times-Bold", 10)
    c.drawString(margin, y, "VEHICLE SCHEDULE")
    y -= 4
    c.setStrokeColor(RULE_COLOR)
    c.setLineWidth(0.8)
    c.line(margin, y, W - margin, y)
    y -= 14

    # Vehicle table header
    v_cols = [margin + 4, margin + 42, margin + 100, margin + 200, margin + 330]
    v_headers = ["Year", "Make", "Model", "VIN", "Use"]
    c.setFillColor(CHARCOAL)
    c.setFont("Helvetica-Bold", 7.5)
    for cx, h in zip(v_cols, v_headers):
        c.drawString(cx, y, h)

    # Underline
    y -= 3
    c.setStrokeColor(CHARCOAL)
    c.setLineWidth(0.3)
    c.line(margin, y, W - margin, y)

    # Vehicle row
    y -= 12
    c.setFont("Helvetica", 9)
    c.drawString(v_cols[0], y, VEHICLE["year"])
    c.drawString(v_cols[1], y, VEHICLE["make"])
    c.drawString(v_cols[2], y, VEHICLE["model"])
    c.setFont("Courier", 8)
    c.drawString(v_cols[3], y, VEHICLE["vin"])
    c.setFont("Helvetica", 9)
    c.drawString(v_cols[4], y, VEHICLE["use"])

    y -= 6
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#666666"))
    c.drawString(v_cols[0], y, f"Garaging Address: {VEHICLE['garaging']}")

    y -= 20

    # ── Coverage Table ───────────────────────────────────────────
    c.setFillColor(GREEN_DARK)
    c.setFont("Times-Bold", 10)
    c.drawString(margin, y, "COVERAGES AND LIMITS")
    y -= 4
    c.setStrokeColor(RULE_COLOR)
    c.setLineWidth(0.8)
    c.line(margin, y, W - margin, y)
    y -= 14

    # Table headers
    cov_cols = [margin + 4, margin + 220, margin + 330, margin + 420]
    cov_headers = ["Coverage", "Limits", "Deductible", "Premium"]
    c.setFillColor(CHARCOAL)
    c.setFont("Helvetica-Bold", 8)
    for cx, h in zip(cov_cols, cov_headers):
        c.drawString(cx, y, h)
    y -= 3
    c.setStrokeColor(CHARCOAL)
    c.setLineWidth(0.5)
    c.line(margin, y, W - margin, y)

    # Coverage rows
    total_premium = 0.0
    for i, cov in enumerate(COVERAGE):
        y -= 16
        # Alternating tan rows
        if i % 2 == 0:
            c.setFillColor(TAN_LIGHT)
            c.rect(margin, y - 3, content_w, 16, fill=1, stroke=0)

        c.setFillColor(CHARCOAL)
        c.setFont("Helvetica", 9)
        c.drawString(cov_cols[0], y, cov["name"])
        c.drawString(cov_cols[1], y, cov["limits"])
        c.drawString(cov_cols[2], y, cov["deductible"])
        c.setFont("Courier", 9)
        c.drawRightString(cov_cols[3] + 60, y, cov["premium"])
        total_premium += float(cov["premium"].replace("$", "").replace(",", ""))

    # Table bottom border
    y -= 4
    c.setStrokeColor(CHARCOAL)
    c.setLineWidth(0.5)
    c.line(margin, y, W - margin, y)

    # Total premium
    y -= 16
    c.setFillColor(CHARCOAL)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(cov_cols[0], y, "TOTAL ANNUAL PREMIUM")
    c.setFont("Courier-Bold", 10)
    c.drawRightString(cov_cols[3] + 60, y, f"${total_premium:,.2f}")

    y -= 24

    # ── Agent Information ────────────────────────────────────────
    c.setFillColor(GREEN_DARK)
    c.setFont("Times-Bold", 10)
    c.drawString(margin, y, "AGENT / PRODUCER")
    y -= 4
    c.setStrokeColor(RULE_COLOR)
    c.setLineWidth(0.8)
    c.line(margin, y, W - margin, y)
    y -= 14

    c.setFillColor(CHARCOAL)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin + 4, y, POLICY["agent_name"])
    c.setFont("Helvetica", 8)
    y -= 12
    c.drawString(margin + 4, y, POLICY["agent_agency"])
    y -= 12
    c.drawString(margin + 4, y, POLICY["agent_address"])
    y -= 12
    c.drawString(margin + 4, y, POLICY["agent_city_state_zip"])
    y -= 12
    c.drawString(margin + 4, y, f"Phone: {POLICY['agent_phone']}")

    y -= 22

    # ── Endorsements ─────────────────────────────────────────────
    c.setFillColor(GREEN_DARK)
    c.setFont("Times-Bold", 10)
    c.drawString(margin, y, "ENDORSEMENTS")
    y -= 4
    c.setStrokeColor(RULE_COLOR)
    c.setLineWidth(0.8)
    c.line(margin, y, W - margin, y)
    y -= 14

    endorsements = [
        ("GA-01", "Rental Reimbursement Coverage", "$30/day, 30-day max"),
        ("GA-02", "Towing and Labor Costs Coverage", "$75 per occurrence"),
    ]
    c.setFillColor(CHARCOAL)
    for code, desc, detail in endorsements:
        c.setFont("Courier-Bold", 8)
        c.drawString(margin + 4, y, code)
        c.setFont("Helvetica", 8)
        c.drawString(margin + 50, y, desc)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawRightString(W - margin - 4, y, detail)
        c.setFillColor(CHARCOAL)
        y -= 14

    y -= 16

    # ── Fine print disclaimer ────────────────────────────────────
    c.setStrokeColor(colors.HexColor("#CCCCCC"))
    c.setLineWidth(0.3)
    c.line(margin, y, W - margin, y)
    y -= 12

    c.setFont("Times-Italic", 6.5)
    c.setFillColor(colors.HexColor("#888888"))
    disclaimer_lines = [
        "This declarations page is a summary of your policy coverages. It does not contain all of the terms, conditions,",
        "and exclusions of your policy. Please refer to your policy contract for complete details of your coverage.",
        "Summit Mutual Insurance Co. is a fictitious company created for demonstration purposes only.",
        f"Policy Number: {POLICY['number']}  |  Named Insured: {IDENTITY['full_name']}  |  "
        f"Effective: {POLICY['effective']} to {POLICY['expiration']}",
    ]
    for line in disclaimer_lines:
        c.drawString(margin, y, line)
        y -= 9

    c.save()
    print(f"  -> {out.name} ({out.stat().st_size / 1024:.0f} KB)")


# =====================================================================
# Step 3: Download + fill Missouri Form 1140 Accident Report
# =====================================================================

def download_and_fill_accident_report():
    out = OUT_DIR / "accident_report.pdf"
    print("Downloading Missouri Form 1140 Accident Report...")

    resp = requests.get(MO1140_URL, timeout=30, headers=HEADERS)
    resp.raise_for_status()
    print(f"  Downloaded ({len(resp.content) / 1024:.0f} KB)")

    reader = PdfReader(io.BytesIO(resp.content))
    writer = PdfWriter()
    writer.append(reader)

    # Fields confirmed via enumeration — all end with (0) suffix
    mo1140_fields = {
        # ── Accident details ──
        "Accident_Date(0)": ACCIDENT["date"],
        "Accident_Time(0)": ACCIDENT["time"],
        "Accident_Location(0)": ACCIDENT["location"],
        "County(0)": ACCIDENT["county"],
        "Vehicles_Involved(0)": "2",
        "Police_Agency(0)": ACCIDENT["police_agency"],
        "Describe_Accident(0)": ACCIDENT["description_alt"],

        # ── Vehicle 1 — Driver (our insured) ──
        "Driver_Name(0)": IDENTITY["full_name"],
        "Driver_Address(0)": IDENTITY["address"],
        "Driver_City_State(0)": f"{IDENTITY['city']}, {IDENTITY['state']}",
        "Driver_Zip(0)": IDENTITY["zip"],
        "Driver_DOB(0)": IDENTITY["dob"],
        "Driver_DLN_State(0)": f"{IDENTITY['dl_number']} / {IDENTITY['dl_state']}",

        # ── Vehicle 1 — Owner/Vehicle ──
        "Owner_Name(0)": IDENTITY["full_name"],
        "Owner_Address(0)": IDENTITY["address"],
        "Owner_City_State(0)": f"{IDENTITY['city']}, {IDENTITY['state']}",
        "Owner_Zip(0)": IDENTITY["zip"],
        "Owner_V_Make(0)": VEHICLE["make"],
        "Owner_V_Model(0)": f"{VEHICLE['model']} ({VEHICLE['year']})",
        "Owner_Plate_Number(0)": VEHICLE["plate"],
        "Owner_Plate_State(0)": VEHICLE["plate_state"],

        # ── Insurance ──
        "Insurance_Co_Name(0)": POLICY["carrier"],
        "Insurance_Policy_No(0)": POLICY["number"],

        # ── Vehicle 2 — Driver ──
        "Driver_Name_1(0)": OTHER_DRIVER["full_name"],
        "Driver_Address_1(0)": OTHER_DRIVER["address"],
        "Driver_City_State_1(0)": OTHER_DRIVER["city_state"],
        "Driver_Zip_1(0)": OTHER_DRIVER["zip"],
        "Driver_DOB_1(0)": OTHER_DRIVER["dob"],
        "Driver_DLN_State_1(0)": f"{OTHER_DRIVER['dl_number']} / {OTHER_DRIVER['dl_state']}",

        # ── Vehicle 2 — Owner/Vehicle ──
        "Owner_Name_1(0)": OTHER_DRIVER["full_name"],
        "Owner_Address_1(0)": OTHER_DRIVER["address"],
        "Owner_City_State_1(0)": OTHER_DRIVER["city_state"],
        "Owner_Zip_1(0)": OTHER_DRIVER["zip"],
        "Owner_V_Make_1(0)": OTHER_DRIVER["vehicle_make"],
        "Owner_V_Model_1(0)": f"{OTHER_DRIVER['vehicle_model']} ({OTHER_DRIVER['vehicle_year']})",
        "Owner_Plate_Number_1(0)": OTHER_DRIVER["vehicle_plate"],
        "Owner_Plate_State_1(0)": OTHER_DRIVER["vehicle_plate_state"],
    }

    # Fill fields across all pages
    for page in writer.pages:
        writer.update_page_form_field_values(page, mo1140_fields)

    # Ensure NeedAppearances is set so viewers regenerate field visuals
    from pypdf.generic import BooleanObject, NameObject
    if "/AcroForm" in writer._root_object:
        writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)

    with open(out, "wb") as f:
        writer.write(f)
    print(f"  -> {out.name} ({out.stat().st_size / 1024:.0f} KB)")


# =====================================================================
# Step 4: Download + fill FL DACS Body Shop Estimate
# =====================================================================

def download_and_fill_repair_estimate():
    out = OUT_DIR / "repair_estimate.pdf"
    print("Downloading FL DACS Body Shop Estimate/Invoice form...")

    resp = requests.get(FL_DACS_ESTIMATE_URL, timeout=30, headers=HEADERS)
    resp.raise_for_status()
    print(f"  Downloaded ({len(resp.content) / 1024:.0f} KB)")

    reader = PdfReader(io.BytesIO(resp.content))
    writer = PdfWriter()
    writer.append(reader)

    # Customer and vehicle info
    estimate_fields = {
        "Name": IDENTITY["full_name"],
        "Address": IDENTITY["address"],
        "City": IDENTITY["city"],
        "State": IDENTITY["state"],
        "Zip": IDENTITY["zip"],
        "Phone": IDENTITY["phone"],
        "YrMake": f"{VEHICLE['year']} {VEHICLE['make']}",
        "Model": VEHICLE["model"],
        "Vin": VEHICLE["vin"],
        "Tag": f"{VEHICLE['plate']} ({VEHICLE['plate_state']})",
        "Miles In": "42,318",

        # Business info
        "Business Name": "CLASSIC COLLISION OF ROSWELL",
        "Business Address": "985 Holcomb Bridge Rd",
        "Business Address 2": "Roswell, GA 30076",
        "Registration Number": "MV-87234",
        "Telephone Number": "(770) 555-4290",

        # Rates
        "Hourly Rate": ESTIMATE_TOTALS["body_rate"],
        "Flat Rate": ESTIMATE_TOTALS["mech_rate"],
        "Estimate Hourly": ESTIMATE_TOTALS["paint_rate"],

        # Hours and their dollar amounts
        # Row at Y~156: Body Hours | fill_195 (body $) | Parts | fill_196 (parts $)
        "Body Hours": ESTIMATE_TOTALS["body_hours"],
        "fill_195": ESTIMATE_TOTALS["body_labor"],
        "Parts": ESTIMATE_TOTALS["parts_total"],
        "fill_196": ESTIMATE_TOTALS["parts_total"],

        # Row at Y~139: Paint Hours | fill_198 (paint $) | Labor | fill_200 (labor $)
        "Paint Hours": ESTIMATE_TOTALS["paint_hours"],
        "fill_198": ESTIMATE_TOTALS["paint_labor"],
        "Labor": ESTIMATE_TOTALS["labor_total"],
        "fill_200": ESTIMATE_TOTALS["labor_total"],

        # Row at Y~122: Mech Hours | fill_201 (mech $) | Shop Sup | fill_202
        "Mech Hours": ESTIMATE_TOTALS["mech_hours"],
        "fill_201": ESTIMATE_TOTALS["mech_labor"],
        "Shop Sup": ESTIMATE_TOTALS["shop_supplies"],
        "fill_202": ESTIMATE_TOTALS["shop_supplies"],

        # Row at Y~106: Paint Supplies | fill_203 | Sublet | fill_205
        "Paint Supplies": ESTIMATE_TOTALS["paint_supplies"],
        "fill_203": ESTIMATE_TOTALS["paint_supplies"],

        # Row at Y~89: Body Supplies | fill_206 | Fees | fill_208
        "Body Supplies": ESTIMATE_TOTALS["body_supplies"],
        "fill_206": ESTIMATE_TOTALS["body_supplies"],

        # Row at Y~72: TowStorage | fill_209 | Subtotal | fill_211
        "Subtotal": ESTIMATE_TOTALS["subtotal"],
        "fill_211": ESTIMATE_TOTALS["subtotal"],

        # Row at Y~56: EpaWaste | fill_212 | Tax | fill_214
        "Tax": ESTIMATE_TOTALS["tax"],
        "fill_214": ESTIMATE_TOTALS["tax"],

        # Row at Y~39: Miscellaneous | fill_215 | Total | fill_217
        "Total": ESTIMATE_TOTALS["total"],
        "fill_217": ESTIMATE_TOTALS["total"],

        # Estimated cost (initial estimate field)
        "Estimated Cost": ESTIMATE_TOTALS["total"],

        # Date
        "Date": ESTIMATE_TOTALS["estimate_date"],
        "Proposed Completion Date": "03/22/2016",
    }

    # Fill line items (rows 1-10)
    for i, (desc, part_no, qty, body, frame, paint, cost) in enumerate(ESTIMATE_LINES, start=1):
        estimate_fields[f"DescriptionRow{i}"] = desc
        if part_no:
            estimate_fields[f"Part NoRow{i}"] = part_no
        if qty:
            estimate_fields[f"QtyRow{i}"] = qty
        if body:
            estimate_fields[f"BodyRow{i}"] = body
        if frame:
            estimate_fields[f"FrameRow{i}"] = frame
        if paint:
            estimate_fields[f"PaintRow{i}"] = paint
        if cost:
            estimate_fields[f"Row{i}"] = cost

    # Clear placeholder "Text" fields that overlay the real fields
    estimate_fields["Business Name Text"] = ""
    estimate_fields["Business Address Text"] = ""
    estimate_fields["Business Address 2 Text"] = ""
    estimate_fields["Business Phone Text"] = ""
    estimate_fields["Registration Number Text"] = ""

    # Fill all fields on the single page
    writer.update_page_form_field_values(writer.pages[0], estimate_fields)

    # Ensure NeedAppearances is set so viewers regenerate field visuals
    from pypdf.generic import BooleanObject, NameObject
    if "/AcroForm" in writer._root_object:
        writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)

    with open(out, "wb") as f:
        writer.write(f)
    print(f"  -> {out.name} ({out.stat().st_size / 1024:.0f} KB)")


# =====================================================================
# Verification: read back filled AcroForm fields
# =====================================================================

def verify_acroform_fills():
    """Read back filled PDFs and confirm key values are present."""
    print("\n" + "=" * 56)
    print("Verifying AcroForm fills...")
    print("=" * 56)

    checks = [
        ("acord2_filled.pdf", [
            ("NamedInsured_FullName_A", IDENTITY["full_name"]),
            ("Policy_PolicyNumberIdentifier_A", POLICY["number"]),
            ("Insurer_FullName_A", POLICY["carrier"]),
            ("Loss_IncidentDate_A", ACCIDENT["date"]),
            ("Vehicle_VINIdentifier_A", VEHICLE["vin"]),
            ("Vehicle_ManufacturersName_A", VEHICLE["make"]),
            ("Driver_Surname_A", IDENTITY["last_name"]),
            ("Driver_Surname_B", OTHER_DRIVER["last_name"]),
        ]),
        ("accident_report.pdf", [
            ("Driver_Name(0)", IDENTITY["full_name"]),
            ("Accident_Date(0)", ACCIDENT["date"]),
            ("Owner_V_Make(0)", VEHICLE["make"]),
            ("Insurance_Co_Name(0)", POLICY["carrier"]),
            ("Driver_Name_1(0)", OTHER_DRIVER["full_name"]),
        ]),
        ("repair_estimate.pdf", [
            ("Name", IDENTITY["full_name"]),
            ("Vin", VEHICLE["vin"]),
            ("Total", "$5,553.00"),
            ("Business Name", "CLASSIC COLLISION"),
            ("DescriptionRow1", "Rear bumper"),
        ]),
    ]

    all_ok = True
    for filename, field_checks in checks:
        filepath = OUT_DIR / filename
        if not filepath.exists():
            print(f"\n  MISSING: {filename}")
            all_ok = False
            continue

        print(f"\n  {filename}:")
        reader = PdfReader(str(filepath))
        fields = reader.get_fields() or {}

        for field_name, expected in field_checks:
            actual = ""
            if field_name in fields:
                actual = str(fields[field_name].get("/V", ""))
            if expected in actual or actual == expected:
                print(f"    OK  {field_name} = {actual!r}")
            else:
                print(f"    FAIL  {field_name}")
                print(f"          expected: {expected!r}")
                print(f"          actual:   {actual!r}")
                all_ok = False

    if all_ok:
        print("\n  All AcroForm verification checks passed!")
    else:
        print("\n  WARNING: Some verification checks failed.")
    return all_ok


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("=" * 56)
    print("Insurance Claims Sample Document Generator")
    print("=" * 56)
    print()

    download_and_fill_acord2()
    generate_declarations_page()
    download_and_fill_accident_report()
    download_and_fill_repair_estimate()

    print()
    print("Done! Generated files:")
    for f in sorted(OUT_DIR.glob("*.pdf")):
        print(f"  {f.name:30s} {f.stat().st_size / 1024:>8.0f} KB")

    if "--verify" in sys.argv:
        verify_acroform_fills()


if __name__ == "__main__":
    main()
