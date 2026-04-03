"""
KYC Document Verification Pipeline with LlamaParse

Processes 3 KYC documents through LlamaParse Extract, uses Claude for
cross-document validation, and generates an interactive HTML report.

Documents:
  1. Government ID (PA DMV driver's license specimen)
  2. Utility bill (synthetic, matching identity)
  3. Bank statement (Impact Bank dummy, mismatched identity)

Usage:
    export LLAMA_CLOUD_API_KEY=llx-...
    export ANTHROPIC_API_KEY=sk-ant-...
    pip install llama-cloud anthropic pydantic
    python kyc_pipeline.py
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

class GovernmentID(BaseModel):
    full_name: str = Field(description="Full legal name on the ID")
    date_of_birth: str = Field(description="Date of birth (MM/DD/YYYY)")
    address: str = Field(description="Full residential address including apartment/unit number, city, state, and ZIP")
    id_number: str = Field(description="Driver's license or ID number")
    expiration_date: str = Field(description="Document expiration date")
    document_type: str = Field(description="Type of ID: driver_license, passport, or state_id")


class UtilityBill(BaseModel):
    account_holder_name: str = Field(description="Name of the account holder")
    service_address: str = Field(description="Full service address including apartment/unit, city, state, ZIP")
    billing_date: str = Field(description="Date the bill was issued")
    due_date: str = Field(description="Payment due date")
    total_amount_due: float = Field(description="Total amount due in dollars")
    account_number: str = Field(description="Utility account number")
    utility_provider: str = Field(description="Name of the utility company")


class BankStatement(BaseModel):
    account_holder_name: str = Field(description="Name on the account")
    address: str = Field(description="Full mailing address of account holder including city, state, ZIP")
    account_number: str = Field(description="Account number (may be partially masked)")
    statement_period: str = Field(description="Statement date range (e.g. 'March 1 - March 31, 2026')")
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

class FieldComparison(BaseModel):
    check_name: str = Field(description="Human-readable label, e.g. 'Name Match: ID vs Utility Bill'")
    doc_a_label: str = Field(description="Label of first document, e.g. 'Government ID'")
    doc_a_value: str = Field(description="The raw extracted value from document A")
    doc_b_label: str = Field(description="Label of second document, e.g. 'Utility Bill'")
    doc_b_value: str = Field(description="The raw extracted value from document B")
    passed: bool = Field(description="Whether the values plausibly refer to the same person/address")
    reasoning: str = Field(description="Brief explanation of why this is a match or mismatch")
    check_type: Literal["name", "address"] = Field(description="Type of comparison")


class KYCDecision(BaseModel):
    checks: list[FieldComparison] = Field(description="All cross-document comparisons")
    decision: Literal["PASS", "REVIEW", "FAIL"] = Field(
        description="PASS if all checks pass, REVIEW if mixed, FAIL if critical identity mismatch"
    )
    decision_reasoning: str = Field(description="Overall rationale for the KYC decision")


def validate_documents_with_llm(
    id_data: dict, bill_data: dict, stmt_data: dict,
) -> KYCDecision:
    """Use Claude to compare identity fields across documents."""
    client = Anthropic()

    prompt = f"""You are a KYC compliance analyst. Compare the extracted data from three
identity documents submitted by an applicant. For each pair of documents, check whether
the name and address refer to the same person/location. Handle abbreviations
(e.g., "J." for "Jason"), name ordering ("SAMPLE, ANDREW" vs "ANDREW SAMPLE"),
and address format differences ("Street" vs "St", with/without zip+4) intelligently.

Document 1 — Government ID:
{json.dumps(id_data, indent=2)}

Document 2 — Utility Bill:
{json.dumps(bill_data, indent=2)}

Document 3 — Bank Statement:
{json.dumps(stmt_data, indent=2)}

Perform these 4 comparisons:
1. Name: Government ID vs Utility Bill
2. Name: Government ID vs Bank Statement
3. Address: Government ID vs Utility Bill
4. Address: Government ID vs Bank Statement

