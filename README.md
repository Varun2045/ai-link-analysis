# AI-Powered Website Link Analysis API

A FastAPI service that fetches a public website, extracts and cleans its content, and uses an LLM to return structured business, competitor, search query, SEO, service, and target audience insights.

## Features

- **`POST /link-analysis`**: Analyzes any public `http`/`https` website URL and returns 5 structured JSON sections.
- **SSRF Protection**: Rejects `localhost`, `.local`/`.internal` hostnames, and private/loopback/reserved IP addresses before and after redirects.
- **Token-Efficient Extraction**: Strips `<script>`, `<style>`, `<svg>`, and duplicate lines; prioritizes metadata, headings, and navigation links.
- **Multi-Provider LLM Support**: Supports **Google Gemini**, **OpenAI**, and **Anthropic** via `LLM_PROVIDER`.
- **In-Memory TTL Caching**: Avoids duplicate LLM calls for repeated URL requests.

## Setup & Running Locally

```bash
cd ai-link-analysis
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY (or OPENAI_API_KEY / ANTHROPIC_API_KEY)

uvicorn app.main:app --host 0.0.0.0 --port 4000
```

Interactive Swagger docs: `http://localhost:4000/docs`

### Run Tests

```bash
pytest -v
```

## Sample Request & Response

**Request:**
```bash
curl -X POST http://localhost:4000/link-analysis \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

**Response (abbreviated):**
```json
{
  "success": true,
  "website": "https://example.com",
  "cached": false,
  "llm_provider": "gemini",
  "llm_model": "gemini-2.5-flash",
  "brand": {
    "name": "Example Domain",
    "category": "Documentation / Placeholder",
    "summary": "Illustrative domain used in documentation examples."
  },
  "analysis": {
    "competitor_analysis": { "...": "..." },
    "target_search_queries": [ "..." ],
    "seo_improvements": { "..." },
    "top_services": [ "..." ],
    "target_audience": { "..." }
  }
}
```

---

## LLM Platform Research & Cost Optimization

### A. LLM Platform Comparison

*(Note: Pricing and context windows reflect published standard API tiers; response speed and extraction quality for this workload are engineering estimates pending live production benchmarking.)*

| Criteria | Google Gemini | OpenAI | Anthropic |
|---|---|---|---|
| **Model Name** | `gemini-2.5-flash` | `gpt-4o-mini` | `claude-3-5-haiku` |
| **API Cost (per 1M tokens)** | ~$0.15 input / ~$0.60 output (non-thinking) | $0.15 input / $0.60 output | $0.80 input / $4.00 output |
| **Context Window** | 1,000,000 tokens | 128,000 tokens | 200,000 tokens |
| **JSON Support** | Native (`responseMimeType: application/json`) | Native (`response_format: json_object`) | Prompt-guided / tool-use JSON |
| **Response Speed (Est.)** | ~1.5–3.0s for ~1.5k output tokens | ~2.0–4.0s for ~1.5k output tokens | ~2.0–4.0s for ~1.5k output tokens |
| **Accuracy (Est.)** | High for structured extraction & synthesis | High for structured extraction | Very high prose quality, higher cost |
| **Suitability** | **Best overall balance** | Strong alternative | Best when prose nuance > cost |

### B. Cost Optimization Strategies Implemented

1. **HTML Noise Removal & Deduplication**: Stripping scripts, styles, SVGs, and duplicate boilerplate lines reduces raw HTML (often 100KB+) down to ~2,000–3,000 tokens.
2. **Character Budget Cap (`MAX_EXTRACTED_CHARS=12000`)**: Caps input context at ~3,000 tokens while prioritizing high-signal `<title>`, `<meta>`, headings (`h1`–`h3`), and `<nav>` links.
3. **Single-Pass Structured Prompt**: Generates all 5 sections in a single JSON call instead of 5 separate LLM round-trips.
4. **TTL Response Caching (`CACHE_TTL_SECONDS=3600`)**: Serves repeat requests for the same URL from memory at zero token cost.
5. **Model Tiering**: Uses fast, low-cost Flash/Mini models rather than frontier reasoning models.

### C. Final LLM Recommendation

- **Recommended Provider & Model**: **Google Gemini (`gemini-2.5-flash`)**
- **Estimated Input Tokens / Analysis**: ~2,500–3,500 tokens (cleaned page + system schema)
- **Estimated Output Tokens / Analysis**: ~1,000–1,500 tokens (5 structured sections)
- **Estimated API Cost / Analysis**: **~$0.0011 – $0.0015 per uncached website**
- **Expected Response Time (Estimated)**: ~2–3 seconds (excluding target website fetch)
- **Fallback Model**: **OpenAI `gpt-4o-mini`** (identical $0.15/$0.60 per 1M token tier with native JSON mode; switchable via `LLM_PROVIDER=openai`).
