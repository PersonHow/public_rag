"""
app/services/qdrant_service.py

Qdrant 操作封裝。

collection: "chunks"，768 維，Cosine distance
多租戶隔離：所有查詢強制帶 company_id payload filter，不可省略。

公開介面：
  init_collection()  — 確保 collection 存在（冪等），FastAPI startup 呼叫
  upsert_chunks()    — 批次寫入向量 + payload，每批 50 筆
  search()           — Phase 5 語意搜尋，強制 company_id filter
"""
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("qdrant")

COLLECTION_NAME = "chunks"
VECTOR_SIZE = 768
UPSERT_BATCH_SIZE = 50


def _get_client() -> QdrantClient:
    return QdrantClient(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        api_key=settings.QDRANT_API_KEY or None,
        timeout=30,
    )


def init_collection() -> None:
    """
    確保 chunks collection 存在（冪等）。
    已存在則跳過，不報錯。
    FastAPI startup event 中呼叫。
    """
    client = _get_client()

    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME in existing:
        logger.info(f"Qdrant collection '{COLLECTION_NAME}' 已存在，跳過建立")
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )

    # Payload index 加速 filter 查詢
    for field, schema in [
        ("company_id", PayloadSchemaType.KEYWORD),
        ("doc_type", PayloadSchemaType.KEYWORD),
        ("product_id", PayloadSchemaType.KEYWORD),
    ]:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name=field,
            field_schema=schema,
        )

    logger.info(
        f"Qdrant collection '{COLLECTION_NAME}' 建立完成",
        extra={"vector_size": VECTOR_SIZE, "distance": "Cosine"},
    )


def upsert_chunks(points: list[dict[str, Any]]) -> None:
    """
    批次 upsert，每批最多 UPSERT_BATCH_SIZE 筆。

    points 每筆格式：
    {
        "id": str(chunk_id),      # UUID string，Qdrant point ID
        "vector": list[float],    # 768 維
        "payload": {
            "company_id":   str,
            "chunk_id":     str,
            "doc_id":       str,
            "doc_type":     str,
            "rule_version": str,
            "face":         str | None,
            "product_name": str | None,
            "product_id":   str | None,
            "situation":    str | None,
            "action":       str | None,
            "embed_text":   str,      # 保留供 debug 直接在 Qdrant 查看
        }
    }
    """
    if not points:
        return

    client = _get_client()
    total = len(points)

    for i in range(0, total, UPSERT_BATCH_SIZE):
        batch = points[i : i + UPSERT_BATCH_SIZE]
        qdrant_points = [
            PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in batch
        ]
        client.upsert(collection_name=COLLECTION_NAME, points=qdrant_points)
        logger.debug(
            f"Qdrant upsert batch {i // UPSERT_BATCH_SIZE + 1}",
            extra={"batch_size": len(batch)},
        )

    logger.info(f"Qdrant upsert 完成", extra={"total": total})


def search(
    query_vector: list[float],
    company_id: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    語意搜尋。強制帶 company_id filter（多租戶隔離，不可省略）。
    Phase 5 用。

    Returns:
        [{"chunk_id": str, "score": float, "payload": dict}, ...]
    """
    client = _get_client()
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        query_filter=Filter(
            must=[FieldCondition(key="company_id", match=MatchValue(value=company_id))]
        ),
        limit=top_k,
        with_payload=True,
    )
    return [
        {
            "chunk_id": r.payload.get("chunk_id"),
            "score": r.score,
            "payload": r.payload,
        }
        for r in results
    ]


def delete_chunks_by_ids(chunk_ids: list[str]) -> None:
    """
    依 chunk_id 列表從 Qdrant 刪除向量。
    用於 upsert 失敗時回滾部分寫入的資料。
    """
    if not chunk_ids:
        return
    client = _get_client()
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=chunk_ids,
    )
    logger.info(f"Qdrant rollback 刪除完成", extra={"deleted_count": len(chunk_ids)})


def count_by_session(session_id: str, company_id: str) -> int:
    """
    驗證用：計算 Qdrant 中某 session 的向量數量（透過 doc_id 聚合）。
    實際上 Qdrant 沒有 session_id payload，透過 company_id + doc_id 集合比對。
    Phase 4 debug endpoint 用。
    """
    client = _get_client()
    result = client.count(
        collection_name=COLLECTION_NAME,
        count_filter=Filter(
            must=[FieldCondition(key="company_id", match=MatchValue(value=company_id))]
        ),
        exact=True,
    )
    return result.count
