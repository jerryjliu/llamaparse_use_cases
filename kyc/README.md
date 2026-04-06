# KYC Document Verification

Extract identity data from government IDs, utility bills, and bank statements — then cross-validate across documents with Claude to automate customer verification.

**[Read the full tutorial](tutorial.md)** for a step-by-step walkthrough with code snippets.

## Quick Start

```bash
pip install 'llama-cloud>=2.1' anthropic pydantic reportlab requests Pillow
export LLAMA_CLOUD_API_KEY=llx-...    # from cloud.llamaindex.ai
export ANTHROPIC_API_KEY=sk-ant-...   # from console.anthropic.com

python sample_docs/generate_docs.py   # generate sample documents
python kyc_pipeline.py                # run extraction + validation
open output/kyc_report.html           # view the report
```

## What It Does

1. **Extract** identity fields from 3 documents using [LlamaExtract](https://developers.llamaindex.ai/python/cloud/llamaextract/getting_started/sdk/) (agentic tier with confidence scores + citations)
2. **Cross-validate** names and addresses with Claude structured outputs
3. **Generate** an HTML report with confidence color-coding, embedded PDFs, and a KYC decision

## Files

```
kyc/
├── tutorial.md              # Step-by-step walkthrough ← start here
├── kyc_pipeline.py          # Complete runnable pipeline
├── report_template.html     # HTML report template
├── sample_docs/
│   └── generate_docs.py     # Downloads real specimens + generates synthetic bill
└── output/
    └── kyc_report.html      # Generated report
```
