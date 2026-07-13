"""Notary Custodian AI route with Ollama-first BYOK provider support."""
from __future__ import annotations

import os
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..dependencies import auth_context
from ..schemas import PGLRequestContext

router = APIRouter(prefix="/notary", tags=["notary"])

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_OPENAI_COMPATIBLE_DEFAULT_BASE = "https://api.openai.com/v1"
_SYSTEM_PROMPT = (
    "You are the Notary Custodian AI of Project Genome Ledger — a compliance and audit "
    "intelligence assistant. You specialise in AI governance frameworks (EU AI Act, NIST AI RMF, "
    "ISO 42001), cryptographic ledger integrity, agent lifecycle auditing, and regulatory risk "
    "assessment. Provide precise, technically rigorous answers. When assessing an agent, refer "
    "to its provided parameters. Format responses in clear Markdown."
)


class NotaryChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    agent_id: Optional[str] = Field(None, description="Optional agent UUID for context injection")
    provider: Literal["ollama", "openai_compatible", "gemini"] = Field("ollama")
    model: str | None = Field(None, max_length=128)
    provider_api_key: str | None = Field(None, max_length=4096, repr=False)
    provider_base_url: str | None = Field(None, max_length=512)


class NotaryChatResponse(BaseModel):
    reply: str
    provider: str
    model_used: str
    input_tokens: int
    output_tokens: int


def _with_agent_context(body: NotaryChatRequest) -> str:
    if body.agent_id:
        return f"[Agent context: {body.agent_id}]\n\n{body.message}"
    return body.message


def _clean_base_url(value: str) -> str:
    return value.rstrip("/")


async def _call_ollama(body: NotaryChatRequest) -> NotaryChatResponse:
    base_url = _clean_base_url(
        body.provider_base_url
        or os.environ.get("OLLAMA_BASE_URL")
        or "http://ollama:11434"
    )
    model = body.model or os.environ.get("OLLAMA_MODEL") or "llama3.1"
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _with_agent_context(body)},
        ],
        "options": {"temperature": 0.4},
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{base_url}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
    reply = data.get("message", {}).get("content")
    if not isinstance(reply, str):
        raise ValueError("Unexpected Ollama response shape")
    return NotaryChatResponse(
        reply=reply,
        provider="ollama",
        model_used=model,
        input_tokens=int(data.get("prompt_eval_count") or 0),
        output_tokens=int(data.get("eval_count") or 0),
    )


async def _call_openai_compatible(body: NotaryChatRequest) -> NotaryChatResponse:
    api_key = body.provider_api_key or os.environ.get("OPENAI_COMPATIBLE_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing provider_api_key for openai_compatible provider.",
        )
    base_url = _clean_base_url(
        body.provider_base_url
        or os.environ.get("OPENAI_COMPATIBLE_BASE_URL")
        or _OPENAI_COMPATIBLE_DEFAULT_BASE
    )
    model = body.model or os.environ.get("OPENAI_COMPATIBLE_MODEL") or "gpt-4o-mini"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _with_agent_context(body)},
        ],
        "temperature": 0.4,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    reply = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return NotaryChatResponse(
        reply=reply,
        provider="openai_compatible",
        model_used=model,
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
    )


async def _call_gemini(body: NotaryChatRequest) -> NotaryChatResponse:
    api_key = body.provider_api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing provider_api_key for gemini provider.",
        )
    model = body.model or os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"
    payload = {
        "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": _with_agent_context(body)}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2048},
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{_GEMINI_BASE}/models/{model}:generateContent?key={api_key}", json=payload)
        resp.raise_for_status()
        data = resp.json()
    reply = data["candidates"][0]["content"]["parts"][0]["text"]
    usage = data.get("usageMetadata", {})
    return NotaryChatResponse(
        reply=reply,
        provider="gemini",
        model_used=model,
        input_tokens=int(usage.get("promptTokenCount") or 0),
        output_tokens=int(usage.get("candidatesTokenCount") or 0),
    )


@router.post("/chat", response_model=NotaryChatResponse)
async def notary_chat(
    body: NotaryChatRequest,
    ctx: PGLRequestContext = Depends(auth_context),
) -> NotaryChatResponse:
    """Send a message to the Notary Custodian AI through Ollama or BYOK providers."""
    _ = ctx
    try:
        if body.provider == "ollama":
            return await _call_ollama(body)
        if body.provider == "openai_compatible":
            return await _call_openai_compatible(body)
        if body.provider == "gemini":
            return await _call_gemini(body)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{body.provider} provider error: {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{body.provider} provider network error: {exc}",
        ) from exc
    except (KeyError, IndexError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unexpected {body.provider} response shape: {exc}",
        ) from exc

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported notary provider")
