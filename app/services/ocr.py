"""
app/services/ocr.py

⚠ 此模組已退役。

Document AI OCR 已被 Gemini Flash PDF 直讀取代。
理由：
  1. Gemini 視覺理解直接讀 PDF 原始影像，語意品質優於 OCR 文字提取
  2. 加密/只讀 PDF 在 Gemini 視覺層完全透明，無分流問題
  3. 省去 async 輪詢（最多 30 次 × 10 秒）這個最脆弱的 pipeline 環節
  4. 費用與 Document AI OCR 相當，比 Layout Parser 便宜

如需重新啟用（例如 v2 特定場景），請從 git history 恢復此檔案。
"""

raise ImportError(
    "ocr.py 已退役，請改用 gemini.convert_pdf_to_chunks()。"
    "詳見 app/services/gemini.py。"
)
