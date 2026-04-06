"""
Loan Income Verification Pipeline with LlamaParse

Processes 4 loan documents through LlamaParse Extract, uses Claude for
cross-document income validation, and generates an interactive HTML report.

Documents:
  1. Loan Application (Fannie Mae 1003 URLA, AcroForm-filled)
  2. W-2 Wage and Tax Statement (eForms AcroForm-filled)
  3. Pay Stub (synthetic, ADP-style)
  4. Bank Statement (synthetic, with transaction table)

Usage:
    export LLAMA_CLOUD_API_KEY=llx-...
    export ANTHROPIC_API_KEY=sk-ant-...
    pip install 'llama-cloud>=2.1' anthropic pydantic
    python loan_pipeline.py
"""

import base64
import html as html_mod
import json
import time
from pathlib import Path
from string import Template
from typing import Literal

from anthropic import Anthropic
from pydantic import BaseModel, Field
from llama_cloud import LlamaCloud

# =====================================================================
# Section 1: Pydantic Extraction Schemas
# =====================================================================

class LoanApplication(BaseModel):
    borrower_name: str = Field(description="Full name of the borrower (first middle last)")
    ssn: str = Field(description="Social Security Number (format: XXX-XX-XXXX)")
    date_of_birth: str = Field(description="Date of birth (MM/DD/YYYY)")
    current_address: str = Field(description="Full current residential address including unit, city, state, ZIP")
    employer_name: str = Field(description="Name of current employer")
    position: str = Field(description="Job title or position")
    monthly_income: float = Field(description="Monthly base income in dollars")
    loan_amount: float = Field(description="Requested loan amount in dollars")
    property_address: str = Field(description="Address of the property being purchased or refinanced")
    property_value: float = Field(description="Estimated property value or purchase price in dollars")


class W2Form(BaseModel):
    employee_name: str = Field(description="Full employee name (first and last)")
    employee_ssn: str = Field(description="Employee Social Security Number")
    employer_name: str = Field(description="Employer name and address")
    employer_ein: str = Field(description="Employer Identification Number (EIN)")
    wages_tips_other: float = Field(description="Box 1: Wages, tips, other compensation in dollars")
    federal_tax_withheld: float = Field(description="Box 2: Federal income tax withheld in dollars")
    social_security_wages: float = Field(description="Box 3: Social security wages in dollars")
    medicare_wages: float = Field(description="Box 5: Medicare wages and tips in dollars")


class PayStub(BaseModel):
    employee_name: str = Field(description="Employee name (may be in LAST, FIRST format)")
    employer_name: str = Field(description="Employer or company name")
    pay_period_start: str = Field(description="Start date of pay period")
    pay_period_end: str = Field(description="End date of pay period")
    pay_date: str = Field(description="Payment date")
    gross_pay: float = Field(description="Current period gross pay in dollars")
    net_pay: float = Field(description="Current period net pay (take-home) in dollars")
    ytd_gross_pay: float = Field(description="Year-to-date gross pay in dollars")
    ytd_net_pay: float = Field(description="Year-to-date net pay in dollars")
    federal_tax: float = Field(description="Current period federal income tax withheld in dollars")
    pay_frequency: str = Field(description="Pay frequency: weekly, biweekly, semi-monthly, or monthly")


class BankStatement(BaseModel):
    account_holder_name: str = Field(description="Name on the account")
    account_number: str = Field(description="Account number (may be partially masked)")
    statement_period_start: str = Field(description="Statement period start date")
    statement_period_end: str = Field(description="Statement period end date")
    opening_balance: float = Field(description="Beginning balance in dollars")
    closing_balance: float = Field(description="Ending balance in dollars")
    total_deposits: float = Field(description="Total deposits/credits in dollars")
    total_withdrawals: float = Field(description="Total withdrawals/debits in dollars")


# =====================================================================
# Section 2: LlamaParse Extraction (v2 API)
# =====================================================================

