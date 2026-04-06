# Loan Income Verification

Extract income data from loan applications, W-2s, pay stubs, and bank statements — then cross-validate with Claude before underwriting.

**[Read the full tutorial](tutorial.md)** for a step-by-step walkthrough with code snippets.

## Quick Start

```bash
pip install 'llama-cloud>=2.1' anthropic pydantic pypdf reportlab requests
export LLAMA_CLOUD_API_KEY=llx-...    # from cloud.llamaindex.ai
export ANTHROPIC_API_KEY=sk-ant-...   # from console.anthropic.com

python sample_docs/generate_docs.py   # generate sample documents
python loan_pipeline.py               # run extraction + validation
open output/loan_report.html          # view the report
```

## What It Does

A loan processor receives documents from a borrower and must verify income consistency before submitting to underwriting. This pipeline automates that:

1. **Extract** structured data from 4 documents using [LlamaExtract](https://developers.llamaindex.ai/python/cloud/llamaextract/getting_started/sdk/) (agentic tier with confidence scores + citations)
2. **Cross-validate** income with Claude structured outputs (5 checks across the income consistency triangle)
3. **Generate** an HTML report with income metrics, validation results, and a processor recommendation

## Files

```
loan_processing/
├── tutorial.md              # Step-by-step walkthrough ← start here
├── loan_pipeline.py         # Complete runnable pipeline
├── report_template.html     # HTML report template
├── sample_docs/
│   └── generate_docs.py     # Downloads forms + generates synthetic docs
└── output/
    └── loan_report.html     # Generated report
```

## Scope and Simplifications

This tutorial focuses on **income verification** — the highest-value cross-validation task for loan processors. To keep the tutorial focused:

- The **1003 loan application** is partially filled (borrower info, employment, income, and basic loan/property details). A real application would include full financial disclosures — additional income sources, other assets/investments, liabilities, monthly expenses, and declarations. These are left blank intentionally.
- The pipeline extracts and validates only **employment income** from a single W-2 employer. A production system would handle self-employment (Schedule C/K-1), multiple income sources, and 2-3 years of tax returns.
- **DTI and LTV ratios** are not calculated. In production these would be derived from the verified income combined with liabilities and the property appraisal.

See the [tutorial](tutorial.md) "What's Next" section for how to extend this into a production pipeline.
