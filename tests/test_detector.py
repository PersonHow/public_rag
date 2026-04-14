"""
tests/test_detector.py

文件類型偵測器單元測試。不需要外部服務。
"""
import pytest
from app.services.detector import (
    PDF_SCAN_THRESHOLD,
    detect_doc_type_from_filename,
    detect_pdf_route,
    is_code_file,
    is_skip_file,
)


class TestDetectDocTypeFromFilename:
    def test_pdf(self):
        assert detect_doc_type_from_filename("report.pdf") == "pdf"
        assert detect_doc_type_from_filename("REPORT.PDF") == "pdf"

    def test_docx(self):
        assert detect_doc_type_from_filename("manual.docx") == "docx"

    def test_tap(self):
        assert detect_doc_type_from_filename("program.TAP") == "tap"
        assert detect_doc_type_from_filename("program.tap") == "tap"

    def test_nc(self):
        assert detect_doc_type_from_filename("cnc.nc") == "nc"
        assert detect_doc_type_from_filename("cnc.NC") == "nc"

    def test_dxf(self):
        assert detect_doc_type_from_filename("drawing.dxf") == "dxf"

    def test_unknown(self):
        assert detect_doc_type_from_filename("data.xlsx") == "unknown"
        assert detect_doc_type_from_filename("noextension") == "unknown"


class TestIsCodeFile:
    def test_tap_is_code(self):
        assert is_code_file("tap") is True

    def test_nc_is_code(self):
        assert is_code_file("nc") is True

    def test_pdf_not_code(self):
        assert is_code_file("pdf") is False


class TestIsSkipFile:
    def test_dxf_is_skip(self):
        assert is_skip_file("dxf") is True

    def test_unknown_is_skip(self):
        assert is_skip_file("unknown") is True

    def test_pdf_not_skip(self):
        assert is_skip_file("pdf") is False


class TestDetectPdfRoute:
    """detect_pdf_route 需要真實 PDF bytes，用最小合法 PDF 測試。"""

    def _make_minimal_pdf_with_text(self, text: str) -> bytes:
        """建立包含指定文字的最小 PDF（純文字型）。"""
        import io
        try:
            import reportlab.pdfgen.canvas as canvas
            buf = io.BytesIO()
            c = canvas.Canvas(buf)
            c.drawString(100, 750, text)
            c.save()
            return buf.getvalue()
        except ImportError:
            pytest.skip("reportlab 未安裝，跳過此測試")

    def test_empty_pdf_is_scanned(self):
        """無任何文字的 PDF 應判斷為掃描 PDF。"""
        # 最小空白 PDF
        minimal_pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer<</Size 4/Root 1 0 R>>
startxref
190
%%EOF"""
        result = detect_pdf_route(minimal_pdf)
        assert result == "scanned"

    def test_invalid_bytes_fallback_to_scanned(self):
        """pdfplumber 讀取失敗時，保守判斷為掃描 PDF（更新版決策 4）。"""
        result = detect_pdf_route(b"not a pdf at all")
        assert result == "scanned"
