import json
import re
from typing import Any, Dict

import httpx

from app.config import Settings


class LLMServiceError(RuntimeError):
    """Raised when the configured LLM provider fails or returns invalid JSON."""


def _strip_markdown_fences(raw_text: str) -> str:
    """Remove optional ```json ... ``` fences from LLM output."""
    text = raw_text.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text


def _parse_json_response(raw_text: str) -> Dict[str, Any]:
    cleaned = _strip_markdown_fences(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMServiceError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMServiceError("LLM response JSON must be an object.")
    return data


class LLMService:
    """Multi-provider async LLM client supporting Gemini, OpenAI, and Anthropic."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = settings.llm_provider.strip().lower()
        self.model = settings.llm_model.strip()

    async def generate_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Call the configured LLM provider and return parsed JSON."""
        if self.provider == "gemini":
            return await self._call_gemini(system_prompt, user_prompt)
        if self.provider == "openai":
            return await self._call_openai(system_prompt, user_prompt)
        if self.provider == "anthropic":
            return await self._call_anthropic(system_prompt, user_prompt)
        if self.provider == "groq":
            return await self._call_groq(system_prompt, user_prompt)
        raise LLMServiceError(
            f"Unsupported LLM_PROVIDER '{self.provider}'. Use gemini, openai, anthropic, or groq."
        )

    async def _call_gemini(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        api_key = self.settings.gemini_api_key.strip()
        if not api_key:
            raise LLMServiceError("GEMINI_API_KEY is not configured.")

        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(endpoint, params={"key": api_key}, json=payload)

        if resp.status_code >= 400:
            raise LLMServiceError(f"Gemini API error ({resp.status_code}): {resp.text[:300]}")

        body = resp.json()
        try:
            text = body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMServiceError(f"Unexpected Gemini response structure: {body}") from exc
        return _parse_json_response(text)

    async def _call_openai(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        api_key = self.settings.openai_api_key.strip()
        if not api_key:
            raise LLMServiceError("OPENAI_API_KEY is not configured.")

        payload = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )

        if resp.status_code >= 400:
            raise LLMServiceError(f"OpenAI API error ({resp.status_code}): {resp.text[:300]}")

        body = resp.json()
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMServiceError(f"Unexpected OpenAI response structure: {body}") from exc
        return _parse_json_response(text)

    async def _call_anthropic(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        api_key = self.settings.anthropic_api_key.strip()
        if not api_key:
            raise LLMServiceError("ANTHROPIC_API_KEY is not configured.")

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": 0.2,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )

        if resp.status_code >= 400:
            raise LLMServiceError(f"Anthropic API error ({resp.status_code}): {resp.text[:300]}")

        body = resp.json()
        try:
            text = body["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMServiceError(f"Unexpected Anthropic response structure: {body}") from exc
        return _parse_json_response(text)

    async def _call_groq(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        api_key = self.settings.groq_api_key.strip()
        if not api_key:
            raise LLMServiceError("GROQ_API_KEY is not configured.")

        payload = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
            )

        if resp.status_code >= 400:
            raise LLMServiceError(f"Groq API error ({resp.status_code}): {resp.text[:300]}")

        body = resp.json()
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMServiceError(f"Unexpected Groq response structure: {body}") from exc
        return _parse_json_response(text)
