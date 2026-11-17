from fastapi import Depends, FastAPI, HTTPException, status

from app.config import Settings, get_settings
from app.schemas import LinkAnalysisRequest, LinkAnalysisResponse
from app.services.analysis_service import AnalysisService
from app.services.llm_service import LLMServiceError
from app.services.website_extractor import WebsiteExtractionError
from app.utils.validators import URLValidationError

app = FastAPI(
    title="AI-Powered Website Link Analysis API",
    description=(
        "Analyzes a website URL using an LLM to generate competitor, search query, "
        "SEO, service, and target audience insights."
    ),
    version="1.0.0",
)

_analysis_service: AnalysisService | None = None


def get_analysis_service(
    settings: Settings = Depends(get_settings),
) -> AnalysisService:
    global _analysis_service
    if _analysis_service is None:
        _analysis_service = AnalysisService(settings)
    return _analysis_service


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}


@app.post("/link-analysis", response_model=LinkAnalysisResponse)
async def link_analysis(
    payload: LinkAnalysisRequest,
    service: AnalysisService = Depends(get_analysis_service),
) -> LinkAnalysisResponse:
    """Fetch, extract, and analyze a public website URL."""
    try:
        return await service.analyze_url(payload.url)
    except URLValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except WebsiteExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except LLMServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
