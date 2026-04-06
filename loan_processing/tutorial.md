# Loan Income Verification with LlamaParse

> Extract income data from loan applications, W-2s, pay stubs, and bank statements — then use Claude to cross-validate and flag discrepancies before underwriting.

## Why Loan Document Processing Matters

Mortgage loan processors spend **15-20% of their time** on data extraction and **10-15% on cross-checking** documents for income consistency. A single mortgage file can contain **500+ pages** across 15-30 document types. The processor must verify that the borrower's stated income matches across every document — application, tax forms, pay stubs, bank deposits — before submitting to underwriting.

The core challenge is the "income consistency triangle": the same income figure should be verifiable across the loan application (stated income), W-2 (employer-reported annual income), pay stub (current pay rate), and bank statement (actual deposit patterns). Discrepancies — a recent raise, unexplained deposits, employer name abbreviations — are exactly what a processor must catch and document.

[LlamaExtract](https://developers.llamaindex.ai/python/cloud/llamaextract/getting_started/) handles the extraction across these wildly different document formats, returning structured JSON with per-field confidence scores and source citations. Claude then reasons about the cross-document relationships.

## What We'll Build

A loan income verification pipeline in 3 steps:

1. **Extract** structured data from 4 documents using [LlamaExtract](https://developers.llamaindex.ai/python/cloud/llamaextract/getting_started/sdk/)
2. **Cross-validate** with Claude structured outputs: income consistency, employer name matching, deposit pattern analysis
3. **Generate** an HTML report with extraction results, income metrics, validation checks, and a processor recommendation

### Sample Documents

| Document | Source | Identity | Parsing Challenge |
|----------|--------|----------|-------------------|
| **Loan Application** (1003) | Fannie Mae URLA (AcroForm-filled) | SARAH M. CHEN | 15-page form, 639 fields |
| **W-2** | eForms.com (AcroForm-filled) | SARAH M. CHEN | Multi-box layout, tax codes |
| **Pay Stub** | Synthetic (reportlab) | CHEN, SARAH M | No standard format, YTD columns |
| **Bank Statement** | Synthetic (reportlab) | SARAH M. CHEN | Transaction table, running balance |

The W-2 shows **$68,500** (prior year) while the pay stub annualizes to **$72,000** (current) — a raise. The bank statement includes unexplained Zelle/Venmo deposits beyond payroll. Claude will catch both.

## Prerequisites

```bash
pip install 'llama-cloud>=2.1' anthropic pydantic pypdf reportlab requests
export LLAMA_CLOUD_API_KEY=llx-...
export ANTHROPIC_API_KEY=sk-ant-...
```

Get your LlamaParse API key from [cloud.llamaindex.ai](https://cloud.llamaindex.ai) and your Anthropic API key from [console.anthropic.com](https://console.anthropic.com).

Generate the sample documents:

```bash
cd sample_docs/
python generate_docs.py
```

This downloads the 1003 and W-2 fillable PDFs and fills them via AcroForm, then generates synthetic pay stub and bank statement with reportlab.

## Step 1: Define Extraction Schemas

Each document type gets a Pydantic model. The `description` field guides LlamaExtract on what to look for:

```python
from pydantic import BaseModel, Field

class LoanApplication(BaseModel):
    borrower_name: str = Field(description="Full name of the borrower (first middle last)")
    ssn: str = Field(description="Social Security Number (format: XXX-XX-XXXX)")
    date_of_birth: str = Field(description="Date of birth (MM/DD/YYYY)")
    current_address: str = Field(description="Full current residential address")
    employer_name: str = Field(description="Name of current employer")
    position: str = Field(description="Job title or position")
    monthly_income: float = Field(description="Monthly base income in dollars")
    loan_amount: float = Field(description="Requested loan amount in dollars")
    property_address: str = Field(description="Address of the property being purchased")
    property_value: float = Field(description="Estimated property value or purchase price")


class W2Form(BaseModel):
    employee_name: str = Field(description="Full employee name (first and last)")
    employee_ssn: str = Field(description="Employee Social Security Number")
    employer_name: str = Field(description="Employer name and address")
    employer_ein: str = Field(description="Employer Identification Number (EIN)")
    wages_tips_other: float = Field(description="Box 1: Wages, tips, other compensation")
    federal_tax_withheld: float = Field(description="Box 2: Federal income tax withheld")
    social_security_wages: float = Field(description="Box 3: Social security wages")
    medicare_wages: float = Field(description="Box 5: Medicare wages and tips")


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
    federal_tax: float = Field(description="Current period federal income tax withheld")
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
```

## Step 2: Extract Documents with LlamaExtract

Upload each document, run extraction with [confidence scores and citations](https://developers.llamaindex.ai/python/cloud/llamaextract/features/options/) enabled, then poll for results:

```python
import time
from llama_cloud import LlamaCloud

client = LlamaCloud()  # uses LLAMA_CLOUD_API_KEY env var

def extract_document(client, file_path, schema_class, label=""):
    """Upload a document, extract with schema, return (result_dict, metadata_dict)."""
    file_obj = client.files.create(file=file_path, purpose="extract")

    job = client.extract.create(
        file_input=file_obj.id,
        configuration={
            "data_schema": schema_class.model_json_schema(),
            "tier": "agentic",
            "cite_sources": True,
            "confidence_scores": True,
        },
    )

    while job.status not in ("COMPLETED", "FAILED", "CANCELLED"):
        time.sleep(3)
        job = client.extract.get(job.id)

    if job.status != "COMPLETED":
        raise RuntimeError(f"Extraction failed for {label}: {job.status}")

    result = job.extract_result or {}
    detailed = client.extract.get(job.id, expand=["extract_metadata"])
    # ... extract metadata for confidence scores and citations
    return result, metadata
```

The `agentic` tier handles diverse document formats — from the structured 1003 form to the unstructured pay stub layout — without any format-specific configuration.

### What Comes Back

For the W-2:

```json
{
  "employee_name": "SARAH M. CHEN",
  "employee_ssn": "078-05-1120",
  "employer_name": "Horizon Technologies, Inc.\n1200 Congress Ave\nAustin, TX 78701",
  "employer_ein": "74-3285619",
  "wages_tips_other": 68500.0,
  "federal_tax_withheld": 10275.0,
  "social_security_wages": 68500.0,
  "medicare_wages": 68500.0
}
```

Each field includes [confidence scores](https://developers.llamaindex.ai/python/cloud/llamaextract/features/options/) and [source citations](https://developers.llamaindex.ai/python/cloud/llamaextract/examples/extract_data_with_citations/) pointing to the exact text and bounding box in the source document.

## Step 3: Cross-Validate Income with Claude

Instead of writing brittle comparison rules, we send all four extraction results to Claude and let it reason about income consistency. Define the output schema:

```python
from typing import Literal
from anthropic import Anthropic

class IncomeCheck(BaseModel):
    check_name: str = Field(description="E.g. 'Stated Income vs W-2 Wages'")
    doc_a_label: str
    doc_a_value: str
    doc_b_label: str
    doc_b_value: str
    passed: bool
    reasoning: str
    check_type: Literal["income", "employer", "deposit"]


class IncomeMetrics(BaseModel):
    stated_annual_income: float    # from 1003 (monthly * 12)
    w2_annual_income: float        # from W-2 Box 1
    annualized_pay_stub: float     # gross_pay * pay_periods
    monthly_income: float          # for DTI calculation
    income_trend: str              # "increasing", "stable", "decreasing"
    unexplained_deposits: float    # deposits beyond expected payroll


class LoanProcessorDecision(BaseModel):
    checks: list[IncomeCheck]
    metrics: IncomeMetrics
    decision: Literal["COMPLETE", "REVIEW", "FLAG"]
    decision_reasoning: str
```

Then call Claude with structured outputs:

```python
def validate_income_with_llm(app_data, w2_data, stub_data, stmt_data):
    client = Anthropic()

    prompt = f"""You are a mortgage loan processor performing income verification.
Cross-validate the income information across these four documents...

Document 1 — Loan Application: {json.dumps(app_data, indent=2)}
Document 2 — W-2 (prior year): {json.dumps(w2_data, indent=2)}
Document 3 — Pay Stub (current): {json.dumps(stub_data, indent=2)}
Document 4 — Bank Statement: {json.dumps(stmt_data, indent=2)}

Perform these checks:
1. Stated Income vs W-2 (flag if >10% discrepancy)
2. Stated Income vs Pay Stub Annualized
3. W-2 vs Pay Stub Annualized (income trend)
4. Pay Stub Net Pay vs Bank Deposits (unexplained deposits)
5. Employer Name Consistency"""

    response = client.messages.parse(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        output_format=LoanProcessorDecision,
    )
    return response.parsed_output
```

Claude returns a structured decision with calculated income metrics:

```
[PASS]  Stated Income vs Pay Stub Annualized
        Application: $72,000  |  Pay Stub: $72,000
        Current biweekly gross of $2,769.23 × 26 = $72,000, matches stated income.

[FLAG]  Stated Income vs W-2 Wages
        Application: $72,000  |  W-2: $68,500
        ~5.1% discrepancy. W-2 is prior year — consistent with a mid-year raise.
        Needs raise documentation (promotion letter or updated offer letter).

[FLAG]  Unexplained Bank Deposits
        Expected payroll: ~$2,050 biweekly
        Additional: $800 (Zelle) + $750 (Venmo) = $1,550 unexplained
        Source of these funds needs documentation.

Decision: REVIEW — Income is broadly consistent but the W-2/pay stub gap needs
raise documentation, and $1,550 in unexplained deposits need sourcing.
```

## Generating the Report

The full pipeline script (`loan_pipeline.py`) generates a self-contained HTML report with:

- **Income Summary Cards** — side-by-side comparison of stated vs verified income, trend indicator, unexplained deposits
- **Document Extraction Cards** — extracted fields per document with confidence scores and source citations, plus embedded source PDF viewer
- **Cross-Document Validation Table** — each check with compared values, pass/flag status, and reasoning
- **Decision Banner** — color-coded COMPLETE (green) / REVIEW (yellow) / FLAG (red) with Claude's reasoning

## Running the Full Pipeline

```bash
cd loan_processing/

# 1. Generate sample documents
python sample_docs/generate_docs.py

# 2. Run the pipeline (extraction + validation + report)
python loan_pipeline.py

# 3. View the report
open output/loan_report.html
```

## What's Next

This tutorial covers the income verification slice of loan processing (Steps 2-4 of the mortgage workflow: extraction, cross-checking, and processor decision). A production system would add:

- **Document classification**: Automatically identify document types from a mixed upload (LlamaExtract can classify before extracting)
- **More document types**: Tax returns (1040 with schedules), 1099s for self-employment, employment verification letters
- **DTI/LTV calculation**: Combine verified income with debt obligations and property value to compute debt-to-income and loan-to-value ratios
- **Compliance checks**: RAG over the Fannie Mae Selling Guide and FHA handbook for guideline-specific validation
- **LOS integration**: Map extracted fields to Encompass, nCino, or other loan origination system fields

---

*Built with [LlamaParse](https://cloud.llamaindex.ai) and [Claude](https://www.anthropic.com) by [LlamaIndex](https://www.llamaindex.ai)*
