"""
app/services/ai/gemini.py

Vertex AI Gemini Flash 格式轉換服務。

兩條處理路徑：
  DOCX → structured text → convert_to_chunks()    （OpenAI-compat endpoint）
  PDF  → file bytes      → convert_pdf_to_chunks() （Vertex AI 原生 REST API，支援 PDF inline data）

防禦邏輯（兩條路徑共用）：
1. strip()
2. 移除 ```json ... ``` markdown fence
3. 找邊界截取 JSON
4. json.loads()
5. Pydantic 驗證：embed_text 不能為空字串或 null
6. 任何 chunk 失敗 → 整批 retry，記錄 WARNING log
7. 超過 3 次 → 拋出 GeminiMaxRetriesError

Phase 3 變更：
  _build_system_prompt / _build_pdf_system_prompt 改為呼叫 PromptBuilder，
  接受 company_context dict（含 company_name、industry、rules）。
  公開函式參數 company_rules → company_context。

TokenManager 單例：過期前 5 分鐘自動刷新，asyncio.Lock thread-safe。
"""
import asyncio
import base64
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import google.auth
import google.auth.transport.requests
import httpx
from openai import AsyncOpenAI
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.chunk import GeminiChunkOutput, GeminiChunkValidationError
from app.services.rules import PromptBuilder

settings = get_settings()
logger = get_logger("gemini")

_SEGMENT_MAX_CHARS = 2000
_MAX_TOKENS = 16384


# ─── TokenManager 單例 ───────────────────────────────────────────────────────

class TokenManager:
    """
    Vertex AI access token 管理。
    - GCP 環境：ADC
    - 本機：GOOGLE_APPLICATION_CREDENTIALS
    - 過期前 5 分鐘自動刷新，asyncio.Lock thread-safe
    """

    _instance: "TokenManager | None" = None

    def __init__(self) -> None:
        self._credentials, self._project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self._refresh_lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "TokenManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def get_token(self) -> str:
        async with self._refresh_lock:
            now = datetime.now(timezone.utc)
            expiry = getattr(self._credentials, "expiry", None)

            if expiry is not None and expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)

            needs_refresh = (
                expiry is None
                or self._credentials.token is None
                or (expiry - now).total_seconds() < 300
            )

            if needs_refresh:
                request = google.auth.transport.requests.Request()
                self._credentials.refresh(request)

            return self._credentials.token


# ─── DOCX 路徑（OpenAI-compat endpoint）────────────────────────────────────

def _build_vertex_client(token: str) -> AsyncOpenAI:
    endpoint = (
        f"https://{settings.VERTEX_AI_LOCATION}-aiplatform.googleapis.com"
        f"/v1beta1/projects/{settings.VERTEX_AI_PROJECT}"
        f"/locations/{settings.VERTEX_AI_LOCATION}/endpoints/openapi"
    )
    return AsyncOpenAI(base_url=endpoint, api_key=token)


# ─── PDF 路徑（Vertex AI 原生 REST API）─────────────────────────────────────

