from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app, get_analysis_service
from app.services.analysis_service import AnalysisService
from app.services.website_extractor import ExtractedWebsite, parse_html_content
from app.utils.validators import URLValidationError, validate_public_url


def test_validate_public_url_rejects_ssrf_targets():
    for bad_url in [
        "",
        "ftp://example.com",
        "http://localhost:8000",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/internal",
        "http://192.168.1.10",
    ]:
        try:
            validate_public_url(bad_url)
            assert False, f"Expected URLValidationError for {bad_url}"
        except URLValidationError:
            pass


def test_parse_html_content_strips_noise_and_deduplicates():
    html = """
    <html>
      <head>
        <title>Acme Cloud - DevOps Platform</title>
        <meta name="description" content="Managed Kubernetes and CI/CD for startups." />
        <script>console.log("ignore me");</script>
        <style>.hidden { display: none; }</style>
      </head>
      <body>
        <nav><a href="/pricing">Pricing</a><a href="/docs">Docs</a></nav>
        <h1>Deploy Faster with Acme Cloud</h1>
        <p>Managed Kubernetes and CI/CD for startups.</p>
        <p>Managed Kubernetes and CI/CD for startups.</p>
      </body>
    </html>
    """
    extracted = parse_html_content("https://acme.example.com", html)
    assert extracted.title == "Acme Cloud - DevOps Platform"
    assert "Managed Kubernetes" in extracted.meta_description
    assert "Deploy Faster with Acme Cloud" in extracted.headings
    assert "ignore me" not in extracted.body_text
    assert extracted.body_text.count("Managed Kubernetes and CI/CD for startups.") == 1


def test_link_analysis_endpoint_success_and_cache():
    mock_llm_payload = {
        "brand": {
            "name": "Acme Cloud",
            "category": "Cloud Infrastructure",
            "summary": "Managed Kubernetes and CI/CD platform for startups.",
        },
        "competitor_analysis": {
            "brand_overview": "Provides developer-friendly cloud deployment.",
            "main_products_and_services": ["Managed Kubernetes", "CI/CD Pipelines"],
            "competitors": [
                {
                    "name": "Render",
                    "main_service": "Cloud Hosting",
                    "target_market": "Startups",
                    "strengths": ["Simple DX"],
                    "weaknesses_or_gaps": ["Limited enterprise controls"],
                    "source": "ai_inferred",
                },
                {
                    "name": "Fly.io",
                    "main_service": "Edge Compute",
                    "target_market": "Developers",
                    "strengths": ["Global edge"],
                    "weaknesses_or_gaps": ["Steeper networking learning curve"],
                    "source": "ai_inferred",
                },
                {
                    "name": "Railway",
                    "main_service": "App Deployment",
                    "target_market": "Small Teams",
                    "strengths": ["Fast onboarding"],
                    "weaknesses_or_gaps": ["Less custom K8s control"],
                    "source": "ai_inferred",
                },
            ],
            "brand_competitive_advantages": ["Turnkey Kubernetes"],
            "opportunities": ["Publish migration guides"],
        },
        "target_search_queries": [
            {
                "query": "managed kubernetes for startups",
                "platforms": ["Google Search", "LinkedIn"],
                "intent": "Service Discovery",
                "business_relevance": "Matches core offering",
                "target_audience": "Startup CTOs",
            }
        ],
        "seo_improvements": {
            "primary_keyword": "managed kubernetes for startups",
            "secondary_keywords": ["ci cd platform", "cloud deployment"],
            "long_tail_keywords": ["best managed kubernetes platform for small teams"],
            "business_keywords": ["devops automation"],
            "recommended_title": "Acme Cloud | Managed Kubernetes & CI/CD for Startups",
            "title_rationale": "Front-loads primary keyword and value proposition.",
            "meta_description": "Deploy faster with Acme Cloud's managed Kubernetes and CI/CD.",
            "supporting_content": [
                {
                    "content_type": "FAQ",
                    "topic": "Kubernetes vs PaaS Cost Comparison",
                    "purpose": "Capture bottom-of-funnel searchers",
                }
            ],
        },
        "top_services": [
            {
                "service_name": "Managed Kubernetes",
                "description": "Zero-ops Kubernetes clusters.",
                "target_industry": "SaaS",
                "target_customer": "Engineering Teams",
                "main_benefit": "Reduces DevOps overhead",
                "is_inferred": False,
            }
        ],
        "target_audience": {
            "primary_audience": ["Startup Engineering Teams"],
            "secondary_audience": ["Digital Agencies"],
            "industries": ["SaaS", "FinTech"],
            "business_types": ["Startups", "SMBs"],
            "customer_profiles": ["CTO", "Lead DevOps Engineer"],
            "geographical_focus": None,
            "customer_needs": ["Fast deployments"],
            "customer_interests": ["Cloud automation"],
            "marketing_segments": ["Seed-to-Series B SaaS"],
        },
    }

    settings = Settings(llm_provider="gemini", llm_model="gemini-2.5-flash", gemini_api_key="test")
    mock_llm = AsyncMock()
    mock_llm.provider = "gemini"
    mock_llm.model = "gemini-2.5-flash"
    mock_llm.generate_json = AsyncMock(return_value=mock_llm_payload)

    service = AnalysisService(settings=settings, llm_service=mock_llm)
    app.dependency_overrides[get_analysis_service] = lambda: service

    extracted = ExtractedWebsite(
        url="https://acme.example.com",
        title="Acme Cloud",
        body_text="Managed Kubernetes and CI/CD for startups.",
    )

    try:
        with patch("app.services.analysis_service.validate_public_url", return_value="https://acme.example.com"), \
             patch("app.services.analysis_service.fetch_and_extract_website", AsyncMock(return_value=extracted)):
            client = TestClient(app)

            resp1 = client.post("/link-analysis", json={"url": "https://acme.example.com"})
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert data1["success"] is True
            assert data1["cached"] is False
            assert data1["brand"]["name"] == "Acme Cloud"
            assert len(data1["analysis"]["competitor_analysis"]["competitors"]) == 3

            # Second request should hit TTL cache without calling LLM again
            resp2 = client.post("/link-analysis", json={"url": "https://acme.example.com"})
            assert resp2.status_code == 200
            assert resp2.json()["cached"] is True
            assert mock_llm.generate_json.await_count == 1
    finally:
        app.dependency_overrides.clear()


def test_link_analysis_rejects_private_ip():
    client = TestClient(app)
    resp = client.post("/link-analysis", json={"url": "http://127.0.0.1:8080"})
    assert resp.status_code == 422
