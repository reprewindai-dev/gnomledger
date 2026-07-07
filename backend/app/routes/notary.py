"""Notary Custodian AI route — proxies Gemini calls server-side.

The Gemini API key is never exposed to the frontend. All requests are
authenticated via gnomledger's standard API key bootstrap pattern.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..dependencies import get_current_account
from ..models import Account

router = APIRouter(prefix="/notary", tags=["notary"])

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
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
    model: str = Field("gemini-2.5-flash", description="Gemini model identifier")


class NotaryChatResponse(BaseModel):
    reply: str
    model_used: str
    input_tokens: int
    output_tokens: int


_ALLOWED_MODELS = {"gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"}


@router.post("/chat", response_model=NotaryChatResponse)
async def notary_chat(
    body: NotaryChatRequest,
    account: Account = Depends(get_current_account),
) -> NotaryChatResponse:
    """Send a message to the Notary Custodian AI (Gemini, server-side)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notary AI is not configured on this deployment (missing GEMINI_API_KEY).",
        )

    model = body.model if body.model in _ALLOWED_MODELS else "gemini-2.5-flash"

    user_content = body.message
    if body.agent_id:
        user_content = f"[Agent context: {body.agent_id}]\n\n{body.message}"

    payload = {
        "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_content}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 2048,
        },
    }

    url = f"{_GEMINI_BASE}/models/{model}:generateContent?key={api_key}"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini API error: {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini network error: {exc}",
        ) from exc

    try:
        reply_text: str = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        input_tokens: int = usage.get("promptTokenCount", 0)
        output_tokens: int = usage.get("candidatesTokenCount", 0)
    except (KeyError, IndexError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unexpected Gemini response shape: {exc}",
        ) from exc

    return NotaryChatResponse(
        reply=reply_text,
        model_used=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
