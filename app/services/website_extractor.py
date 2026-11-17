import re
from dataclasses import dataclass, field
from typing import List

import httpx
from bs4 import BeautifulSoup

from app.utils.validators import URLValidationError, validate_public_url


class WebsiteExtractionError(RuntimeError):
    """Raised when a website cannot be fetched or parsed."""


@dataclass
class ExtractedWebsite:
    """Cleaned, structured website content ready for LLM analysis."""

    url: str
    title: str = ""
    meta_description: str = ""
    meta_keywords: str = ""
    og_site_name: str = ""
    headings: List[str] = field(default_factory=list)
    nav_links: List[str] = field(default_factory=list)
    body_text: str = ""

    def to_prompt_context(self, max_chars: int = 12_000) -> str:
        """Format extracted fields into a compact, token-efficient context block."""
        parts = [
            f"URL: {self.url}",
            f"Site Name: {self.og_site_name or 'N/A'}",
            f"Title: {self.title or 'N/A'}",
            f"Meta Description: {self.meta_description or 'N/A'}",
            f"Meta Keywords: {self.meta_keywords or 'N/A'}",
        ]
        if self.headings:
            parts.append("Key Headings:\n- " + "\n- ".join(self.headings[:25]))
        if self.nav_links:
            parts.append("Navigation / Service Links: " + ", ".join(self.nav_links[:25]))

        header_block = "\n".join(parts)
        remaining = max(500, max_chars - len(header_block) - 30)
        trimmed_body = self.body_text[:remaining]
        return f"{header_block}\n\nMain Content:\n{trimmed_body}"


_NOISE_TAGS = ("script", "style", "noscript", "svg", "iframe", "canvas")


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_html_content(url: str, html: str, max_chars: int = 12_000) -> ExtractedWebsite:
    """Parse HTML and extract metadata, headings, navigation items, and body text."""
    soup = BeautifulSoup(html, "html.parser")

    title = _clean_text(soup.title.get_text()) if soup.title else ""

    def _meta(name: str = "", prop: str = "") -> str:
        tag = (
            soup.find("meta", attrs={"name": re.compile(f"^{name}$", re.I)})
            if name
            else soup.find("meta", attrs={"property": re.compile(f"^{prop}$", re.I)})
        )
        if tag and tag.get("content"):
            return _clean_text(str(tag["content"]))
        return ""

    meta_description = _meta(name="description") or _meta(prop="og:description")
    meta_keywords = _meta(name="keywords")
    og_site_name = _meta(prop="og:site_name")

    headings: List[str] = []
    seen_headings = set()
    for tag in soup.find_all(["h1", "h2", "h3"]):
        txt = _clean_text(tag.get_text())
        if txt and txt.lower() not in seen_headings:
            seen_headings.add(txt.lower())
            headings.append(txt)

    nav_links: List[str] = []
    seen_nav = set()
    for nav in soup.find_all(["nav", "header"]):
        for a in nav.find_all("a"):
            txt = _clean_text(a.get_text())
            if 2 <= len(txt) <= 50 and txt.lower() not in seen_nav:
                seen_nav.add(txt.lower())
                nav_links.append(txt)

    for noise in soup.find_all(_NOISE_TAGS):
        noise.decompose()

    # Deduplicate lines while preserving order to reduce token waste
    raw_lines = [
        _clean_text(line)
        for line in soup.get_text(separator="\n").splitlines()
    ]
    unique_lines: List[str] = []
    seen_lines = set()
    for line in raw_lines:
        if len(line) < 3:
            continue
        key = line.lower()
        if key not in seen_lines:
            seen_lines.add(key)
            unique_lines.append(line)

    body_text = "\n".join(unique_lines)[:max_chars]

    return ExtractedWebsite(
        url=url,
        title=title,
        meta_description=meta_description,
        meta_keywords=meta_keywords,
        og_site_name=og_site_name,
        headings=headings,
        nav_links=nav_links,
        body_text=body_text,
    )


async def fetch_and_extract_website(
    url: str,
    timeout_seconds: int = 15,
    max_html_bytes: int = 2_097_152,
    max_extracted_chars: int = 12_000,
) -> ExtractedWebsite:
    """Fetch a public URL safely and extract structured text content."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; DXoraLinkAnalyzer/1.0; +https://github.com/chivoxai/practical-test)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            # Re-validate final URL after redirects against SSRF
            validate_public_url(str(response.url))
    except URLValidationError:
        raise
    except httpx.TimeoutException as exc:
        raise WebsiteExtractionError(f"Timed out fetching '{url}'.") from exc
    except httpx.HTTPStatusError as exc:
        raise WebsiteExtractionError(
            f"Website returned HTTP {exc.response.status_code} for '{url}'."
        ) from exc
    except httpx.RequestError as exc:
        raise WebsiteExtractionError(f"Failed to connect to '{url}': {exc}") from exc

    content_type = response.headers.get("content-type", "").lower()
    if "html" not in content_type and "text/" not in content_type:
        raise WebsiteExtractionError(
            f"Unsupported content type '{content_type or 'unknown'}' at '{url}'."
        )

    raw_bytes = response.content[:max_html_bytes]
    encoding = response.encoding or "utf-8"
    html = raw_bytes.decode(encoding, errors="replace")

    extracted = parse_html_content(str(response.url), html, max_chars=max_extracted_chars)
    if not extracted.body_text and not extracted.title:
        raise WebsiteExtractionError(
            f"No readable text content could be extracted from '{url}'."
        )
    return extracted