def extract_document(
    client: LlamaCloud,
    file_path: str,
    schema_class: type[BaseModel],
    label: str = "",
) -> tuple[dict, dict]:
    """Upload a document, extract with schema, return (result_dict, metadata_dict)."""
    print(f"  Uploading {label or file_path}...")
    file_obj = client.files.create(file=file_path, purpose="extract")

    print(f"  Extracting with {schema_class.__name__} schema...")
    job = client.extract.create(
        file_input=file_obj.id,
        configuration={
            "data_schema": schema_class.model_json_schema(),
            "tier": "agentic",
            "cite_sources": True,
            "confidence_scores": True,
        },
    )
    print(f"  Job created: {job.id}")

    # Poll for completion
    while job.status not in ("COMPLETED", "FAILED", "CANCELLED"):
        time.sleep(3)
        job = client.extract.get(job.id)
        print(f"    Status: {job.status}")

    if job.status != "COMPLETED":
        raise RuntimeError(f"Extraction failed for {label}: {job.status}")

    # Results on the job object
    result = job.extract_result or {}

    # Metadata requires expand parameter
    detailed = client.extract.get(job.id, expand=["extract_metadata"])
    metadata = {}
    if detailed.extract_metadata:
        em = detailed.extract_metadata
        # v2 API: extract_metadata.field_metadata is an ExtractedFieldMetadata object
        # with .document_metadata (dict of field_name -> {confidence, citation, ...})
        if hasattr(em, "field_metadata") and em.field_metadata is not None:
            fm = em.field_metadata
            if hasattr(fm, "document_metadata") and fm.document_metadata:
                metadata = fm.document_metadata
            elif isinstance(fm, dict):
                metadata = fm
        elif isinstance(em, dict):
            metadata = em.get("field_metadata", {})

    # Normalize: if result is a list with one item, unwrap it
    if isinstance(result, list) and len(result) == 1:
        result = result[0]

    print(f"  Done! Extracted {len(result)} fields.")
    return result, metadata


# =====================================================================
# Section 3: LLM-Driven Cross-Document Validation (Claude)
# =====================================================================

class IncomeCheck(BaseModel):
    check_name: str = Field(description="Human-readable label, e.g. 'Stated Income vs W-2 Wages'")
    doc_a_label: str = Field(description="Label of first document, e.g. 'Loan Application'")
    doc_a_value: str = Field(description="The raw extracted value from document A")
    doc_b_label: str = Field(description="Label of second document, e.g. 'W-2'")
    doc_b_value: str = Field(description="The raw extracted value from document B")
    passed: bool = Field(description="Whether the values are consistent (within reasonable tolerance)")
    reasoning: str = Field(description="Brief explanation of the comparison result")
    check_type: Literal["income", "employer", "deposit"] = Field(description="Type of check")


class IncomeMetrics(BaseModel):
    stated_annual_income: float = Field(description="Annual income from loan application (monthly * 12)")
    w2_annual_income: float = Field(description="W-2 Box 1 wages")
    annualized_pay_stub: float = Field(description="Pay stub gross pay annualized based on pay frequency")
    monthly_income: float = Field(description="Monthly income for DTI calculation (from pay stub)")
    income_trend: str = Field(description="'increasing', 'stable', or 'decreasing' based on W-2 vs current pay")
    unexplained_deposits: float = Field(description="Total deposits beyond expected payroll in bank statement")


class LoanProcessorDecision(BaseModel):
    checks: list[IncomeCheck] = Field(description="All cross-document income comparisons")
    metrics: IncomeMetrics = Field(description="Calculated income metrics")
    decision: Literal["COMPLETE", "REVIEW", "FLAG"] = Field(
        description="COMPLETE if all checks pass, REVIEW if minor discrepancies, FLAG if significant issues"
    )
    decision_reasoning: str = Field(description="Overall rationale for the processor's decision")


