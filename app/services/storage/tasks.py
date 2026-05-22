"""
app/services/storage/tasks.py

Cloud Tasks 任務派送。
本機開發：直接打 /internal/tasks/process-document（見 dev_trigger.py）。

Phase 4 新增：enqueue_ingest_chunks()

⚠ retry_config 已移除：Cloud Tasks HTTP target 不支援在 task body 內設定
  retry_config，需在 Queue 層級設定（GCP Console → Cloud Tasks → Queue 設定）。
"""
import json
import uuid

from google.cloud import tasks_v2

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("tasks")


def enqueue_process_document(
    session_id: uuid.UUID,
    doc_id: uuid.UUID,
    doc_type: str,
    company_id: str,
) -> str:
    """
    發送 Cloud Tasks 任務，觸發 Worker 處理文件。
    回傳 task name。
    重試次數由 Queue 層級設定（非 task body）。
    """
    client = tasks_v2.CloudTasksClient()
    queue_path = client.queue_path(
        settings.CLOUD_TASKS_PROJECT,
        settings.CLOUD_TASKS_LOCATION,
        settings.CLOUD_TASKS_QUEUE,
    )

    payload = json.dumps({
        "session_id": str(session_id),
        "doc_id": str(doc_id),
        "doc_type": doc_type,
        "company_id": company_id,
    }).encode("utf-8")

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{settings.WORKER_BASE_URL}/internal/tasks/process-document",
            "headers": {
                "Content-Type": "application/json",
                "X-Internal-Token": settings.INTERNAL_TOKEN,
            },
            "body": payload,
        },
    }

    response = client.create_task(request={"parent": queue_path, "task": task})
    task_name = response.name

    logger.info(
        "Cloud Tasks 任務已派送",
        extra={
            "session_id": str(session_id),
            "doc_id": str(doc_id),
            "doc_type": doc_type,
            "task_name": task_name,
        },
    )
    return task_name


def enqueue_ingest_chunks(session_id: uuid.UUID) -> str:
    """
    Phase 4：發送 Cloud Tasks 任務，觸發向量寫入 worker。
    由 confirm_session 呼叫（session confirmed 後自動派送）。
    回傳 task name。
    """
    client = tasks_v2.CloudTasksClient()
    queue_path = client.queue_path(
        settings.CLOUD_TASKS_PROJECT,
        settings.CLOUD_TASKS_LOCATION,
        settings.CLOUD_TASKS_QUEUE,
    )

    payload = json.dumps({
        "session_id": str(session_id),
    }).encode("utf-8")

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{settings.WORKER_BASE_URL}/internal/tasks/ingest-chunks",
            "headers": {
                "Content-Type": "application/json",
                "X-Internal-Token": settings.INTERNAL_TOKEN,
            },
            "body": payload,
        },
    }

    response = client.create_task(request={"parent": queue_path, "task": task})
    task_name = response.name

    logger.info(
        "ingest-chunks Cloud Tasks 任務已派送",
        extra={"session_id": str(session_id), "task_name": task_name},
    )
    return task_name
