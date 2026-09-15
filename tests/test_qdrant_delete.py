"""
tests/test_qdrant_delete.py

delete_chunks_by_doc_ids 單元測試（mock QdrantClient，不連線）。
重點：
  - 空 doc_ids 是 no-op，完全不碰 client
  - filter 正確帶 company_id（多租戶隔離）+ doc_id MatchAny（批次）
"""
from unittest.mock import MagicMock, patch

from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

from app.services.ai import qdrant_service


def test_empty_doc_ids_is_noop():
    """空 doc_ids 不應建立 client、不應呼叫 delete。"""
    with patch.object(qdrant_service, "_get_client") as mock_get_client:
        qdrant_service.delete_chunks_by_doc_ids([], "company-1")
        mock_get_client.assert_not_called()


def test_delete_assembles_company_and_doc_filter():
    """filter 必須同時帶 company_id（MatchValue）與 doc_id（MatchAny）。"""
    mock_client = MagicMock()
    with patch.object(qdrant_service, "_get_client", return_value=mock_client):
        qdrant_service.delete_chunks_by_doc_ids(["doc-a", "doc-b"], "company-1")

    mock_client.delete.assert_called_once()
    selector: Filter = mock_client.delete.call_args.kwargs["points_selector"]

    # 強制帶 company_id（多租戶隔離，不可省略）
    company_conds = [
        c for c in selector.must
        if isinstance(c, FieldCondition) and c.key == "company_id"
    ]
    assert len(company_conds) == 1
    assert isinstance(company_conds[0].match, MatchValue)
    assert company_conds[0].match.value == "company-1"

    # doc_id 用 MatchAny 一次刪多個
    doc_conds = [
        c for c in selector.must
        if isinstance(c, FieldCondition) and c.key == "doc_id"
    ]
    assert len(doc_conds) == 1
    assert isinstance(doc_conds[0].match, MatchAny)
    assert doc_conds[0].match.any == ["doc-a", "doc-b"]


def test_delete_targets_configured_collection():
    """刪除必須打在設定的 collection 上。"""
    mock_client = MagicMock()
    with patch.object(qdrant_service, "_get_client", return_value=mock_client):
        qdrant_service.delete_chunks_by_doc_ids(["doc-a"], "company-1")

    assert mock_client.delete.call_args.kwargs["collection_name"] == qdrant_service.COLLECTION_NAME
