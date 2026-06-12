import logging

from fastapi import APIRouter, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/translate", tags=["translate"])


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=12000)
    source_language: str = Field(default="auto", max_length=40)
    target_language: str = Field(default="zh-CN", max_length=40)


class TranslateResponse(BaseModel):
    translated_text: str
    source_language: str
    target_language: str
    model: str


def _api_key_ready() -> bool:
    return bool(DEEPSEEK_API_KEY and DEEPSEEK_API_KEY != "your_api_key_here")


@router.post("", response_model=TranslateResponse)
async def translate_text(payload: TranslateRequest) -> TranslateResponse:
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text to translate cannot be empty.")
    if not _api_key_ready():
        raise HTTPException(
            status_code=503,
            detail="Translation is unavailable because DEEPSEEK_API_KEY is not configured.",
        )

    client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    target = payload.target_language or "zh-CN"
    source = payload.source_language or "auto"
    try:
        response = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise academic paper translator. Translate the user's "
                        "paper excerpt into natural Simplified Chinese. Preserve technical "
                        "terms, equations, citations, and paragraph boundaries. Return only "
                        "the translation."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Source language: {source}\n"
                        f"Target language: {target}\n\n"
                        f"Text:\n{text}"
                    ),
                },
            ],
            temperature=0.2,
        )
    except Exception as exc:
        logger.error("Translation request failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Translation request failed: {exc}") from exc

    translated = (response.choices[0].message.content or "").strip()
    if not translated:
        raise HTTPException(status_code=502, detail="Translation service returned an empty response.")

    return TranslateResponse(
        translated_text=translated,
        source_language=source,
        target_language=target,
        model=DEEPSEEK_MODEL,
    )
