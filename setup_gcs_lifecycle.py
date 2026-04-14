"""
setup_gcs_lifecycle.py

一次性執行：設定 GCS Lifecycle Policy（更新版決策 GCS Lifecycle）。
- raw/       → 15 天後自動刪除
- processed/ → 15 天後自動刪除
- converted/ → 永久保留（不設 lifecycle）

執行：
    python setup_gcs_lifecycle.py

⚠ 需要有 GCS bucket 的 storage.buckets.update 權限。
"""
import os
from dotenv import load_dotenv
from google.cloud import storage

load_dotenv()

BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "your-rag-bucket")
LIFECYCLE_DAYS = 15


def setup_lifecycle() -> None:
    client = storage.Client()
    bucket = client.get_bucket(BUCKET_NAME)

    # GCS lifecycle rule：prefix 匹配 + age 條件
    rules = [
        {
            "action": {"type": "Delete"},
            "condition": {
                "age": LIFECYCLE_DAYS,
                "matchesPrefix": ["raw/"],
            },
        },
        {
            "action": {"type": "Delete"},
            "condition": {
                "age": LIFECYCLE_DAYS,
                "matchesPrefix": ["processed/"],
            },
        },
    ]

    bucket.lifecycle_rules = rules
    bucket.patch()

    print(f"✅ GCS Lifecycle Policy 設定完成")
    print(f"   Bucket: {BUCKET_NAME}")
    print(f"   raw/       → {LIFECYCLE_DAYS} 天後自動刪除")
    print(f"   processed/ → {LIFECYCLE_DAYS} 天後自動刪除")
    print(f"   converted/ → 永久保留")


if __name__ == "__main__":
    setup_lifecycle()
