# Loan Income Verification

Automated income verification pipeline for mortgage loan processing using [LlamaExtract](https://developers.llamaindex.ai/python/cloud/llamaextract/getting_started/) and Claude.

## Overview

A loan processor receives documents from a borrower and must verify that stated income is consistent across all of them before submitting to underwriting. This tutorial automates that cross-validation.

| Document | Source | Strategy |
|----------|--------|----------|
| **Loan Application** (1003 URLA) | [Fillable PDF](https://www.worthington.bank) | Downloaded + AcroForm filled via pypdf |
| **W-2 Wage Statement** | [eForms.com](https://eforms.com/irs/w2/) | Downloaded + AcroForm filled via pypdf |
| **Pay Stub** | Synthetic | Generated with reportlab (ADP-style) |
| **Bank Statement** | Synthetic | Generated with reportlab |

## Quick Start

```bash
# Install dependencies
pip install 'llama-cloud>=2.1' anthropic pydantic pypdf reportlab requests

# Set API keys
export LLAMA_CLOUD_API_KEY=llx-...
export ANTHROPIC_API_KEY=sk-ant-...

# Generate sample documents
cd sample_docs && python generate_docs.py && cd ..

# Run the pipeline
python loan_pipeline.py

# View the report
open output/loan_report.html
```

## Files

```
loan_processing/
├── README.md                     # This file
├── tutorial.md                   # Step-by-step walkthrough
├── loan_pipeline.py              # Complete runnable pipeline
├── report_template.html          # HTML report template
├── sample_docs/
│   └── generate_docs.py          # Downloads forms + generates synthetic docs
└── output/
    └── loan_report.html          # Generated report (after running pipeline)
```

## Architecture

```
┌─────────────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐
│ Loan Application│  │   W-2    │  │ Pay Stub │  │ Bank Statement │
│  (1003 URLA)    │  │  (IRS)   │  │  (ADP)   │  │  (transactions)│
└────────┬────────┘  └────┬─────┘  └────┬─────┘  └───────┬────────┘
         │                │              │                │
         └───────── LlamaExtract (agentic tier) ─────────┘
                          │
                   Structured JSON with
                   confidence + citations
                          │
                    Claude (sonnet 4.6)
                   Cross-doc validation
                          │
                   ┌──────┴──────┐
                   │ HTML Report │
                   │  - Income   │
                   │    Summary  │
                   │  - Checks   │
                   │  - Decision │
                   └─────────────┘
```

## What It Checks

1. **Stated Income vs W-2** — Does the application income match employer-reported wages?
2. **Stated Income vs Pay Stub** — Does current pay rate support stated income?
3. **W-2 vs Pay Stub** — Income trend (raises, pay cuts)
4. **Net Pay vs Bank Deposits** — Do actual deposits match expected payroll?
5. **Employer Consistency** — Same employer across all documents (handling abbreviations)

## Scope and Simplifications

This tutorial focuses on **income verification** — the highest-value cross-validation task for loan processors. To keep the tutorial focused:

- The **1003 loan application** is partially filled (borrower info, employment, income, and basic loan/property details). A real application would include full financial disclosures — additional income sources, other assets/investments, liabilities, monthly expenses, and declarations. These are left blank intentionally.
- The pipeline extracts and validates only **employment income** from a single W-2 employer. A production system would handle self-employment (Schedule C/K-1), multiple income sources, and 2-3 years of tax returns.
- **DTI and LTV ratios** are not calculated. In production these would be derived from the verified income combined with liabilities and the property appraisal.

See the [tutorial](tutorial.md) "What's Next" section for how to extend this into a production pipeline.