def validate_income_with_llm(
    app_data: dict, w2_data: dict, stub_data: dict, stmt_data: dict,
) -> LoanProcessorDecision:
    """Use Claude to cross-validate income across all four documents."""
    client = Anthropic()

    prompt = f"""You are a mortgage loan processor performing income verification. You have
extracted data from four documents submitted by a borrower. Cross-validate the income
information and check for consistency.

Document 1 — Loan Application (1003):
{json.dumps(app_data, indent=2)}

Document 2 — W-2 Wage and Tax Statement (prior year):
{json.dumps(w2_data, indent=2)}

Document 3 — Pay Stub (current):
{json.dumps(stub_data, indent=2)}

Document 4 — Bank Statement:
{json.dumps(stmt_data, indent=2)}

Perform these checks:

1. **Stated Income vs W-2**: Compare loan application stated annual income (monthly_income * 12)
   against W-2 Box 1 wages. The W-2 is from the prior year, so a difference may indicate a
   raise or pay cut. Flag if >10% discrepancy.

2. **Stated Income vs Pay Stub Annualized**: Annualize the pay stub gross pay based on
   pay_frequency (biweekly = gross * 26, semi-monthly = gross * 24, monthly = gross * 12).
   Compare against stated income. Should be close.

3. **W-2 vs Pay Stub Annualized**: Compare prior year W-2 against current annualized pay.
   This reveals income trends (raise, pay cut, job change).

4. **Pay Stub Net Pay vs Bank Deposits**: Check if the bank statement shows regular deposits
   consistent with the pay stub net pay. Also note any unexplained deposits that don't match
   payroll (these may indicate undisclosed income that needs documentation).

5. **Employer Name Consistency**: Verify the employer name is consistent across the loan
   application, W-2, and pay stub. Handle abbreviations ("Inc." vs "INC", "Technologies" vs
   "TECH") intelligently.

Calculate income metrics and make a decision:
- **COMPLETE**: All checks pass, income is consistent — ready to submit to underwriting
- **REVIEW**: Minor discrepancies that are likely explainable but need documentation
  (e.g., recent raise, name abbreviation differences, small unexplained deposits)
- **FLAG**: Significant discrepancies or potential fraud indicators — requires senior review"""

    print("  Sending to Claude for income cross-validation...")
    response = client.messages.parse(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        output_format=LoanProcessorDecision,
    )
    return response.parsed_output


# =====================================================================
# Section 4: HTML Report Generation (template-based)
# =====================================================================

TEMPLATE_PATH = Path(__file__).parent / "report_template.html"


def build_html_report(
    documents: list[dict],
    result: LoanProcessorDecision,
) -> str:
    """Generate a self-contained HTML report from the template."""
    decision = result.decision

    decision_colors = {
        "COMPLETE": ("#27AE60", "#EAFAF1", "Ready for Underwriting"),
        "REVIEW": ("#F39C12", "#FEF9E7", "Needs Additional Documentation"),
        "FLAG": ("#E74C3C", "#FDEDEC", "Requires Senior Review"),
    }
    dec_color, dec_bg, dec_label = decision_colors.get(decision, decision_colors["REVIEW"])

    icon_map = {"COMPLETE": "&#10003;", "REVIEW": "!", "FLAG": "&#10007;"}

    template = Template(TEMPLATE_PATH.read_text())
    return template.substitute(
        dec_color=dec_color,
        dec_bg=dec_bg,
        dec_label=dec_label,
        decision=decision,
        decision_icon=icon_map.get(decision, "!"),
        safe_reasoning=html_mod.escape(result.decision_reasoning),
        docs_json=json.dumps(documents, default=str),
        checks_json=json.dumps([c.model_dump() for c in result.checks]),
        metrics_json=json.dumps(result.metrics.model_dump()),
    )


# =====================================================================
# Main Pipeline
# =====================================================================

