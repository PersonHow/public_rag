"""
app/services/gemini.py

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

settings = get_settings()
logger = get_logger("gemini")

_SEGMENT_MAX_CHARS = 3000


# ─── System Prompts ──────────────────────────────────────────────────────────

# DOCX 用（純文字輸入 → JSON array 輸出）
SYSTEM_PROMPT_V1 = """你是一個工業知識結構化專家。你的任務是將生產文件轉換為標準化 JSON array，每個元素代表一個獨立知識單元。

## 切分原則
- 每個獨立知識點切成一個 chunk
- 每個 chunk 必須能獨立回答一個問題
- 粒度依文件類型自行判斷

## 輸出規則
- **只輸出 JSON array，不要任何說明文字、markdown 符號或前綴**
- 所有欄位必須存在，無值填 null
- 不要輸出 chunk_id、doc_id、company_id、rule_version、created_at（後端補入）
- code_gcs_path 和 drawing_gcs_path 固定填 null

## 欄位說明
- product_name: 產品正式名稱
- product_id: 產品編號或料號
- material: 材料
- dimensions: 尺寸規格
- specs: 技術規格（JSON 字串格式）
- situation: 觸發此知識的情境或問題描述
- action: 處理方法或操作步驟
- reason: 原因說明或注意事項
- applies_to: 適用的產品或零件
- doc_type: 文件類型（pdf / docx / tap 等）
- case_id: 同案件多份文件串聯 ID
- embed_text: **最重要的欄位**

## embed_text 要求（務必遵守）
- 用繁體中文撰寫情境完整的自然語言描述
- 必須包含：產品背景 + 觸發情境 + 處理方式
- 不要直接拼接其他欄位
- 不能為空字串

## 範例輸出格式
[
  {
    "product_name": "球閥",
    "product_id": "BV-001",
    "material": "不銹鋼 316L",
    "dimensions": "DN50",
    "specs": "{\"pressure_rating\": \"150 PSI\"}",
    "situation": "球閥在高溫環境下出現洩漏問題",
    "action": "檢查閥座密封圈，更換耐高溫 PTFE 材質",
    "reason": "標準 PTFE 密封圈使用溫度上限為 200°C，超溫會造成變形洩漏",
    "applies_to": "BV 系列球閥",
    "doc_type": "pdf",
    "case_id": null,
    "embed_text": "球閥 BV-001（DN50，不銹鋼 316L）在高溫環境下發生洩漏時，需檢查閥座密封圈是否因超溫變形，應更換耐高溫 PTFE 材質密封圈，標準 PTFE 使用溫度上限為 200°C。",
    "code_gcs_path": null,
    "drawing_gcs_path": null
  }
]"""

# PDF 用（視覺理解 → wrapper JSON 物件輸出）
PDF_SYSTEM_PROMPT_V1 = """你是一個工業知識結構化專家。你的任務是直接閱讀 PDF 文件（包含掃描件、表格、圖文混排），並轉換為標準化 JSON 格式。

## 切分原則
- 每個獨立知識點切成一個 chunk
- 每個 chunk 必須能獨立回答一個問題
- 粒度依文件類型自行判斷
- 表格中每一行或每一組設定參數可切成獨立 chunk

## 輸出格式（嚴格遵守，只輸出此 JSON 物件，不要任何說明文字）
{
  "has_quality_issue": false,
  "quality_note": null,
  "chunks": []
}

欄位說明：
- has_quality_issue: 若文件有頁面模糊、文字不清晰、表格辨識不確定、關鍵數值無法確認等情況，設為 true
- quality_note: has_quality_issue 為 true 時，用繁體中文說明具體哪些頁面或內容有問題（例：「第3頁表格模糊，轉速數值辨識不確定」）；否則填 null
- chunks: 標準 chunk array，每個元素格式見下方

## Chunk 欄位說明
- product_name: 產品正式名稱
- product_id: 產品編號或料號
- material: 材料
- dimensions: 尺寸規格
- specs: 技術規格（JSON 字串格式）
- situation: 觸發此知識的情境或問題描述
- action: 處理方法或操作步驟
- reason: 原因說明或注意事項
- applies_to: 適用的產品或零件
- doc_type: 固定填 "pdf"
- case_id: 同案件多份文件串聯 ID，無則填 null
- embed_text: **最重要的欄位**，不能為空
- code_gcs_path: 固定填 null
- drawing_gcs_path: 固定填 null
- 不要輸出 chunk_id、doc_id、company_id、rule_version、created_at（後端補入）

