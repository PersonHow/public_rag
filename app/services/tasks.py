"""
app/services/tasks.py

Cloud Tasks 任務派送。
本機開發：直接打 /internal/tasks/process-document（見 dev_trigger.py）。
"""
import json
import uuid

from google.cloud import tasks_v2
from google.protobuf import duration_pb2

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

    最大重試次數：3 次（更新版決策 3）。
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

    worker_url = f"{settings.WORKER_BASE_URL}/internal/tasks/process-document"

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": worker_url,
            "headers": {
                "Content-Type": "application/json",
                "X-Internal-Token": settings.INTERNAL_TOKEN,
            },
            "body": payload,
        },
        "retry_config": {
            "max_attempts": settings.CLOUD_TASKS_MAX_RETRIES,
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