def main():
    base_dir = Path(__file__).parent
    sample_dir = base_dir / "sample_docs"
    output_dir = base_dir / "output"
    output_dir.mkdir(exist_ok=True)

    # Check sample docs exist
    doc_files = {
        "Loan Application": ("loan_application.pdf", LoanApplication),
        "W-2": ("w2.pdf", W2Form),
        "Pay Stub": ("pay_stub.pdf", PayStub),
        "Bank Statement": ("bank_statement.pdf", BankStatement),
    }
    for label, (fname, _) in doc_files.items():
        fpath = sample_dir / fname
        if not fpath.exists():
            print(f"ERROR: {fpath} not found. Run generate_docs.py first.")
            return

    print("=" * 56)
    print("Loan Income Verification Pipeline")
    print("=" * 56)

    llama_client = LlamaCloud()

    # ── Extract all documents ─────────────────────────────────────
    results = {}
    metadata = {}

    for label, (fname, schema) in doc_files.items():
        fpath = sample_dir / fname
        print(f"\n[{label}] {fname}")
        result, meta = extract_document(llama_client, str(fpath), schema, label=label)
        results[label] = result
        metadata[label] = meta
        print(f"  Result: {json.dumps(result, indent=2, default=str)[:500]}")

    # ── Cross-document validation with Claude ─────────────────────
    print("\n" + "=" * 56)
    print("Income Cross-Validation (Claude)")
    print("=" * 56)

    decision = validate_income_with_llm(
        results["Loan Application"],
        results["W-2"],
        results["Pay Stub"],
        results["Bank Statement"],
    )

    for ch in decision.checks:
        icon = "PASS" if ch.passed else "FLAG"
        print(f"  [{icon}] {ch.check_name}")
        print(f"         {ch.doc_a_label}: {ch.doc_a_value}")
        print(f"         {ch.doc_b_label}: {ch.doc_b_value}")
        print(f"         Reasoning: {ch.reasoning}")

    print(f"\n  Decision: {decision.decision}")
    print(f"  Reasoning: {decision.decision_reasoning}")

    print(f"\n  Income Metrics:")
    m = decision.metrics
    print(f"    Stated Annual:     ${m.stated_annual_income:,.2f}")
    print(f"    W-2 Annual:        ${m.w2_annual_income:,.2f}")
    print(f"    Pay Stub Annual:   ${m.annualized_pay_stub:,.2f}")
    print(f"    Monthly Income:    ${m.monthly_income:,.2f}")
    print(f"    Income Trend:      {m.income_trend}")
    print(f"    Unexplained Deps:  ${m.unexplained_deposits:,.2f}")

    # ── Build report data ─────────────────────────────────────────
    documents_for_report = []

    field_labels = {
        "Loan Application": {
            "borrower_name": "Borrower Name", "ssn": "SSN",
            "date_of_birth": "Date of Birth", "current_address": "Address",
            "employer_name": "Employer", "position": "Position",
            "monthly_income": "Monthly Income", "loan_amount": "Loan Amount",
            "property_address": "Property Address", "property_value": "Property Value",
        },
        "W-2": {
            "employee_name": "Employee Name", "employee_ssn": "SSN",
            "employer_name": "Employer", "employer_ein": "EIN",
            "wages_tips_other": "Box 1: Wages", "federal_tax_withheld": "Box 2: Federal Tax",
            "social_security_wages": "Box 3: SS Wages", "medicare_wages": "Box 5: Medicare Wages",
        },
        "Pay Stub": {
            "employee_name": "Employee Name", "employer_name": "Employer",
            "pay_period_start": "Period Start", "pay_period_end": "Period End",
            "pay_date": "Pay Date", "gross_pay": "Gross Pay",
            "net_pay": "Net Pay", "ytd_gross_pay": "YTD Gross",
            "ytd_net_pay": "YTD Net", "federal_tax": "Federal Tax",
            "pay_frequency": "Pay Frequency",
        },
        "Bank Statement": {
            "account_holder_name": "Account Holder", "account_number": "Account #",
            "statement_period_start": "Period Start", "statement_period_end": "Period End",
            "opening_balance": "Opening Balance", "closing_balance": "Closing Balance",
            "total_deposits": "Total Deposits", "total_withdrawals": "Total Withdrawals",
        },
    }

    for label, (fname, _) in doc_files.items():
        result = results[label]
        meta = metadata[label]
        labels = field_labels[label]
        fields = []

        for field_key, display_name in labels.items():
            value = result.get(field_key, "N/A")

            # Format dollar amounts
            if isinstance(value, (int, float)) and any(
                k in field_key for k in ("income", "amount", "balance", "pay", "tax", "wages", "value",
                                          "deposits", "withdrawals")
            ):
                value = f"${value:,.2f}"

            # Get confidence score
            confidence = None
            field_meta = meta.get(field_key, {}) if isinstance(meta, dict) else {}
            if isinstance(field_meta, dict):
                confidence = field_meta.get("confidence")

            # Get citation text
            citation = None
            if isinstance(field_meta, dict):
                citations = field_meta.get("citation", [])
                if isinstance(citations, list) and citations:
                    citation = citations[0].get("matching_text", "") if isinstance(citations[0], dict) else ""

            fields.append({
                "label": display_name,
                "key": field_key,
                "value": value,
                "confidence": confidence,
                "citation": citation,
            })

        # Embed PDF as base64 for the source document viewer tab
        pdf_path = sample_dir / fname
        pdf_b64 = base64.b64encode(pdf_path.read_bytes()).decode()

        documents_for_report.append({
            "doc_type": label,
            "source_file": fname,
            "fields": fields,
            "pdf_base64": pdf_b64,
        })

    # ── Generate HTML report ──────────────────────────────────────
    html = build_html_report(documents_for_report, decision)
    out_path = output_dir / "loan_report.html"
    out_path.write_text(html)

    print(f"\n{'=' * 56}")
    print(f"Report generated: {out_path}")
    print(f"Open in browser:  open {out_path}")


if __name__ == "__main__":
    main()
