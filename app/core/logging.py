"""
app/core/logging.py

JSON structured logging，對接 GCP Cloud Logging。
所有 log 必須帶 phase, service, session_id, company_id 基本欄位。
"""
import logging
import sys
from typing import Any

try:
    from pythonjsonlogger.json import JsonFormatter as _JsonFormatter
except ImportError:
    from pythonjsonlogger.jsonlogger import JsonFormatter as _JsonFormatter  # type: ignore


class RagJsonFormatter(_JsonFormatter):
    """強制每條 log 帶 phase / service / session_id / company_id。"""

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)

        if 'asctime' not in log_record and 'timestamp' not in log_record:
            log_record['asctime'] = self.formatTime(record, self.datefmt)

        # 保留欄位順序
        log_record.setdefault("phase", getattr(record, "phase", "phase1"))
        log_record.setdefault("service", getattr(record, "service", "app"))
        log_record.setdefault("session_id", getattr(record, "session_id", None))
        log_record.setdefault("company_id", getattr(record, "company_id", "dev-company"))

        # level 標準化
        log_record["level"] = record.levelname


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    formatter = RagJsonFormatter(
        fmt="%(asctime)s %(level)s %(phase)s %(service)s %(session_id)s %(company_id)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
        rename_fields={"asctime": "timestamp"},
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(service: str, phase: str = "phase1") -> logging.LoggerAdapter:
    """
    取得帶預設 extra 的 LoggerAdapter。

    使用方式：
        logger = get_logger("upload")
        logger.info("文件上傳完成", extra={"doc_id": doc_id, "filename": filename})

        # 帶 session_id：
        logger = get_logger("ocr").with_context(session_id="abc", company_id="dev-company")
    """
    base_logger = logging.getLogger(f"rag.{service}")
    return logging.LoggerAdapter(
        base_logger,
        extra={"phase": phase, "service": service, "session_id": None, "company_id": "dev-company"},
    )
