from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class LinkAnalysisRequest(BaseModel):
    """Request payload for website link analysis."""

    url: str = Field(..., description="Public HTTP/HTTPS website URL to analyze.")


class BrandInfo(BaseModel):
    """High-level brand summary extracted from the website."""

    name: str
    category: str
    summary: str


class CompetitorDetail(BaseModel):
    """Competitor profile and comparison against the submitted brand."""

    name: str
    main_service: str
    target_market: str
    strengths: List[str] = Field(default_factory=list)
    weaknesses_or_gaps: List[str] = Field(default_factory=list)
    source: Literal["ai_inferred", "extracted"] = Field(
        default="ai_inferred",
        description="Indicates whether competitor info was extracted or AI-suggested.",
    )


class CompetitorAnalysis(BaseModel):
    """Section 1: Competitor vs Your Brand Details."""

    brand_overview: str
    main_products_and_services: List[str] = Field(default_factory=list)
    competitors: List[CompetitorDetail] = Field(default_factory=list)
    brand_competitive_advantages: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)


class SearchQueryItem(BaseModel):
    """Section 2 item: Target search query with platform and intent."""

    query: str
    platforms: List[
        Literal["Google Search", "Facebook", "Instagram", "LinkedIn", "X"]
    ]
    intent: str
    business_relevance: str
    target_audience: str


class SupportingContentIdea(BaseModel):
    """Supporting content recommendation for SEO visibility."""

    content_type: str
    topic: str
    purpose: str


class SEOImprovements(BaseModel):
    """Section 3: SEO Improvement recommendations."""

    primary_keyword: str
    secondary_keywords: List[str] = Field(default_factory=list)
    long_tail_keywords: List[str] = Field(default_factory=list)
    business_keywords: List[str] = Field(default_factory=list)
    recommended_title: str
    title_rationale: str
    meta_description: str
    supporting_content: List[SupportingContentIdea] = Field(default_factory=list)


class ServiceItem(BaseModel):
    """Section 4 item: Identified or inferred service offering."""

    service_name: str
    description: str
    target_industry: str
    target_customer: str
    main_benefit: str
    is_inferred: bool = Field(
        default=False,
        description="True if inferred from context rather than explicitly listed on the site.",
    )


class TargetAudience(BaseModel):
    """Section 5: Target Audience Identification."""

    primary_audience: List[str] = Field(default_factory=list)
    secondary_audience: List[str] = Field(default_factory=list)
    industries: List[str] = Field(default_factory=list)
    business_types: List[str] = Field(default_factory=list)
    customer_profiles: List[str] = Field(default_factory=list)
    geographical_focus: Optional[str] = None
    customer_needs: List[str] = Field(default_factory=list)
    customer_interests: List[str] = Field(default_factory=list)
    marketing_segments: List[str] = Field(default_factory=list)


class AnalysisPayload(BaseModel):
    """All five required analysis sections."""

    competitor_analysis: CompetitorAnalysis
    target_search_queries: List[SearchQueryItem] = Field(default_factory=list)
    seo_improvements: SEOImprovements
    top_services: List[ServiceItem] = Field(default_factory=list)
    target_audience: TargetAudience


class LinkAnalysisResponse(BaseModel):
    """Top-level API response for POST /link-analysis."""

    success: bool = True
    website: str
    cached: bool = False
    llm_provider: str
    llm_model: str
    brand: BrandInfo
    analysis: AnalysisPayload