Then decide:
- PASS: All checks pass — auto-approve
- REVIEW: Some checks fail — send to analyst for review
- FAIL: All name checks fail — different individuals, reject"""

    print("  Sending to Claude for cross-document reasoning...")
    response = client.messages.parse(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        output_format=KYCDecision,
    )
    return response.parsed_output


# =====================================================================
# Section 4: HTML Report Generation (template-based)
# =====================================================================

TEMPLATE_PATH = Path(__file__).parent / "report_template.html"


def build_html_report(
    documents: list[dict],
    kyc_result: KYCDecision,
) -> str:
    """Generate a self-contained HTML report from the template."""
    decision = kyc_result.decision

    decision_colors = {
        "PASS": ("#27AE60", "#EAFAF1", "Approved"),
        "REVIEW": ("#F39C12", "#FEF9E7", "Manual Review Required"),
        "FAIL": ("#E74C3C", "#FDEDEC", "Rejected"),
    }
    dec_color, dec_bg, dec_label = decision_colors.get(decision, decision_colors["REVIEW"])

    icon_map = {"PASS": "&#10003;", "REVIEW": "!", "FAIL": "&#10007;"}

    template = Template(TEMPLATE_PATH.read_text())
    return template.substitute(
        dec_color=dec_color,
        dec_bg=dec_bg,
        dec_label=dec_label,
        decision=decision,
        decision_icon=icon_map.get(decision, "!"),
        safe_reasoning=html_mod.escape(kyc_result.decision_reasoning),
        docs_json=json.dumps(documents, default=str),
        checks_json=json.dumps([c.model_dump() for c in kyc_result.checks]),
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
        "Government ID": ("drivers_license.pdf", GovernmentID),
        "Utility Bill": ("utility_bill.pdf", UtilityBill),
        "Bank Statement": ("bank_statement.pdf", BankStatement),
    }
    for label, (fname, _) in doc_files.items():
        fpath = sample_dir / fname
        if not fpath.exists():
            print(f"ERROR: {fpath} not found. Run generate_docs.py first.")
            return

    print("=" * 56)
    print("KYC Document Verification Pipeline")
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
    print("Cross-Document Validation (Claude)")
    print("=" * 56)

    kyc_result = validate_documents_with_llm(
        results["Government ID"],
        results["Utility Bill"],
        results["Bank Statement"],
    )

    for ch in kyc_result.checks:
        icon = "PASS" if ch.passed else "FAIL"
        print(f"  [{icon}] {ch.check_name}")
        print(f"         {ch.doc_a_label}: {ch.doc_a_value}")
        print(f"         {ch.doc_b_label}: {ch.doc_b_value}")
        print(f"         Reasoning: {ch.reasoning}")

    print(f"\n  KYC Decision: {kyc_result.decision}")
    print(f"  Reasoning: {kyc_result.decision_reasoning}")

    # ── Build report data ─────────────────────────────────────────
    documents_for_report = []

    field_labels = {
        "Government ID": {
            "full_name": "Full Name", "date_of_birth": "Date of Birth",
            "address": "Address", "id_number": "ID Number",
            "expiration_date": "Expiration", "document_type": "Document Type",
        },
        "Utility Bill": {
            "account_holder_name": "Account Holder", "service_address": "Service Address",
            "billing_date": "Bill Date", "due_date": "Due Date",
            "total_amount_due": "Amount Due", "account_number": "Account #",
            "utility_provider": "Provider",
        },
        "Bank Statement": {
            "account_holder_name": "Account Holder", "address": "Address",
            "account_number": "Account #", "statement_period": "Statement Period",
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
    html = build_html_report(documents_for_report, kyc_result)
    out_path = output_dir / "kyc_report.html"
    out_path.write_text(html)

    print(f"\n{'=' * 56}")
    print(f"Report generated: {out_path}")
    print(f"Open in browser:  open {out_path}")


if __name__ == "__main__":
    main()
