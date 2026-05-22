"""
app/services/rules.py

company_rules DB 操作 + PromptBuilder。

DB 操作：
  get_latest_rules()  → 取最新版本（created_at DESC LIMIT 1）
  create_rules()      → INSERT 新版本，舊版本永不刪除
  get_rules_history() → 歷史版本清單（只回傳 metadata）

PromptBuilder：
  組裝順序（DOCX / PDF 共用前六段，第七段輸出規則各自不同）：
  1. 角色定義（固定）
  2. 公司資訊
  3. 術語對照（terminology_mapping）
  4. 文件理解提示（doc_type_hints）
  5. 通用切分規則（固定）
  6. 額外指令（extra_instructions）
  7. 輸出規則（DOCX → JSON array；PDF → wrapper JSON object）

Phase 4：_CHUNK_FIELDS 新增 face 欄位說明。
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company_rule import CompanyRule


# ── DB 操作 ───────────────────────────────────────────────────────────────────

async def get_latest_rules(
    db: AsyncSession,
    company_id: uuid.UUID,
) -> Optional[CompanyRule]:
    """取該公司最新版本的 rules（created_at DESC）。沒有設定回傳 None。"""
    result = await db.execute(
        select(CompanyRule)
        .where(CompanyRule.company_id == company_id)
        .order_by(CompanyRule.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_rules(
    db: AsyncSession,
    company_id: uuid.UUID,
    field_mapping: dict,
) -> CompanyRule:
    """
    INSERT 新版本 rules。
    每次都是新增一筆，舊版本永不刪除（供 chunk rule_version 追溯）。
    """
    rule = CompanyRule(
        rule_id=uuid.uuid4(),
        company_id=company_id,
        field_mapping=field_mapping,
        rule_version=generate_rule_version(),
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def get_rules_history(
    db: AsyncSession,
    company_id: uuid.UUID,
) -> list[CompanyRule]:
    """歷史版本清單，最新在前。"""
    result = await db.execute(
        select(CompanyRule)
        .where(CompanyRule.company_id == company_id)
        .order_by(CompanyRule.created_at.desc())
    )
    return list(result.scalars().all())


def generate_rule_version() -> str:
    """生成 rule_version，格式：v1-YYMMDD-HHMM。"""
    now = datetime.now(timezone.utc)
    return now.strftime("v1-%y%m%d-%H%M")


# ── PromptBuilder ─────────────────────────────────────────────────────────────

class PromptBuilder:
    """
    動態組裝 Gemini Flash system prompt。

    company_context 結構（從 tasks.py 傳入）：
    {
        "company_name": str,
        "industry": str,
        "rules": dict | None,   # CompanyRule.field_mapping，None 表示尚未設定
        "rule_version": str,
    }
    """

    @staticmethod
    def build_system_prompt(company_context: dict | None) -> str:
        """DOCX 路徑：輸出 JSON array。"""
        sections = [_ROLE_DEFINITION]

        if company_context:
            _add_company_info(sections, company_context)
            _add_dynamic_sections(sections, company_context.get("rules"))

        sections.append(_CHUNKING_RULES)
        sections.append(_DOCX_OUTPUT_RULES)
        sections.append(_CHUNK_FIELDS)
        sections.append(_EMBED_TEXT_RULES)
        sections.append(_DOCX_EXAMPLE)

        return "\n\n".join(sections)

    @staticmethod
    def build_pdf_system_prompt(company_context: dict | None) -> str:
        """PDF 路徑：輸出 wrapper JSON object（含 has_quality_issue）。"""
        sections = [_ROLE_DEFINITION_PDF]

        if company_context:
            _add_company_info(sections, company_context)
            _add_dynamic_sections(sections, company_context.get("rules"))

        sections.append(_PDF_CHUNKING_RULES)
        sections.append(_PDF_OUTPUT_RULES)
        sections.append(_CHUNK_FIELDS)
        sections.append(_EMBED_TEXT_RULES)

        return "\n\n".join(sections)


# ── 私有輔助函式 ──────────────────────────────────────────────────────────────

def _add_company_info(sections: list[str], company_context: dict) -> None:
    name = company_context.get("company_name", "")
    industry = company_context.get("industry", "")
    if not name:
        return
    lines = [f"## 公司資訊", f"- 公司名稱：{name}"]
    if industry:
        lines.append(f"- 產業類別：{industry}")
    sections.append("\n".join(lines))


def _add_dynamic_sections(sections: list[str], rules: dict | None) -> None:
    """將 rules 的動態區塊（術語對照、文件提示、額外指令）加入 sections。"""
    if not rules:
        return

    # 術語對照
    terminology: dict[str, str] = rules.get("terminology_mapping", {})
    if terminology:
        lines = ["## 術語對照（此公司特定術語 → 標準欄位）"]
        for term, field in terminology.items():
            lines.append(f"- 文件中的「{term}」對應到標準欄位 `{field}`")
        sections.append("\n".join(lines))

    # 文件理解提示
    hints: list[str] = rules.get("doc_type_hints", [])
    if hints:
        lines = ["## 文件理解提示"]
        lines.extend(f"- {h}" for h in hints)
        sections.append("\n".join(lines))

    # 額外切分指令
    extras: list[str] = rules.get("extra_instructions", [])
    if extras:
        lines = ["## 額外切分指令"]
        lines.extend(f"- {e}" for e in extras)
        sections.append("\n".join(lines))


# ── 固定 prompt 區塊 ──────────────────────────────────────────────────────────

_ROLE_DEFINITION = "你是一個工業知識結構化專家。你的任務是將生產文件轉換為標準化 JSON array，每個元素代表一個獨立知識單元。"

_ROLE_DEFINITION_PDF = "你是一個工業知識結構化專家。你的任務是直接閱讀 PDF 文件（包含掃描件、表格、圖文混排），並轉換為標準化 JSON 格式。"

_CHUNKING_RULES = """## 切分原則
- 每個獨立知識點切成一個 chunk
- 每個 chunk 必須能獨立回答一個問題
- 粒度依文件類型自行判斷"""

_PDF_CHUNKING_RULES = """## 切分原則
- 每個獨立知識點切成一個 chunk
- 每個 chunk 必須能獨立回答一個問題
- 粒度依文件類型自行判斷
- 表格中每一行或每一組設定參數可切成獨立 chunk"""

_DOCX_OUTPUT_RULES = """## 輸出規則
- **只輸出 JSON array，不要任何說明文字、markdown 符號或前綴**
- 所有欄位必須存在，無值填 null
- 不要輸出 chunk_id、doc_id、company_id、rule_version、created_at（後端補入）
- code_gcs_path 和 drawing_gcs_path 固定填 null"""

_PDF_OUTPUT_RULES = """\
## 輸出格式（嚴格遵守，只輸出此 JSON 物件，不要任何說明文字）
{
  "has_quality_issue": false,
  "quality_note": null,
  "chunks": []
}

