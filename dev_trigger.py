"""
dev_trigger.py

本機開發用：模擬 Cloud Tasks 觸發 Worker（§14 風險注意事項）。
Cloud Tasks 本機無法直接測試，用此腳本直打 /internal/tasks/process-document。

使用方式：
    python dev_trigger.py <session_id> <doc_id> <doc_type>

範例：
    python dev_trigger.py abc123 def456 pdf
    python dev_trigger.py abc123 def456 docx
    python dev_trigger.py abc123 def456 tap
"""
import sys
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("WORKER_BASE_URL", "http://localhost:8000")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "dev-internal-token-change-in-prod")
DEFAULT_COMPANY_ID = os.getenv("DEFAULT_COMPANY_ID", "dev-company")


def trigger(session_id: str, doc_id: str, doc_type: str) -> None:
    url = f"{BASE_URL}/internal/tasks/process-document"
    payload = {
        "session_id": session_id,
        "doc_id": doc_id,
        "doc_type": doc_type,
        "company_id": DEFAULT_COMPANY_ID,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Token": INTERNAL_TOKEN,
    }

    print(f"POST {url}")
    print(f"Payload: {payload}")

    response = httpx.post(url, json=payload, headers=headers, timeout=300.0)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python dev_trigger.py <session_id> <doc_id> <doc_type>")
        sys.exit(1)

    trigger(
        session_id=sys.argv[1],
        doc_id=sys.argv[2],
        doc_type=sys.argv[3],
    )
