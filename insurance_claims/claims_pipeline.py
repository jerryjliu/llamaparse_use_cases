"""
Auto Claims Coverage Verification Pipeline with LlamaParse

Processes 4 insurance documents through LlamaParse Extract, uses Claude for
cross-document coverage verification, and generates an interactive HTML report.

Documents:
  1. ACORD 2 Auto Loss Notice (AcroForm-filled)
  2. Policy Declarations Page (synthetic, reportlab)
  3. Accident Report — Missouri Form 1140 (AcroForm-filled)
  4. Repair Estimate — FL DACS Body Shop Form (AcroForm-filled)

Usage:
    export LLAMA_CLOUD_API_KEY=llx-...
    export ANTHROPIC_API_KEY=sk-ant-...
    pip install 'llama-cloud>=2.1' anthropic pydantic
    python claims_pipeline.py
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


class PolicyDeclarations(BaseModel):
    """Auto Insurance Declarations Page"""
    named_insured: str = Field(description="Name of the named insured on the policy")
    insured_address: str = Field(description="Mailing address of the named insured")
    policy_number: str = Field(description="Policy number")
    policy_effective_date: str = Field(description="Policy effective/start date")
    policy_expiration_date: str = Field(description="Policy expiration/end date")
    carrier_name: str = Field(description="Insurance company name")
    vehicle_year: str = Field(description="Year of the covered vehicle")
    vehicle_make: str = Field(description="Make of the covered vehicle")
    vehicle_model: str = Field(description="Model of the covered vehicle")
    vehicle_vin: str = Field(description="VIN of the covered vehicle")
    collision_coverage: bool = Field(description="Whether collision coverage is included")
    collision_deductible: float = Field(description="Collision deductible amount in dollars")
    collision_limit: float = Field(description="Collision coverage limit in dollars")
    comprehensive_deductible: float = Field(description="Comprehensive deductible amount in dollars")
    bodily_injury_limit: str = Field(description="Bodily injury liability limit (e.g. '100000/300000')")
    property_damage_limit: float = Field(description="Property damage liability limit in dollars")


class AccidentReport(BaseModel):
    """Driver-Filed Accident Report (Missouri Form 1140)"""
    driver_name: str = Field(description="Full name of the driver filing the report")
    driver_address: str = Field(description="Full address of the driver")
    accident_date: str = Field(description="Date of the accident (MM/DD/YYYY)")
    accident_time: str = Field(description="Time of the accident")
    accident_location: str = Field(description="Location/intersection where the accident occurred")
    vehicle_make: str = Field(description="Make of the driver's vehicle")
    vehicle_model: str = Field(description="Model of the driver's vehicle")
    accident_description: str = Field(description="Narrative description of how the accident occurred")
    other_driver_name: str = Field(description="Name of the other driver involved")
    other_vehicle_make: str = Field(description="Make of the other driver's vehicle")
    police_notified: bool = Field(description="Whether police were notified")
    insurance_company: str = Field(description="Insurance company name listed on the report")


class RepairEstimate(BaseModel):
    """Auto Body Repair Estimate"""
    customer_name: str = Field(description="Name of the vehicle owner/customer on the estimate")
    vehicle_year_make: str = Field(description="Year and make of the vehicle (e.g. '2015 Lexus')")
    vehicle_model: str = Field(description="Model of the vehicle")
    vehicle_vin: str = Field(description="VIN of the vehicle")
    estimate_date: str = Field(description="Date the estimate was written")
    repair_shop_name: str = Field(description="Name of the repair facility")
    total_labor: str = Field(description="Total labor cost in dollars")
    total_parts: str = Field(description="Total replacement parts cost in dollars")
    estimate_total: str = Field(description="Grand total of the repair estimate in dollars")
    line_item_descriptions: str = Field(description="Comma-separated list of all repair line item descriptions")


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

class CoverageCheck(BaseModel):
    check_name: str = Field(description="Human-readable label, e.g. 'Identity: Insured vs Claimant'")
    doc_a_label: str = Field(description="Label of first document, e.g. 'Policy Declarations'")
    doc_a_value: str = Field(description="The raw extracted value from document A")
    doc_b_label: str = Field(description="Label of second document, e.g. 'ACORD 2'")
    doc_b_value: str = Field(description="The raw extracted value from document B")
    passed: bool = Field(description="Whether the check passes (values are consistent/covered)")
    reasoning: str = Field(description="Brief explanation of the check result")
    check_type: Literal["identity", "coverage", "vehicle", "financial", "consistency"] = Field(
        description="Type of verification check"
    )


class CoverageAssessment(BaseModel):
    repair_total: float = Field(description="Total repair estimate amount in dollars")
    deductible: float = Field(description="Applicable deductible amount in dollars")
    net_payable: float = Field(description="Amount payable after deductible (repair_total - deductible)")
    within_policy_limits: bool = Field(description="Whether the repair total is within policy coverage limits")
    coverage_type: str = Field(description="Type of coverage applicable, e.g. 'Collision'")


class ClaimsDecision(BaseModel):
    checks: list[CoverageCheck] = Field(description="All cross-document verification checks")
    assessment: CoverageAssessment = Field(description="Financial coverage assessment")
    decision: Literal["APPROVE", "REVIEW", "DENY"] = Field(
        description="APPROVE if all checks pass, REVIEW if minor issues, DENY if coverage fails"
    )
    decision_reasoning: str = Field(description="Overall rationale for the claims decision")


def verify_coverage_with_llm(
    loss_data: dict, policy_data: dict, report_data: dict, estimate_data: dict,
) -> ClaimsDecision:
    """Use Claude to cross-validate coverage across all four documents."""
    client = Anthropic()

    prompt = f"""You are an auto insurance claims adjuster performing initial coverage verification
