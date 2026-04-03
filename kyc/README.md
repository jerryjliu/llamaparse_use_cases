# KYC Document Verification with LlamaParse

Extract identity data from government IDs, utility bills, and bank statements — then use Claude to cross-validate across documents and automate customer verification.

## Overview

A 2-step KYC (Know Your Customer) pipeline:

1. **Identification**: Extract name, DOB, address, and ID number from a driver's license using [LlamaExtract](https://developers.llamaindex.ai/python/cloud/llamaextract/getting_started/sdk/)
2. **Due Diligence**: Extract fields from a utility bill and bank statement, then cross-validate names and addresses using Claude with [structured outputs](https://docs.anthropic.com/en/docs/build-with-claude/structured-outputs)

The pipeline generates an interactive HTML report with per-field confidence scores, source citations, embedded PDF viewers, and LLM-generated reasoning for each validation check.

## Sample Documents

| Document | Source | Identity | OCR Challenge |
|----------|--------|----------|---------------|
| **Driver's License** | PA DMV official specimen | ANDREW JASON SAMPLE | Photo, watermark, barcode, multi-field layout |
| **Utility Bill** | Synthetic (reportlab) | ANDREW J. SAMPLE | Multi-column boxes, nested charge tiers, bar chart, footnotes |
| **Bank Statement** | Impact Bank real sample | JAMES C. MORRISON | **Image-based PDF** (no text layer), multiple table schemas |

The utility bill matches the ID (with a name abbreviation). The bank statement uses a different person — the cross-validation catches this mismatch.

## Quick Start

```bash
# Install dependencies
pip install 'llama-cloud>=2.1' anthropic pydantic reportlab requests Pillow

# Set API keys
export LLAMA_CLOUD_API_KEY=llx-...
export ANTHROPIC_API_KEY=sk-ant-...

# Generate sample documents
cd sample_docs/
python generate_docs.py
cd ..

# Run the pipeline
python kyc_pipeline.py

# View the report
open output/kyc_report.html
```

## Files

```
kyc/
├── README.md                # This file
├── tutorial.md              # Detailed walkthrough with code snippets
├── kyc_pipeline.py          # Complete runnable pipeline
├── report_template.html     # HTML report template (string.Template)
├── sample_docs/
│   └── generate_docs.py     # Downloads real specimens + generates synthetic bill
└── output/
    └── kyc_report.html      # Generated report (after running pipeline)
```

## Tutorial

See [tutorial.md](tutorial.md) for a step-by-step walkthrough covering:
- Defining Pydantic extraction schemas
- Using the LlamaExtract v2 API with confidence scores and citations
- LLM-driven cross-document validation with Claude structured outputs
- Generating an interactive HTML report

## How It Works

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Driver's    │     │ Utility     │     │ Bank        │
│ License     │     │ Bill        │     │ Statement   │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────┬───────┴───────────────────┘
                   │
          ┌────────▼────────┐
          │  LlamaExtract   │  Structured extraction with
          │  (agentic tier) │  confidence scores + citations
          └────────┬────────┘
                   │
          ┌────────▼────────┐
          │  Claude Sonnet  │  Cross-document name/address
          │  (structured    │  validation with reasoning
          │   outputs)      │
          └────────┬────────┘
                   │
          ┌────────▼────────┐
          │  HTML Report    │  Confidence color-coding,
          │                 │  embedded PDFs, KYC decision
          └─────────────────┘
```

---

*Built with [LlamaParse](https://cloud.llamaindex.ai) and [Claude](https://www.anthropic.com) by [LlamaIndex](https://www.llamaindex.ai)*
