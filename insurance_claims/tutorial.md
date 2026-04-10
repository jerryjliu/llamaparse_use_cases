# Auto Claims Coverage Verification with LlamaParse

> Extract claim data from ACORD forms, policy declarations, accident reports, and repair estimates — then use Claude to verify coverage and flag discrepancies automatically.

## Why Insurance Claims Processing Matters

Claims adjusters manage 150-200 open claims simultaneously and spend **50-60% of their time on documentation** — re-keying data, cross-referencing policy documents, and chasing missing information. Industry-wide straight-through processing is only **3%** (Datos Insights), meaning 97% of claims require manual handling. The bottleneck is unstructured documents: **97% of claims data is unstructured** (CLM Magazine).

When a new auto claim arrives, the adjuster's first job is coverage verification: confirm the claimant matches the policy, the policy was active on the loss date, the loss type is covered, and the repair estimate is within limits. This requires reading and cross-referencing 3-4 documents — exactly the kind of multi-document extraction and reasoning that [LlamaExtract](https://developers.llamaindex.ai/python/cloud/llamaextract/getting_started/) handles well.

## What We'll Build

A 3-step auto claims coverage verification pipeline:

1. **Extract** structured data from 4 insurance documents using [LlamaExtract](https://developers.llamaindex.ai/python/cloud/llamaextract/getting_started/sdk/)
2. **Cross-validate** with Claude: identity matching, coverage confirmation, accident consistency, repair estimate review
3. **Generate** an HTML report with extracted fields, confidence scores, coverage assessment, and an adjuster recommendation

### Sample Documents

We use four documents with different characteristics:

| Document | Source | Identity | Parsing Challenge |
|----------|--------|----------|-------------------|
| **ACORD 2 Auto Loss Notice** | Florida CFO (AcroForm filled) | MICHAEL R. TORRES | 4-page form, 258 fields, insurance terminology |
| **Policy Declarations Page** | Synthetic (reportlab) | MICHAEL R. TORRES | Multi-section layout, coverage table, vehicle schedule |
| **Accident Report** | Missouri DOR Form 1140 (AcroForm filled) | MICHAEL R. TORRES | 4-page form, checkboxes + dropdowns + narrative |
| **Repair Estimate** | FL DACS Body Shop Form (AcroForm filled) | MICHAEL R. TORRES | Itemized parts/labor table, totals |

All documents share the same insured identity. The repair estimate includes a subtle discrepancy — a "front bumper inspect and refinish" line item on a rear-end collision — which the cross-validation step should flag.

## Prerequisites

```bash
pip install 'llama-cloud>=2.1' anthropic pydantic pypdf reportlab requests
export LLAMA_CLOUD_API_KEY=llx-...
export ANTHROPIC_API_KEY=sk-ant-...
```

Get your LlamaParse API key from [cloud.llamaindex.ai](https://cloud.llamaindex.ai) and your Anthropic API key from [console.anthropic.com](https://console.anthropic.com).

Generate the sample documents (downloads real forms + fills with synthetic data + generates declarations page):

```bash
cd sample_docs/
python generate_docs.py
```

## Step 1: Document Extraction

### Define the Schemas

Each document type gets a Pydantic model that tells LlamaExtract what fields to extract:

```python
from pydantic import BaseModel, Field

class AutoLossNotice(BaseModel):
    """ACORD 2 — Automobile Loss Notice"""
    insured_name: str = Field(description="Name of the insured/policyholder")
    insured_address: str = Field(description="Full address of the insured")
    policy_number: str = Field(description="Insurance policy number")
    carrier_name: str = Field(description="Name of the insurance company")
    date_of_loss: str = Field(description="Date the loss/accident occurred (MM/DD/YYYY)")
    time_of_loss: str = Field(description="Time the accident occurred")
    loss_location: str = Field(description="Location/address where the accident occurred")
    loss_description: str = Field(description="Description of how the accident occurred")
    vehicle_year: str = Field(description="Year of the insured vehicle")
    vehicle_make: str = Field(description="Make of the insured vehicle")
    vehicle_model: str = Field(description="Model of the insured vehicle")
    vehicle_vin: str = Field(description="VIN of the insured vehicle")
    estimated_damage: str = Field(description="Estimated damage amount reported by the insured")
    police_report_number: str = Field(description="Police report number if filed")
```

The `description` field guides the extraction model on what to look for. We define similar schemas for the policy declarations (16 fields including coverage details), accident report (12 fields), and repair estimate (10 fields) — see `claims_pipeline.py` for the complete set.

### Extract with LlamaExtract

Upload each document and extract with [confidence scores and citations](https://developers.llamaindex.ai/python/cloud/llamaextract/features/options/) enabled:

```python
import time
from llama_cloud import LlamaCloud

client = LlamaCloud()  # uses LLAMA_CLOUD_API_KEY env var

# Upload
file_obj = client.files.create(file="sample_docs/acord2_filled.pdf", purpose="extract")

# Create extraction job
job = client.extract.create(
    file_input=file_obj.id,
    configuration={
        "data_schema": AutoLossNotice.model_json_schema(),
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
loss_data = job.extract_result

# Access metadata (confidence scores + citations) — requires expand
detailed = client.extract.get(job.id, expand=["extract_metadata"])
loss_meta = detailed.extract_metadata
```

### What Comes Back

The `extract_result` contains the extracted fields as a dictionary:

```json
{
  "insured_name": "MICHAEL R. TORRES",
  "insured_address": "789 Cedar Lane, Roswell, GA 30076",
  "policy_number": "AUTO-2016-0847291",
  "carrier_name": "SUMMIT MUTUAL INSURANCE CO.",
  "date_of_loss": "02/15/2016",
  "time_of_loss": "3:45 PM",
  "loss_location": "Intersection of Alpharetta Hwy and Holcomb Bridge Rd, Roswell, GA",
  "loss_description": "Insured vehicle was stopped at a red light...",
  "vehicle_year": "2015",
  "vehicle_make": "Lexus",
  "vehicle_model": "RC 350",
  "vehicle_vin": "JTHHE5BC7F5006073",
  "estimated_damage": "$8,000",
  "police_report_number": "RPD-2016-008847"
}
```

Each field also gets [confidence scores and citations](https://developers.llamaindex.ai/python/cloud/llamaextract/examples/extract_data_with_citations/) pointing to the exact source text and bounding box — the audit trail that claims compliance requires.

## Step 2: Coverage Verification with Claude

### Define the Output Schema

Instead of writing coverage-checking rules, we send all extracted data to Claude and let it reason about coverage, identity, and consistency. Define the output structure:

```python
from typing import Literal
from anthropic import Anthropic

class CoverageCheck(BaseModel):
    check_name: str = Field(description="E.g. 'Identity: Insured vs Claimant'")
    doc_a_label: str = Field(description="Label of first document")
    doc_a_value: str = Field(description="Extracted value from document A")
    doc_b_label: str = Field(description="Label of second document")
    doc_b_value: str = Field(description="Extracted value from document B")
    passed: bool = Field(description="Whether the check passes")
    reasoning: str = Field(description="Explanation of the result")
    check_type: Literal["identity", "coverage", "vehicle", "financial", "consistency"]


class CoverageAssessment(BaseModel):
    repair_total: float
    deductible: float
    net_payable: float        # repair_total - deductible
    within_policy_limits: bool
    coverage_type: str        # "Collision", "Comprehensive", etc.


class ClaimsDecision(BaseModel):
    checks: list[CoverageCheck]
    assessment: CoverageAssessment
    decision: Literal["APPROVE", "REVIEW", "DENY"]
    decision_reasoning: str
```

### Call Claude with Structured Output

```python
def verify_coverage_with_llm(loss_data, policy_data, report_data, estimate_data):
    client = Anthropic()

    prompt = f"""You are an auto insurance claims adjuster performing initial coverage
verification. Cross-validate these four documents and check:
1. Identity match (insured vs claimant vs accident report driver)
2. Policy active on loss date
3. Vehicle match by VIN
4. Coverage type applicable
5. Accident descriptions consistent
6. Estimate line items consistent with described damage
7. Financial assessment (estimate vs deductible vs limits)

Document 1 — ACORD 2: {json.dumps(loss_data, indent=2)}
Document 2 — Policy Declarations: {json.dumps(policy_data, indent=2)}
Document 3 — Accident Report: {json.dumps(report_data, indent=2)}
Document 4 — Repair Estimate: {json.dumps(estimate_data, indent=2)}

Decide: APPROVE (all clear), REVIEW (discrepancies need follow-up), DENY (coverage fails)."""

    response = client.messages.parse(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        output_format=ClaimsDecision,
    )
    return response.parsed_output
```

`messages.parse()` returns a validated Pydantic model directly. Each check includes reasoning explaining the result:

```
[PASS] Identity Match — Insured vs Claimant
       Reasoning: Both documents list MICHAEL R. TORRES. Names are identical.

[PASS] Collision Coverage Verification
       Reasoning: Policy carries collision coverage ($500 deductible, $50K limit).
       Loss type is a rear-end collision — covered.

[FLAG] Estimate Line Items vs Damage Description
       Reasoning: Most items are consistent with rear-end collision damage.
       However, 'Front bumper cover — inspect, refinish' is flagged as
       potentially inconsistent. No front-end impact was described.
```

This is the key advantage of LLM-driven verification — Claude catches the subtle front bumper discrepancy that rule-based systems would miss, and explains its reasoning transparently.

## Generating the Report

The full pipeline script (`claims_pipeline.py`) generates a self-contained HTML report with:

- **Decision Banner** — color-coded APPROVE (green) / REVIEW (yellow) / DENY (red) with Claude's reasoning
- **Coverage Assessment Card** — repair total, deductible, net payable, within limits
- **Document Extraction Cards** — 4 tabbed cards with extracted fields, confidence scores, source citations, and embedded PDF viewer
- **Cross-Document Verification Table** — each check with compared values, pass/flag status, and reasoning

## Running the Full Pipeline

```bash
cd insurance_claims/

# 1. Generate sample documents
python sample_docs/generate_docs.py

# 2. Run the claims pipeline (extraction + verification + report)
python claims_pipeline.py

# 3. View the report
open output/claims_report.html
```

## What's Next

This tutorial covers the initial coverage verification steps (FNOL → Coverage → Investigation → Estimation). A production claims system would add:

- **Medical records parsing**: Extract diagnoses, treatment codes, and charges from medical PDFs — the #1 daily pain point for adjusters
- **Fraud detection**: SIU referral logic based on red flags (inconsistent damage, suspicious patterns)
- **Reserve setting**: Calculate expected claim cost based on extracted data
- **Subrogation**: Identify recovery opportunities from at-fault parties
- **Claims management integration**: Push extracted data to Guidewire ClaimCenter, Duck Creek, or other claims systems

---

*Built with [LlamaParse](https://cloud.llamaindex.ai) and [Claude](https://www.anthropic.com) by [LlamaIndex](https://www.llamaindex.ai)*