on a new claim. You have extracted data from four documents. Cross-validate the information
and determine if the claim should be approved, reviewed, or denied.

Document 1 — ACORD 2 Auto Loss Notice (claim filed by insured):
{json.dumps(loss_data, indent=2)}

Document 2 — Policy Declarations Page (insurer's policy record):
{json.dumps(policy_data, indent=2)}

Document 3 — Accident Report (driver-filed report):
{json.dumps(report_data, indent=2)}

Document 4 — Repair Estimate (body shop estimate):
{json.dumps(estimate_data, indent=2)}

Perform these verification checks:

1. **Identity Match — Insured vs Claimant**: Compare the named insured on the policy
   declarations against the insured name on the ACORD 2 loss notice. Handle name format
   differences (middle initial, ordering) intelligently.

2. **Identity Match — Claimant vs Accident Report**: Compare the ACORD 2 insured name
   against the driver name on the accident report.

3. **Policy Active on Loss Date**: Check if the date of loss falls within the policy
   effective and expiration dates.

4. **Accident Date Consistency**: Compare the date of loss on the ACORD 2 against the
   accident date on the accident report. They should match.

5. **Vehicle Match**: Compare the vehicle (make, model, VIN) between the policy
   declarations and the ACORD 2 loss notice.

6. **Coverage Type**: Verify that the policy has collision coverage (since this is a
   collision loss). Check if collision_coverage is true on the declarations page.

7. **Accident Description Consistency**: Compare the loss description on the ACORD 2
   against the accident description on the accident report. They should describe the
   same incident.

8. **Estimate Line Items vs Damage Description**: Review the repair estimate line items
   and compare against the accident description. Flag any repair items that seem
   inconsistent with the described damage (e.g., front-end work on a rear-end collision).

9. **Estimate vs Initial Damage Estimate**: Compare the body shop estimate total against
   the initial estimated damage amount on the ACORD 2. Note any significant variance.

10. **Financial Assessment**: Calculate the net payable (estimate total minus collision
    deductible) and verify it's within the collision coverage limit.

Then make a decision:
- **APPROVE**: All checks pass, coverage confirmed, no discrepancies — ready for payment
- **REVIEW**: Coverage confirmed but discrepancies need investigation (inconsistent repair
  items, significant estimate variance, etc.) — needs adjuster follow-up
- **DENY**: Policy not active, loss type not covered, or critical issues found"""

    print("  Sending to Claude for coverage verification...")
    response = client.messages.parse(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        output_format=ClaimsDecision,
    )
    return response.parsed_output


# =====================================================================
# Section 4: HTML Report Generation (template-based)
# =====================================================================

TEMPLATE_PATH = Path(__file__).parent / "report_template.html"


def build_html_report(
    documents: list[dict],
    result: ClaimsDecision,
) -> str:
    """Generate a self-contained HTML report from the template."""
    decision = result.decision

    decision_colors = {
        "APPROVE": ("#27AE60", "#EAFAF1", "Approved for Payment"),
        "REVIEW": ("#F39C12", "#FEF9E7", "Needs Adjuster Review"),
        "DENY": ("#E74C3C", "#FDEDEC", "Claim Denied"),
    }
    dec_color, dec_bg, dec_label = decision_colors.get(decision, decision_colors["REVIEW"])

    icon_map = {"APPROVE": "&#10003;", "REVIEW": "!", "DENY": "&#10007;"}

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
        assessment_json=json.dumps(result.assessment.model_dump()),
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
        "ACORD 2 Loss Notice": ("acord2_filled.pdf", AutoLossNotice),
        "Policy Declarations": ("declarations_page.pdf", PolicyDeclarations),
        "Accident Report": ("accident_report.pdf", AccidentReport),
        "Repair Estimate": ("repair_estimate.pdf", RepairEstimate),
    }
    for label, (fname, _) in doc_files.items():
        fpath = sample_dir / fname
        if not fpath.exists():
            print(f"ERROR: {fpath} not found. Run sample_docs/generate_docs.py first.")
            return

    print("=" * 56)
    print("Auto Claims Coverage Verification Pipeline")
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
    print("Coverage Verification (Claude)")
    print("=" * 56)

    decision = verify_coverage_with_llm(
        results["ACORD 2 Loss Notice"],
        results["Policy Declarations"],
        results["Accident Report"],
        results["Repair Estimate"],
    )

    for ch in decision.checks:
        icon = "PASS" if ch.passed else "FLAG"
        print(f"  [{icon}] {ch.check_name}")
        print(f"         {ch.doc_a_label}: {ch.doc_a_value}")
        print(f"         {ch.doc_b_label}: {ch.doc_b_value}")
        print(f"         Reasoning: {ch.reasoning}")

    print(f"\n  Decision: {decision.decision}")
    print(f"  Reasoning: {decision.decision_reasoning}")

    a = decision.assessment
    print(f"\n  Coverage Assessment:")
    print(f"    Repair Total:       ${a.repair_total:,.2f}")
    print(f"    Deductible:         ${a.deductible:,.2f}")
    print(f"    Net Payable:        ${a.net_payable:,.2f}")
    print(f"    Coverage Type:      {a.coverage_type}")
    print(f"    Within Limits:      {'Yes' if a.within_policy_limits else 'No'}")

    # ── Build report data ─────────────────────────────────────────
    documents_for_report = []

    field_labels = {
        "ACORD 2 Loss Notice": {
            "insured_name": "Insured Name", "insured_address": "Address",
            "policy_number": "Policy Number", "carrier_name": "Carrier",
            "date_of_loss": "Date of Loss", "time_of_loss": "Time of Loss",
            "loss_location": "Loss Location", "loss_description": "Loss Description",
            "vehicle_year": "Vehicle Year", "vehicle_make": "Vehicle Make",
            "vehicle_model": "Vehicle Model", "vehicle_vin": "VIN",
            "estimated_damage": "Estimated Damage", "police_report_number": "Police Report #",
        },
        "Policy Declarations": {
            "named_insured": "Named Insured", "insured_address": "Address",
            "policy_number": "Policy Number",
            "policy_effective_date": "Effective Date", "policy_expiration_date": "Expiration Date",
            "carrier_name": "Carrier",
            "vehicle_year": "Vehicle Year", "vehicle_make": "Vehicle Make",
            "vehicle_model": "Vehicle Model", "vehicle_vin": "VIN",
            "collision_coverage": "Collision Coverage", "collision_deductible": "Collision Deductible",
            "collision_limit": "Collision Limit",
            "comprehensive_deductible": "Comprehensive Deductible",
            "bodily_injury_limit": "BI Limit", "property_damage_limit": "PD Limit",
        },
        "Accident Report": {
            "driver_name": "Driver Name", "driver_address": "Address",
            "accident_date": "Accident Date", "accident_time": "Time",
            "accident_location": "Location",
            "vehicle_make": "Vehicle Make", "vehicle_model": "Vehicle Model",
            "accident_description": "Accident Description",
            "other_driver_name": "Other Driver", "other_vehicle_make": "Other Vehicle",
            "police_notified": "Police Notified", "insurance_company": "Insurance Co.",
        },
        "Repair Estimate": {
            "customer_name": "Customer Name",
            "vehicle_year_make": "Year / Make", "vehicle_model": "Model",
            "vehicle_vin": "VIN", "estimate_date": "Estimate Date",
            "repair_shop_name": "Repair Shop",
            "total_labor": "Total Labor", "total_parts": "Total Parts",
            "estimate_total": "Estimate Total",
            "line_item_descriptions": "Line Items",
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
                k in field_key for k in ("deductible", "limit", "damage")
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
    out_path = output_dir / "claims_report.html"
    out_path.write_text(html)

    print(f"\n{'=' * 56}")
    print(f"Report generated: {out_path}")
    print(f"Open in browser:  open {out_path}")


if __name__ == "__main__":
    main()
