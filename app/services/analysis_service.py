import time
from typing import Any, Dict, Tuple

from pydantic import ValidationError

from app.config import Settings
from app.schemas import (
    AnalysisPayload,
    BrandInfo,
    LinkAnalysisResponse,
    SEOImprovements,
    ServiceItem,
    SearchQueryItem,
    TargetAudience,
)
from app.services.competitor_service import normalize_competitor_analysis
from app.services.llm_service import LLMService, LLMServiceError
from app.services.website_extractor import ExtractedWebsite, fetch_and_extract_website
from app.utils.validators import validate_public_url

_SYSTEM_PROMPT = """You are a senior digital strategy, SEO, and market intelligence analyst.
Analyze the provided website content and return a single valid JSON object matching the exact schema below.

Rules:
1. Base all brand, service, and audience insights strictly on the provided website content.
2. Never invent search volumes, traffic numbers, or ranking metrics.
3. For competitors, provide at least 3 relevant competitors and set "source" to "ai_inferred" unless explicitly named on the website ("extracted").
4. For top_services, identify up to 5 services from the website content; set "is_inferred": true for any service inferred rather than explicitly listed.
5. For target_search_queries, provide exactly 5 queries covering platforms from: "Google Search", "Facebook", "Instagram", "LinkedIn", "X".
6. Return ONLY raw JSON with no markdown or extra commentary.

Required JSON schema:
{
  "brand": {
    "name": "string",
    "category": "string",
    "summary": "string"
  },
  "competitor_analysis": {
    "brand_overview": "string",
    "main_products_and_services": ["string"],
    "competitors": [
      {
        "name": "string",
        "main_service": "string",
        "target_market": "string",
        "strengths": ["string"],
        "weaknesses_or_gaps": ["string"],
        "source": "ai_inferred"
      }
    ],
    "brand_competitive_advantages": ["string"],
    "opportunities": ["string"]
  },
  "target_search_queries": [
    {
      "query": "string",
      "platforms": ["Google Search"],
      "intent": "string",
      "business_relevance": "string",
      "target_audience": "string"
    }
  ],
  "seo_improvements": {
    "primary_keyword": "string",
    "secondary_keywords": ["string"],
    "long_tail_keywords": ["string"],
    "business_keywords": ["string"],
    "recommended_title": "string",
    "title_rationale": "string",
    "meta_description": "string",
    "supporting_content": [
      {
        "content_type": "string",
        "topic": "string",
        "purpose": "string"
      }
    ]
  },
  "top_services": [
    {
      "service_name": "string",
      "description": "string",
      "target_industry": "string",
      "target_customer": "string",
      "main_benefit": "string",
      "is_inferred": false
    }
  ],
  "target_audience": {
    "primary_audience": ["string"],
    "secondary_audience": ["string"],
    "industries": ["string"],
    "business_types": ["string"],
    "customer_profiles": ["string"],
    "geographical_focus": "string or null",
    "customer_needs": ["string"],
    "customer_interests": ["string"],
    "marketing_segments": ["string"]
  }
}"""


class AnalysisService:
    """Orchestrates URL validation, extraction, LLM analysis, and TTL caching."""

    def __init__(self, settings: Settings, llm_service: LLMService | None = None) -> None:
        self.settings = settings
        self.llm_service = llm_service or LLMService(settings)
        self._cache: Dict[str, Tuple[float, LinkAnalysisResponse]] = {}

    def _get_cached(self, url: str) -> LinkAnalysisResponse | None:
        entry = self._cache.get(url)
        if not entry:
            return None
        expires_at, response = entry
        if time.monotonic() > expires_at:
            self._cache.pop(url, None)
            return None
        return response.model_copy(update={"cached": True})

    def _set_cached(self, url: str, response: LinkAnalysisResponse) -> None:
        if self.settings.cache_ttl_seconds > 0:
            self._cache[url] = (
                time.monotonic() + self.settings.cache_ttl_seconds,
                response,
            )

    async def analyze_url(self, raw_url: str) -> LinkAnalysisResponse:
        """Validate, fetch, and analyze a website URL."""
        validated_url = validate_public_url(raw_url)
        cache_key = validated_url.rstrip("/").lower()

        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        extracted: ExtractedWebsite = await fetch_and_extract_website(
            validated_url,
            timeout_seconds=self.settings.request_timeout_seconds,
            max_html_bytes=self.settings.max_html_bytes,
            max_extracted_chars=self.settings.max_extracted_chars,
        )

        user_prompt = (
            "Analyze the following extracted website content and produce the JSON report:\n\n"
            + extracted.to_prompt_context(self.settings.max_extracted_chars)
        )
        raw_result: Dict[str, Any] = await self.llm_service.generate_json(
            _SYSTEM_PROMPT, user_prompt
        )

        try:
            brand = BrandInfo(**(raw_result.get("brand") or {}))
            competitor_analysis = normalize_competitor_analysis(
                raw_result.get("competitor_analysis") or {}
            )
            queries = [
                SearchQueryItem(**item)
                for item in (raw_result.get("target_search_queries") or [])[:5]
            ]
            seo = SEOImprovements(**(raw_result.get("seo_improvements") or {}))
            services = [
                ServiceItem(**item)
                for item in (raw_result.get("top_services") or [])[:5]
            ]
            audience = TargetAudience(**(raw_result.get("target_audience") or {}))

            response = LinkAnalysisResponse(
                success=True,
                website=extracted.url,
                cached=False,
                llm_provider=self.llm_service.provider,
                llm_model=self.llm_service.model,
                brand=brand,
                analysis=AnalysisPayload(
                    competitor_analysis=competitor_analysis,
                    target_search_queries=queries,
                    seo_improvements=seo,
                    top_services=services,
                    target_audience=audience,
                ),
            )
        except (ValidationError, TypeError) as exc:
            raise LLMServiceError(
                f"LLM output did not match expected schema: {exc}"
            ) from exc

        self._set_cached(cache_key, response)
        return response
