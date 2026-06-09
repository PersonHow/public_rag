"""
app/services/ai/embedding.py

Gemini Embedding 001 向量化服務。
使用 Vertex AI 原生 REST API（httpx async）。

限制：gemini-embedding-001 每次請求只能處理 1 筆文字。
策略：asyncio.gather + Semaphore 並發呼叫（上限 5）。
維度：output_dimensionality=768（MRL 截短，與 Qdrant collection 一致）。

token 管理：使用 google-auth ADC（與 PDF 路徑相同機制）。
本機開發：ADC via gcloud auth application-default login。
Cloud Run：Service Account 自動處理。
"""
import asyncio
from typing import Optional

import google.auth
import google.auth.transport.requests
import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("embedding")

_EMBEDDING_URL_TEMPLATE = (
    "https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
    "/locations/{location}/publishers/google/models/{model}:predict"
)

# 並發上限（保護 Vertex AI rate limit）
_SEMAPHORE: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    """lazy init，避免在 event loop 啟動前建立 Semaphore。"""
    global _SEMAPHORE
    if _SEMAPHORE is None:
        _SEMAPHORE = asyncio.Semaphore(5)
    return _SEMAPHORE


async def _get_access_token() -> str:
    """
    非同步取得 GCP access token（google-auth ADC）。
    credentials.refresh() 是同步阻塞 I/O，用 run_in_executor 避免阻塞事件迴圈。
    """
    loop = asyncio.get_running_loop()

    def _refresh() -> str:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        return credentials.token

    return await loop.run_in_executor(None, _refresh)


def _is_retryable_embedding_error(exc: BaseException) -> bool:
    """
    只對暫時性錯誤重試：連線/逾時，以及 HTTP 429 / 5xx。
    不可重試的 4xx（400/401/403/404 等）直接失敗，避免無謂的指數退避。
    """
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return False


_EMBEDDING_DIM = 768


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable_embedding_error),
)
async def embed_text(
    text: str,
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> list[float]:
    """
    單筆向量化，回傳 768 維 float list。

    task_type:
      RETRIEVAL_DOCUMENT — 寫入 Qdrant 時（chunk 內容）
      RETRIEVAL_QUERY    — 查詢時（Phase 5，問題向量化）
    """
    url = _EMBEDDING_URL_TEMPLATE.format(
        location=settings.VERTEX_AI_LOCATION,
        project=settings.VERTEX_AI_PROJECT,
        model=settings.GEMINI_EMBEDDING_MODEL,
    )
    token = await _get_access_token()

    payload = {
        "instances": [{"content": text, "task_type": task_type}],
        "parameters": {"outputDimensionality": 768},
    }

    async with _get_semaphore():
        async with httpx.AsyncClient(timeout=30.0) as client:
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
        vector = data["predictions"][0]["embeddings"]["values"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"Vertex embedding 回應格式非預期: {e}") from e

    if len(vector) != _EMBEDDING_DIM:
        # 維度不符會在寫入 Qdrant 時才爆，提早在邊界擋下
        raise ValueError(
            f"Embedding 維度不符：預期 {_EMBEDDING_DIM}，實得 {len(vector)}"
        )
    return vector


async def embed_texts(
    texts: list[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> list[list[float]]:
    """
    批次向量化（並發呼叫）。
    回傳順序與輸入順序一致。
    空 list 直接回傳 []。
    """
    if not texts:
        return []
    tasks = [embed_text(t, task_type) for t in texts]
    results = await asyncio.gather(*tasks)
    logger.info(f"embed_texts 完成：{len(texts)} 筆", extra={"count": len(texts)})
    return list(results)