async def _call_gemini_native_api(
    token: str,
    system_prompt: str,
    pdf_bytes: bytes,
) -> str:
    """
    Vertex AI 原生 generateContent API。
    OpenAI-compat endpoint 不支援 PDF inline data，必須用此原生 API。
    """
    model_name = settings.GEMINI_MODEL.split("/")[-1]
    url = (
        f"https://{settings.VERTEX_AI_LOCATION}-aiplatform.googleapis.com"
        f"/v1/projects/{settings.VERTEX_AI_PROJECT}"
        f"/locations/{settings.VERTEX_AI_LOCATION}"
        f"/publishers/google/models/{model_name}:generateContent"
    )

    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [{
            "role": "user",
            "parts": [
                {
                    "inline_data": {
                        "mime_type": "application/pdf",
                        "data": base64.b64encode(pdf_bytes).decode("utf-8"),
                    }
                },
                {"text": "請分析此 PDF 文件，依照指定格式輸出 JSON。"},
            ],
        }],
        "generation_config": {
            "temperature": 0.1,
            "max_output_tokens": 8192,
        },
    }

    async with httpx.AsyncClient(timeout=settings.GEMINI_PDF_TIMEOUT_SEC) as client:
        response = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "unknown")
        raise httpx.HTTPStatusError(
            f"Gemini API 請求頻率超限（429），Retry-After: {retry_after}",
            request=response.request,
            response=response,
        )
    if response.status_code >= 500:
        raise httpx.HTTPStatusError(
            f"Gemini API 伺服器錯誤（{response.status_code}），body: {response.text[:200]}",
            request=response.request,
            response=response,
        )
    response.raise_for_status()

    try:
        data = response.json()
    except Exception as json_err:
        raise ValueError(
            f"Gemini 回傳非 JSON 內容: {json_err}，body 前 200 字: {response.text[:200]}"
        )

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(
            f"Gemini native API 回應結構異常: {e}，"
            f"原始回應前 300 字: {str(data)[:300]}"
        )


# ─── JSON 防禦邏輯（共用）───────────────────────────────────────────────────

