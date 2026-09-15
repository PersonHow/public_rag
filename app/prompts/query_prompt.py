"""
app/prompts/query_prompt.py

RAG 查詢相關 prompt 常數與組裝函式。

SYSTEM_PROMPT  — Gemini 角色設定與回答格式規範
build_rag_prompt — 組裝含 filename 的 user prompt
"""

# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
你是一位工業生產知識助理，擅長解讀建議工法、品質標準與工序規範。

根據提供的知識片段，用條列式回答操作員的問題。

理解問題時：
- 操作員的問法可能與知識片段的用詞不同，但描述的是同一個加工情境（例如問「法蘭太厚怎麼處理」，片段可能以「端距與法蘭厚度無法兼顧」「端距過長/過短」描述同一件事）。請先判斷片段是否與問題相關，只要相關就直接依片段內容回答，不要因為「用詞不完全對應」就拒答。
- 片段中已明確記載的情境、處理方式、數值，都視為「資料中有」，可直接引用作答。
- 操作員問句描述的方向（例如太厚/太薄、過長/過短、過大/過小）往往只是成對情境的其中一種。只要片段裡有同一產品或主題下成對、並列的情境（過長與過短、正面與背面、外銷與國內等），請務必把整組都列出，讓操作員自行對照，不要因為問句只提到一個方向就省略另一個方向。

回答格式規範：
- 開頭使用【建議工法】、【品質標準】或其他適合的區塊標題
- 每個要點以「- 」開頭
- 技術數值保留原始單位
- 不要捏造片段中沒有的數值或步驟
- 只有在所有片段都與問題無關、完全找不到可依據的內容時，才回答「資料中未找到相關資訊」
- 禁止自行生成【來源】區塊；來源資訊由系統另行處理，不需要也不應該出現在你的回答中\
"""


# ── User Prompt 組裝 ──────────────────────────────────────────────────────────

def build_rag_prompt(
    question: str,
    chunks: list[dict],
    doc_id_to_filename: dict[str, str],
) -> str:
    """
    組裝 RAG user prompt。

    Args:
        question:            使用者問題
        chunks:              Qdrant search 回傳結果（含 payload）
        doc_id_to_filename:  doc_id → filename 對照表（由 query endpoint 批次查 SQL 後傳入）
    """
    context_parts: list[str] = []

    for i, chunk in enumerate(chunks, 1):
        p = chunk["payload"]
        doc_id = p.get("doc_id", "")
        filename = doc_id_to_filename.get(doc_id, "未知文件")

        lines = [f"【片段 {i}｜{filename}（相關度 {chunk['score']:.2f}）】"]

        if p.get("product_name"):
            lines.append(f"產品：{p['product_name']}")
        if p.get("product_id"):
            lines.append(f"料號：{p['product_id']}")
        if p.get("face"):
            lines.append(f"加工面：{p['face']}")
        if p.get("situation"):
            lines.append(f"情境：{p['situation']}")
        if p.get("action"):
            lines.append(f"處理方式：{p['action']}")
        if p.get("specs"):
            lines.append(f"規格：{p['specs']}")
        if p.get("reason"):
            lines.append(f"說明：{p['reason']}")

        lines.append(f"內容：{p.get('embed_text', '')}")
        context_parts.append("\n".join(lines))

    context = "\n\n".join(context_parts)
    return f"以下是相關知識片段：\n\n{context}\n\n問題：{question}"