## embed_text 要求（務必遵守）
- 用繁體中文撰寫情境完整的自然語言描述
- 必須包含：產品背景 + 觸發情境 + 處理方式
- 不要直接拼接其他欄位
- 不能為空字串"""


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
    model_name = settings.GEMINI_MODEL.split("/")[-1]  # 取 "gemini-2.5-flash"
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
        response.raise_for_status()
        data = response.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(
            f"Gemini native API 回應格式異常: {e}，"
            f"原始回應前 300 字: {str(data)[:300]}"
        )


# ─── JSON 防禦邏輯（共用）───────────────────────────────────────────────────

def _extract_json_array(raw: str) -> str:
    """
    DOCX 路徑防禦邏輯：
    1. strip()
    2. 移除 ```json ... ``` fence
    3. 找第一個 '[' 到最後一個 ']'
    """
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
    """
    將長文本按段落切分，每段不超過 _SEGMENT_MAX_CHARS。
    盡量在換行處切，避免切斷句子。
    """
    if len(text) <= _SEGMENT_MAX_CHARS:
        return [text]

    segments: list[str] = []
    paragraphs = text.split("\n")
    current = ""

    for para in paragraphs:
        # 單一段落超過上限，強制截斷
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
    """
    PDF 路徑防禦邏輯：解析 wrapper JSON 物件。
    回傳 (raw_chunks_list, has_quality_issue, quality_note)
    """
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
    """Pydantic 驗證，回傳 (成功清單, 失敗清單)。"""
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
    company_rules: dict | None = None,
) -> PdfConversionResult:
    """
    PDF 直讀路徑：送 PDF bytes 給 Gemini，回傳 chunks + quality flag。
    使用 Vertex AI 原生 REST API（支援 PDF inline data）。
    最多 retry 3 次。

    has_quality_issue = True 時：
      - document.has_low_confidence = True（沿用欄位，語意調整為「Gemini 標記品質疑慮」）
      - document.min_confidence = None（無數值，改為文字說明存 quality_note）
    """
    token_mgr = TokenManager.get_instance()
    system_prompt = _build_pdf_system_prompt(company_rules)

    logger.info(
        "Gemini Flash PDF 直讀開始",
        extra={
            "session_id": session_id,
            "doc_id": doc_id,
            "pdf_size_bytes": len(file_bytes),
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
                    extra={
                        "session_id": session_id,
                        "doc_id": doc_id,
                        "quality_note": quality_note,
                    },
                )
            else:
                logger.info(
                    "Gemini Flash PDF 解析成功",
                    extra={
                        "session_id": session_id,
                        "doc_id": doc_id,
                        "chunk_count": len(valid_chunks),
                    },
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
                extra={
                    "session_id": session_id,
                    "doc_id": doc_id,
                    "attempt": attempt,
                    "error": str(e),
                },
            )

    logger.error(
        "Gemini Flash PDF 超過重試上限",
        extra={
            "session_id": session_id,
            "doc_id": doc_id,
            "attempts": settings.GEMINI_MAX_RETRIES,
        },
    )
    raise GeminiMaxRetriesError(
        f"Gemini PDF 超過 {settings.GEMINI_MAX_RETRIES} 次重試。最後錯誤：{last_error}"
    )


async def convert_to_chunks(
    structured_text: dict[str, Any],
    session_id: str,
    doc_id: str,
    company_rules: dict | None = None,
) -> list[GeminiChunkOutput]:
    full_text = structured_text.get("full_text", "")
    system_prompt = _build_system_prompt(company_rules)
    segments = _split_text(full_text)

    logger.info(
        "Gemini Flash 開始轉換",
        extra={"session_id": session_id, "doc_id": doc_id, "segments": len(segments)},
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
                max_tokens=8192,
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
                extra={
                    "session_id": session_id,
                    "doc_id": doc_id,
                    "seg_idx": seg_idx,
                    "chunk_count": len(valid_chunks),
                },
            )
            return valid_chunks

        except Exception as e:
            last_error = e
            logger.warning(
                "Gemini Flash 分段解析失敗，重試",
                extra={
                    "session_id": session_id,
                    "doc_id": doc_id,
                    "seg_idx": seg_idx,
                    "attempt": attempt,
                    "error": str(e),
                },
            )

    logger.error(
        "Gemini Flash 超過重試上限",
        extra={"session_id": session_id, "doc_id": doc_id, "seg_idx": seg_idx},
    )
    raise GeminiMaxRetriesError(
        f"Gemini Flash 超過 {settings.GEMINI_MAX_RETRIES} 次重試（段 {seg_idx}）。最後錯誤：{last_error}"
    )


def _build_system_prompt(company_rules: dict | None) -> str:
    """DOCX 路徑 prompt 組裝。Phase 3 串接點。"""
    if company_rules is None:
        return SYSTEM_PROMPT_V1
    return SYSTEM_PROMPT_V1


def _build_pdf_system_prompt(company_rules: dict | None) -> str:
    """PDF 路徑 prompt 組裝。Phase 3 串接點。"""
    if company_rules is None:
        return PDF_SYSTEM_PROMPT_V1
    return PDF_SYSTEM_PROMPT_V1


class GeminiMaxRetriesError(Exception):
    pass