def _extract_json_array(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or start >= end:
        raise ValueError(f"找不到 JSON array 邊界。原始回應前 200 字：{text[:200]}")

    return text[start: end + 1]


def _split_text(text: str) -> list[str]:
    if len(text) <= _SEGMENT_MAX_CHARS:
        return [text]

    segments: list[str] = []
    paragraphs = text.split("\n")
    current = ""

    for para in paragraphs:
        if len(para) > _SEGMENT_MAX_CHARS:
            if current:
                segments.append(current.strip())
                current = ""
            for i in range(0, len(para), _SEGMENT_MAX_CHARS):
                segments.append(para[i:i + _SEGMENT_MAX_CHARS])
            continue

        if len(current) + len(para) + 1 > _SEGMENT_MAX_CHARS:
            if current:
                segments.append(current.strip())
            current = para
        else:
            current = current + "\n" + para if current else para

    if current:
        segments.append(current.strip())

    return [s for s in segments if s]


def _extract_pdf_wrapper(raw: str) -> tuple[list[dict], bool, str | None]:
    text = raw.strip()
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or start >= end:
        raise ValueError(f"找不到 JSON 物件邊界。原始回應前 200 字：{text[:200]}")

    obj = json.loads(text[start: end + 1])

    chunks = obj.get("chunks", [])
    if not isinstance(chunks, list):
        raise ValueError(f"chunks 欄位不是 array，型別：{type(chunks)}")

    has_quality_issue = bool(obj.get("has_quality_issue", False))
    quality_note = obj.get("quality_note", None)

    return chunks, has_quality_issue, quality_note


def _validate_chunks(
    raw_list: list[dict],
) -> tuple[list[GeminiChunkOutput], list[GeminiChunkValidationError]]:
    valid: list[GeminiChunkOutput] = []
    errors: list[GeminiChunkValidationError] = []

    for i, item in enumerate(raw_list):
        try:
            valid.append(GeminiChunkOutput.model_validate(item))
        except ValidationError as e:
            errors.append(
                GeminiChunkValidationError(
                    index=i,
                    product_name=item.get("product_name"),
                    embed_text=item.get("embed_text"),
                    error=str(e),
                )
            )

    return valid, errors


# ─── Prompt 組裝（Phase 3：委派給 PromptBuilder）────────────────────────────

def _build_system_prompt(company_context: dict | None) -> str:
    """DOCX 路徑 prompt 組裝。Phase 3：呼叫 PromptBuilder。"""
    return PromptBuilder.build_system_prompt(company_context)


def _build_pdf_system_prompt(company_context: dict | None) -> str:
    """PDF 路徑 prompt 組裝。Phase 3：呼叫 PromptBuilder。"""
    return PromptBuilder.build_pdf_system_prompt(company_context)


# ─── 公開介面 ────────────────────────────────────────────────────────────────

@dataclass
class PdfConversionResult:
    """convert_pdf_to_chunks 回傳結構。"""
    chunks: list[GeminiChunkOutput]
    has_quality_issue: bool
    quality_note: str | None


async def convert_pdf_to_chunks(
    file_bytes: bytes,
    session_id: str,
    doc_id: str,
    company_context: dict | None = None,   # Phase 3：原 company_rules 改為 company_context
) -> PdfConversionResult:
    """
    PDF 直讀路徑：送 PDF bytes 給 Gemini，回傳 chunks + quality flag。
    company_context 為 None 時使用通用預設 prompt（公司尚未設定 rules 時的行為）。
    """
    token_mgr = TokenManager.get_instance()
    system_prompt = _build_pdf_system_prompt(company_context)

    logger.info(
        "Gemini Flash PDF 直讀開始",
        extra={
            "session_id": session_id,
            "doc_id": doc_id,
            "pdf_size_bytes": len(file_bytes),
            "has_rules": company_context is not None and company_context.get("rules") is not None,
        },
    )

    last_error: Exception | None = None

    for attempt in range(1, settings.GEMINI_MAX_RETRIES + 1):
        try:
            token = await token_mgr.get_token()
            raw_output = await _call_gemini_native_api(token, system_prompt, file_bytes)

            raw_list, has_quality_issue, quality_note = _extract_pdf_wrapper(raw_output)

            if not raw_list:
                raise ValueError("chunks array 為空，文件可能完全無法解析")

            valid_chunks, validation_errors = _validate_chunks(raw_list)

            if validation_errors:
                logger.warning(
                    "PDF embed_text 驗證失敗，整批 retry",
                    extra={
                        "session_id": session_id,
                        "doc_id": doc_id,
                        "attempt": attempt,
                        "failed_chunk_count": len(validation_errors),
                        "failed_chunks": [e.model_dump() for e in validation_errors],
                    },
                )
                last_error = ValueError(f"{len(validation_errors)} 個 chunk 驗證失敗")
                continue

            if has_quality_issue:
                logger.warning(
                    "Gemini 標記 PDF 品質問題",
                    extra={"session_id": session_id, "doc_id": doc_id, "quality_note": quality_note},
                )
            else:
                logger.info(
                    "Gemini Flash PDF 解析成功",
                    extra={"session_id": session_id, "doc_id": doc_id, "chunk_count": len(valid_chunks)},
                )

            return PdfConversionResult(
                chunks=valid_chunks,
                has_quality_issue=has_quality_issue,
                quality_note=quality_note,
            )

        except Exception as e:
            last_error = e
            logger.warning(
                "Gemini Flash PDF 解析失敗，重試",
                extra={"session_id": session_id, "doc_id": doc_id, "attempt": attempt, "error": str(e)},
            )

    logger.error(
        "Gemini Flash PDF 超過重試上限",
        extra={"session_id": session_id, "doc_id": doc_id, "attempts": settings.GEMINI_MAX_RETRIES},
    )
    raise GeminiMaxRetriesError(
        f"Gemini PDF 超過 {settings.GEMINI_MAX_RETRIES} 次重試。最後錯誤：{last_error}"
    )


async def convert_to_chunks(
    structured_text: dict[str, Any],
    session_id: str,
    doc_id: str,
    company_context: dict | None = None,   # Phase 3：原 company_rules 改為 company_context
) -> list[GeminiChunkOutput]:
    """
    DOCX 路徑：分段送文字給 Gemini，回傳 chunks。
    company_context 為 None 時使用通用預設 prompt。
    """
    full_text = structured_text.get("full_text", "")
    system_prompt = _build_system_prompt(company_context)
    segments = _split_text(full_text)

    logger.info(
        "Gemini Flash 開始轉換",
        extra={
            "session_id": session_id,
            "doc_id": doc_id,
            "segments": len(segments),
            "has_rules": company_context is not None and company_context.get("rules") is not None,
        },
    )

    all_chunks: list[GeminiChunkOutput] = []

    for seg_idx, segment in enumerate(segments):
        chunks = await _convert_segment(
            segment=segment,
            seg_idx=seg_idx,
            total_segments=len(segments),
            system_prompt=system_prompt,
            session_id=session_id,
            doc_id=doc_id,
        )
        all_chunks.extend(chunks)

    logger.info(
        "Gemini Flash 全部分段完成",
        extra={"session_id": session_id, "doc_id": doc_id, "total_chunks": len(all_chunks)},
    )
    return all_chunks


async def _convert_segment(
    segment: str,
    seg_idx: int,
    total_segments: int,
    system_prompt: str,
    session_id: str,
    doc_id: str,
) -> list[GeminiChunkOutput]:
    token_mgr = TokenManager.get_instance()
    last_error: Exception | None = None

    for attempt in range(1, settings.GEMINI_MAX_RETRIES + 1):
        try:
            token = await token_mgr.get_token()
            client = _build_vertex_client(token)

            response = await client.chat.completions.create(
                model=settings.GEMINI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            f"請將以下文件內容（第 {seg_idx+1}/{total_segments} 段）"
                            f"轉換為標準化 JSON array：\n\n{segment}"
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=_MAX_TOKENS,
            )

            raw_output = response.choices[0].message.content or ""
            json_str = _extract_json_array(raw_output)
            raw_list = json.loads(json_str)

            if not isinstance(raw_list, list):
                raise ValueError(f"Gemini 輸出不是 JSON array，型別：{type(raw_list)}")

            valid_chunks, validation_errors = _validate_chunks(raw_list)

            if validation_errors:
                logger.warning(
                    "embed_text 驗證失敗，整批 retry",
                    extra={
                        "session_id": session_id,
                        "doc_id": doc_id,
                        "seg_idx": seg_idx,
                        "attempt": attempt,
                        "failed_chunk_count": len(validation_errors),
                        "failed_chunks": [e.model_dump() for e in validation_errors],
                    },
                )
                last_error = ValueError(f"{len(validation_errors)} 個 chunk 驗證失敗")
                continue

            logger.info(
                "Gemini Flash 分段解析成功",
                extra={"session_id": session_id, "doc_id": doc_id, "seg_idx": seg_idx, "chunk_count": len(valid_chunks)},
            )
            return valid_chunks

        except Exception as e:
            last_error = e
            logger.warning(
                "Gemini Flash 分段解析失敗，重試",
                extra={"session_id": session_id, "doc_id": doc_id, "seg_idx": seg_idx, "attempt": attempt, "error": str(e)},
            )

    logger.error(
        "Gemini Flash 超過重試上限",
        extra={"session_id": session_id, "doc_id": doc_id, "seg_idx": seg_idx},
    )
    raise GeminiMaxRetriesError(
        f"Gemini Flash 超過 {settings.GEMINI_MAX_RETRIES} 次重試（段 {seg_idx}）。最後錯誤：{last_error}"
    )


"""
generate_answer()：RAG 查詢專用，純文字生成，不做 chunk 解析。
與 convert_to_chunks / convert_pdf_to_chunks 完全獨立。
"""
async def generate_answer(
    system_prompt: str,
    user_prompt: str,
) -> str:
    """
    Phase 5 RAG 查詢專用：呼叫 Gemini Flash 生成條列式回答。
    走 OpenAI-compat endpoint（DOCX 路徑相同的 client）。
    純文字生成，不做 JSON 解析。
    失敗時直接拋出例外（由 query router 的 FastAPI error handler 處理）。
    """
    token_mgr = TokenManager.get_instance()
    token = await token_mgr.get_token()
    client = _build_vertex_client(token)
 
    response = await client.chat.completions.create(
        model=settings.GEMINI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,      # 回答比 ETL 轉換稍高一點，語氣更自然
        max_tokens=2048,
    )
 
    return (response.choices[0].message.content or "").strip()


class GeminiMaxRetriesError(Exception):
    pass
