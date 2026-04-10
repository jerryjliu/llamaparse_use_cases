# Auto Claims Coverage Verification

Extract claim data from ACORD forms, policy declarations, accident reports, and repair estimates — then cross-validate coverage and flag discrepancies with Claude.

**[Read the full tutorial](tutorial.md)** for a step-by-step walkthrough with code snippets.

## Quick Start

```bash
pip install 'llama-cloud>=2.1' anthropic pydantic pypdf reportlab requests
export LLAMA_CLOUD_API_KEY=llx-...    # from cloud.llamaindex.ai
export ANTHROPIC_API_KEY=sk-ant-...   # from console.anthropic.com

python sample_docs/generate_docs.py   # generate sample documents
python claims_pipeline.py             # run extraction + verification
open output/claims_report.html        # view the report
```

## What It Does

1. **Extract** structured data from 4 insurance documents using [LlamaExtract](https://developers.llamaindex.ai/python/cloud/llamaextract/getting_started/sdk/) (agentic tier with confidence scores + citations)
2. **Cross-validate** identity, coverage, dates, vehicle info, accident descriptions, and repair line items with Claude structured outputs
3. **Generate** an HTML report with coverage assessment, confidence color-coding, embedded PDFs, and an APPROVE/REVIEW/DENY decision

## Files

```
insurance_claims/
├── tutorial.md              # Step-by-step walkthrough ← start here
├── claims_pipeline.py       # Complete runnable pipeline
├── report_template.html     # HTML report template
├── sample_docs/
│   └── generate_docs.py     # Downloads forms + generates synthetic dec page
└── output/
    └── claims_report.html   # Generated report
```

## Architecture

```
  ACORD 2          Policy Dec Page      Accident Report     Repair Estimate
  (AcroForm)       (Synthetic)          (AcroForm)          (AcroForm)
      │                 │                    │                    │
      └────────┬────────┴────────┬───────────┴────────┬──────────┘
               │                 │                    │
         LlamaExtract      LlamaExtract         LlamaExtract
         (agentic tier)    (agentic tier)       (agentic tier)
               │                 │                    │
               └────────┬────────┴────────────────────┘
                        │
                  Claude (sonnet 4.6)
                  Cross-Document Verification
                        │
                  HTML Report
                  (APPROVE / REVIEW / DENY)
```
