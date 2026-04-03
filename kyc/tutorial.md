# KYC Document Verification with LlamaParse

> Extract identity data from government IDs, utility bills, and bank statements — then use Claude to cross-validate across documents and automate customer verification.

## Why KYC Document Processing Matters

Know Your Customer (KYC) is a regulatory requirement for financial institutions. Every bank, fintech, and payment processor must verify customer identity before opening accounts. This involves collecting documents — government IDs, proof of address, bank statements — and manually extracting and cross-checking information across them.

The challenge is scale and format diversity. A utility bill from one provider looks completely different from another. Bank statements vary wildly across institutions. Many are scanned images with no text layer. Manual review costs **$2,200 per case** at traditional banks, and even small parsing errors compound: at 95% per-field accuracy across 10 fields, only **60% of applications pass straight-through processing**. At 99%, that jumps to 90%.

[LlamaExtract](https://developers.llamaindex.ai/python/cloud/llamaextract/getting_started/) — LlamaParse's structured extraction feature — maps directly to this problem. Define a schema, get back JSON with per-field confidence scores and source citations. Know how confident the extraction is, and trace every value back to its source for audit compliance.

## What We'll Build

A 2-step KYC verification pipeline:

1. **Identification (CIP)**: Extract name, DOB, address, and ID number from a government-issued driver's license using [LlamaExtract](https://developers.llamaindex.ai/python/cloud/llamaextract/getting_started/sdk/)
2. **Due Diligence (CDD)**: Extract fields from a utility bill and bank statement, then use Claude to cross-validate names and addresses against the ID with natural language reasoning

The pipeline produces an HTML report showing extracted fields with confidence scores, cross-document validation with per-check reasoning, and an overall KYC decision (pass / review / fail).

### Sample Documents

We use three documents with intentionally different characteristics:


| Document             | Source                   | Identity            | OCR Challenge                                                 |
| -------------------- | ------------------------ | ------------------- | ------------------------------------------------------------- |
| **Driver's License** | PA DMV official specimen | ANDREW JASON SAMPLE | Photo, watermark, barcode, multi-field layout                 |
| **Utility Bill**     | Synthetic (reportlab)    | ANDREW J. SAMPLE    | Multi-column boxes, nested charge tiers, bar chart, footnotes |
| **Bank Statement**   | Impact Bank real sample  | JAMES C. MORRISON   | **Image-based PDF** (no text layer), multiple table schemas   |


The utility bill matches the ID identity (with a name abbreviation variant). The bank statement deliberately uses a different person — the cross-validation step will catch this mismatch.

## Prerequisites

```bash
pip install 'llama-cloud>=2.1' anthropic pydantic reportlab requests Pillow
export LLAMA_CLOUD_API_KEY=llx-...
export ANTHROPIC_API_KEY=sk-ant-...
```

Get your LlamaParse API key from [cloud.llamaindex.ai](https://cloud.llamaindex.ai) and your Anthropic API key from [console.anthropic.com](https://console.anthropic.com).

Generate the sample documents (downloads real specimens + generates synthetic utility bill):

```bash
cd sample_docs/
python generate_docs.py
```

## Step 1: Identity Extraction

### Define the Schema

Each document type gets a Pydantic model that tells LlamaParse exactly what fields to extract:

```python
from pydantic import BaseModel, Field

class GovernmentID(BaseModel):
    full_name: str = Field(description="Full legal name on the ID")
    date_of_birth: str = Field(description="Date of birth (MM/DD/YYYY)")
    address: str = Field(
        description="Full residential address including apartment/unit number, city, state, and ZIP"
    )
    id_number: str = Field(description="Driver's license or ID number")
    expiration_date: str = Field(description="Document expiration date")
    document_type: str = Field(description="Type of ID: driver_license, passport, or state_id")
```

The `description` field is important — it guides the extraction model on what to look for and how to format the output.

### Extract with LlamaParse

Upload the document, create an extraction job with [confidence scores and citations](https://developers.llamaindex.ai/python/cloud/llamaextract/features/options/) enabled, then poll for results:

```python
import time
from llama_cloud import LlamaCloud

client = LlamaCloud()  # uses LLAMA_CLOUD_API_KEY env var

# Upload
file_obj = client.files.create(file="sample_docs/drivers_license.pdf", purpose="extract")

# Create extraction job
job = client.extract.create(
    file_input=file_obj.id,
    configuration={
        "data_schema": GovernmentID.model_json_schema(),
        "tier": "agentic",
        "cite_sources": True,
        "confidence_scores": True,
    },
)

# Poll for completion
while job.status not in ("COMPLETED", "FAILED", "CANCELLED"):
    time.sleep(3)
    job = client.extract.get(job.id)

# Access extracted data
id_data = job.extract_result  # {"full_name": "ANDREW JASON SAMPLE", ...}

# Access metadata (confidence scores + citations) — requires expand
detailed = client.extract.get(job.id, expand=["extract_metadata"])
id_meta = detailed.extract_metadata
```

### What Comes Back

The `extract_result` contains the extracted fields as a dictionary:

```json
{
  "full_name": "ANDREW JASON SAMPLE",
  "date_of_birth": "01/07/1973",
  "address": "123 MAIN STREET APT. 1, HARRISBURG, PA 17101-0000",
  "id_number": "99 999 999",
  "expiration_date": "01/08/2026",
  "document_type": "driver_license"
}
```

The `extract_metadata` includes per-field confidence scores and source citations:

```json
{
  "field_metadata": {
    "full_name": {
      "parsing_confidence": 0.989,
      "extraction_confidence": 0.854,
      "confidence": 0.845,
      "citation": [{
        "page": 1,
        "matching_text": "Andrew Sample",
        "bounding_boxes": [{"x": 25, "y": 253, "w": 160, "h": 30}],
        "page_dimensions": {"width": 485, "height": 306}
      }]
    }
  }
}
```

Each field gets three confidence scores (`parsing_confidence`, `extraction_confidence`, and a combined `confidence`) plus a [citation](https://developers.llamaindex.ai/python/cloud/llamaextract/examples/extract_data_with_citations/) pointing to the exact text and bounding box in the source document. This is the audit trail that KYC compliance requires.

## Step 2: Due Diligence & Cross-Validation

### Define Schemas for Supplementary Documents

```python
class UtilityBill(BaseModel):
    account_holder_name: str = Field(description="Name of the account holder")
    service_address: str = Field(
        description="Full service address including apartment/unit, city, state, ZIP"
    )
    billing_date: str = Field(description="Date the bill was issued")
    due_date: str = Field(description="Payment due date")
    total_amount_due: float = Field(description="Total amount due in dollars")
    account_number: str = Field(description="Utility account number")
    utility_provider: str = Field(description="Name of the utility company")


class BankStatement(BaseModel):
    account_holder_name: str = Field(description="Name on the account")
    address: str = Field(
        description="Full mailing address of account holder including city, state, ZIP"
    )
    account_number: str = Field(description="Account number (may be partially masked)")
    statement_period: str = Field(description="Statement date range")
    opening_balance: float = Field(description="Beginning balance in dollars")
    closing_balance: float = Field(description="Ending balance in dollars")
    total_deposits: float = Field(description="Total deposits/credits in dollars")
    total_withdrawals: float = Field(description="Total withdrawals/debits in dollars")
```

### Extract All Documents

We use a helper to extract each document with the same pattern:

```python
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
    metadata = {}
    if detailed.extract_metadata:
        em = detailed.extract_metadata
        if isinstance(em, dict):
            metadata = em.get("field_metadata", {})
        elif hasattr(em, "field_metadata"):
            metadata = em.field_metadata or {}
    return result, metadata

# Extract all three documents
id_data, id_meta = extract_document(client, "sample_docs/drivers_license.pdf", GovernmentID)
bill_data, bill_meta = extract_document(client, "sample_docs/utility_bill.pdf", UtilityBill)
stmt_data, stmt_meta = extract_document(client, "sample_docs/bank_statement.pdf", BankStatement)
```

Note that the bank statement is an **image-based PDF** with no text layer — simple text extraction tools would return nothing. LlamaParse uses its agentic tier to read the document visually.

### Cross-Document Validation with Claude

Instead of writing brittle string-matching rules to compare names and addresses, we send all three extraction results to Claude and let it reason about identity matches. Claude handles name abbreviations ("J." for "Jason"), name ordering ("SAMPLE, ANDREW" vs "ANDREW SAMPLE"), and address format differences ("Street" vs "St", zip+4 vs zip) natively.

First, define the output schema using Pydantic:

```python
from typing import Literal
from anthropic import Anthropic

class FieldComparison(BaseModel):
    check_name: str = Field(description="E.g. 'Name Match: ID vs Utility Bill'")
    doc_a_label: str = Field(description="Label of first document")
    doc_a_value: str = Field(description="Extracted value from document A")
    doc_b_label: str = Field(description="Label of second document")
    doc_b_value: str = Field(description="Extracted value from document B")
    passed: bool = Field(description="Whether values refer to the same person/address")
    reasoning: str = Field(description="Explanation of match/mismatch")
    check_type: Literal["name", "address"]


class KYCDecision(BaseModel):
    checks: list[FieldComparison]
    decision: Literal["PASS", "REVIEW", "FAIL"]
    decision_reasoning: str = Field(description="Overall rationale for the KYC decision")
```

Then call Claude with structured output:

```python
def validate_documents_with_llm(id_data, bill_data, stmt_data):
    client = Anthropic()

    prompt = f"""You are a KYC compliance analyst. Compare the extracted data from three
identity documents. For each pair, check whether the name and address refer to the same
person/location. Handle abbreviations, name ordering, and address format differences.

Document 1 — Government ID:
{json.dumps(id_data, indent=2)}

Document 2 — Utility Bill:
{json.dumps(bill_data, indent=2)}

Document 3 — Bank Statement:
{json.dumps(stmt_data, indent=2)}

Perform 4 comparisons (name and address for each document pair against the ID).
Then decide: PASS (all match), REVIEW (some mismatch), or FAIL (critical identity mismatch)."""

    response = client.messages.parse(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        output_format=KYCDecision,
    )
    return response.parsed_output
```

`messages.parse()` returns a validated Pydantic model directly — no JSON parsing needed. Each check includes a `reasoning` field explaining the match/mismatch decision:

```
[PASS] Name Match: Government ID vs Utility Bill
       Reasoning: 'Andrew' matches, 'J.' is an abbreviation of 'Jason',
       and 'Sample' matches. Casing differences are irrelevant.

[FAIL] Name Match: Government ID vs Bank Statement
       Reasoning: 'Andrew Jason Sample' shares no common names with
       'James C. Morrison'. This is a critical identity mismatch.
```

This is the key advantage of LLM-driven validation — the reasoning is transparent and handles edge cases that hard-coded rules would miss.

## Generating the Report

The full pipeline script (`kyc_pipeline.py`) generates a self-contained HTML report with:

- **KYC Decision Banner** — color-coded pass (green) / review (yellow) / fail (red) with Claude's reasoning
- **Document Extraction Cards** — extracted fields per document with confidence scores and source citations
- **Cross-Document Validation Table** — each check with compared values, pass/fail status, and reasoning

The report uses LlamaIndex brand styling and requires no external dependencies to view.

## Running the Full Pipeline

```bash
cd kyc/

# 1. Generate sample documents (downloads real specimens + generates synthetic bill)
python sample_docs/generate_docs.py

# 2. Run the KYC pipeline (extraction + validation + report)
python kyc_pipeline.py

# 3. View the report
open output/kyc_report.html
```

## What's Next

This tutorial demonstrates the foundation — document parsing with LlamaParse and cross-document reasoning with Claude. A production KYC system would add:

- **More document types**: Lease agreements, tax returns (W-2, 1040), pay stubs
- **Sanctions/PEP screening**: Check extracted names against OFAC, EU, and UN watchlists
- **Risk scoring**: Combine confidence scores, validation results, and business rules into a composite risk score
- **Agentic pipeline**: Chain multiple AI agents for classification, extraction, validation, screening, and decision-making
- **Batch processing**: Use LlamaParse webhooks to process documents asynchronously at scale

---

*Built with [LlamaParse](https://cloud.llamaindex.ai) and [Claude](https://www.anthropic.com) by [LlamaIndex*](https://www.llamaindex.ai)