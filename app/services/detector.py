"""
app/services/detector.py

文件類型偵測：
- Upload 時：副檔名輕量偵測，只存 doc_type 字串

⚠ detect_pdf_route()（pdfplumber 試讀分流）已移除。
  PDF 現在統一送 Gemini Flash 直接視覺理解，不再區分掃描/文字型。
  掃描 PDF、加密 PDF、只讀 PDF、純文字 PDF 全部走同一條路徑。
"""
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger("detector")

# 副檔名 → doc_type 對照
EXTENSION_MAP: dict[str, str] = {
    ".docx": "docx",
    ".pdf": "pdf",
    ".tap": "tap",
    ".nc": "nc",
    ".dxf": "dxf",
}


def detect_doc_type_from_filename(filename: str) -> str:
    """
    Upload 時輕量偵測：只看副檔名。
    未知副檔名回傳 "unknown"。
    """
    ext = Path(filename).suffix.lower()
    doc_type = EXTENSION_MAP.get(ext, "unknown")
    logger.debug(f"副檔名偵測: {filename} → {doc_type}")
    return doc_type


def is_code_file(doc_type: str) -> bool:
    """加工程式檔案（tap / nc）：不進向量庫，只存 GCS 路徑。"""
    return doc_type in ("tap", "nc")


def is_skip_file(doc_type: str) -> bool:
    """v1 跳過處理的檔案（dxf / unknown）。"""
    return doc_type in ("dxf", "unknown")
