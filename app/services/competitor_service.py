from typing import Any, Dict, List
from app.schemas import CompetitorAnalysis, CompetitorDetail


def normalize_competitor_analysis(raw: Dict[str, Any]) -> CompetitorAnalysis:
    """Validate and normalize competitor analysis output, marking AI-inferred entries."""
    competitors_raw: List[Dict[str, Any]] = raw.get("competitors") or []
    normalized_competitors: List[CompetitorDetail] = []

    for item in competitors_raw:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        source = item.get("source")
        if source not in ("ai_inferred", "extracted"):
            source = "ai_inferred"
        normalized_competitors.append(
            CompetitorDetail(
                name=str(item["name"]),
                main_service=str(item.get("main_service", "N/A")),
                target_market=str(item.get("target_market", "General")),
                strengths=[str(s) for s in (item.get("strengths") or [])],
                weaknesses_or_gaps=[str(w) for w in (item.get("weaknesses_or_gaps") or [])],
                source=source,
            )
        )

    return CompetitorAnalysis(
        brand_overview=str(raw.get("brand_overview", "")),
        main_products_and_services=[
            str(x) for x in (raw.get("main_products_and_services") or [])
        ],
        competitors=normalized_competitors,
        brand_competitive_advantages=[
            str(x) for x in (raw.get("brand_competitive_advantages") or [])
        ],
        opportunities=[str(x) for x in (raw.get("opportunities") or [])],
    )