欄位說明：
- has_quality_issue: 若文件有頁面模糊、文字不清晰、表格辨識不確定、關鍵數值無法確認等情況，設為 true
- quality_note: has_quality_issue 為 true 時，用繁體中文說明具體哪些頁面或內容有問題；否則填 null
- chunks: 標準 chunk array

## Chunk 輸出規則
- 所有欄位必須存在，無值填 null
- 不要輸出 chunk_id、doc_id、company_id、rule_version、created_at（後端補入）
- code_gcs_path 和 drawing_gcs_path 固定填 null"""

_CHUNK_FIELDS = """## Chunk 欄位說明
- product_name: 產品正式名稱
- product_id: 產品編號或料號
- material: 材料
- dimensions: 尺寸規格
- specs: 技術規格（JSON 字串格式）
- situation: 觸發此知識的情境或問題描述
- action: 處理方法或操作步驟
- reason: 原因說明或注意事項
- applies_to: 適用的產品或零件
- doc_type: 文件類型（pdf / docx / tap 等）
- case_id: 同案件多份文件串聯 ID
- face: 加工面向，如「第一面」、「第二面」，原始文件怎麼寫就怎麼填，無此資訊填 null
- embed_text: **最重要的欄位**"""

_EMBED_TEXT_RULES = """## embed_text 要求（務必遵守）
- 用繁體中文撰寫情境完整的自然語言描述
- 必須包含：產品背景 + 觸發情境 + 處理方式
- 不要直接拼接其他欄位
- 不能為空字串"""

_DOCX_EXAMPLE = """\
## 範例輸出格式
[
  {
    "product_name": "球閥",
    "product_id": "BV-001",
    "material": "不銹鋼 316L",
    "dimensions": "DN50",
    "specs": "{\\"pressure_rating\\": \\"150 PSI\\"}",
    "situation": "球閥在高溫環境下出現洩漏問題",
    "action": "檢查閥座密封圈，更換耐高溫 PTFE 材質",
    "reason": "標準 PTFE 密封圈使用溫度上限為 200°C，超溫會造成變形洩漏",
    "applies_to": "BV 系列球閥",
    "doc_type": "docx",
    "case_id": null,
    "face": null,
    "embed_text": "球閥 BV-001（DN50，不銹鋼 316L）在高溫環境下發生洩漏時，需檢查閥座密封圈是否因超溫變形，應更換耐高溫 PTFE 材質密封圈，標準 PTFE 使用溫度上限為 200°C。",
    "code_gcs_path": null,
    "drawing_gcs_path": null
  }
]"""
