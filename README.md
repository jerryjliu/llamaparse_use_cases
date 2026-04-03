# LlamaParse Use Cases

Real-world tutorials demonstrating [LlamaParse](https://cloud.llamaindex.ai) document processing across industry verticals.

Each use case includes sample documents, a runnable pipeline script, and an interactive HTML report.

## Use Cases

| Use Case | Vertical | What It Shows |
|----------|----------|---------------|
| [**KYC Document Verification**](kyc/) | Fintech | Extract identity fields from IDs, utility bills, and bank statements with [LlamaExtract](https://developers.llamaindex.ai/python/cloud/llamaextract/getting_started/), then cross-validate across documents using Claude |

## Getting Started

Each use case is self-contained in its own directory. See the README in each folder for setup instructions.

You'll need:
- A [LlamaCloud API key](https://cloud.llamaindex.ai) (`LLAMA_CLOUD_API_KEY`)
- An [Anthropic API key](https://console.anthropic.com) (`ANTHROPIC_API_KEY`) for use cases that include LLM-driven reasoning
- Python 3.10+

---

*Built with [LlamaParse](https://cloud.llamaindex.ai) by [LlamaIndex](https://www.llamaindex.ai)*
