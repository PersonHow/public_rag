# HANDOVER — v2 Inline 編輯 + 公司規則設定頁

> 接手對話請先讀完本文件再動手。  
> 分支：`v2-Phase1`　  撰寫時間：2026-06-01

---

## 1. 任務目標

讓使用者在「**preview 階段**」可以直接修正 Gemini 解析錯誤的 chunk，並提供 admin 一個介面手動維護 `company_rules`（術語對照、文件提示、額外指令）。

主要 user story：
- 「我看到 chunk 把『閥體編號』歸到錯誤欄位，希望當下就能修。」
- 「我想新增 / 修改公司規則，下次上傳時 Gemini 就用新規則切。」
- 預覽頁要有一條提示「發現問題？→ 更新公司規則」引導 admin 過去設定。

---

## 2. 現況診斷（為什麼要做）

**`company_rules` 只有一筆的根因：前端從來沒有更新 rules 的 UI。**

驗證軌跡：
- 後端 [app/routers/rules.py](app/routers/rules.py) 三支 API 完整且 router 已掛載 ([app/main.py:84](app/main.py#L84))。
- [app/services/rules.py:49-67](app/services/rules.py#L49-L67) `create_rules()` 是 INSERT-only（每次 POST 產生新 rule_version，舊版本永不刪），機制本身正確。
- 上傳流程 ([app/routers/internal/tasks.py:444-461](app/routers/internal/tasks.py#L444-L461)) 只呼叫 `get_latest_rules()`，**不會** INSERT。
- 全前端 (`web/src/`) 搜尋 `/rules`、`companyRules`、`terminology_mapping` → 0 命中。`admin.service.ts` 只有 Users / Companies。
- 結論：rules 目前只能用 Swagger / curl 手動建，所以只有第一筆。

---

## 3. 設計決策（先讀懂這幾條再開工）

### 3-1. inline 編輯只開放在「confirm 前」（status = `pending_preview`）

這是核心簡化決策。時序如下：

```
upload → Gemini parse → chunks 進 PostgreSQL (status=pending_preview)
                              │
                       ★ preview 編輯就在這裡（Qdrant 還沒有任何東西）
                              │
                       使用者按確認
                              │
                       Cloud Task: ingest-chunks (Phase 4)
                              │
                       這時才 embed_texts() + Qdrant upsert
```

因為 [app/routers/sessions.py confirm_session](app/routers/sessions.py) 是按了確認**才**派 ingest-chunks，所以 preview 階段去 PATCH chunk 欄位**完全不用碰 Qdrant、也不需重新 embed**。

### 3-2. DB schema 幾乎不用動

- `chunks` 表已有所有可編輯欄位 ([app/models/chunk.py](app/models/chunk.py))，且大部分 nullable。
- `company_rules` 是 JSONB 整包存 ([app/models/company_rule.py:31](app/models/company_rule.py#L31))，新增規則就是 POST 新一筆，舊版本不刪 → 結構本來就支援。
- **不要寫 alembic migration**。如果之後想加 `chunks.updated_at` 給稽核，是 v3 的範圍。

### 3-3. `company_rules` 不自動連動 chunk 編輯

理由：自動推斷哪條 rule 該改容易誤判，反而污染規則庫。設計上：
- 編輯 chunk → 只改該 chunk
- 改 rules → 只影響「未來上傳的文件」
- 舊 chunks 想用新規則切 → 是「重新上傳該文件」這條獨立路徑（不在本次 scope）

`chunks.rule_version` ([app/models/chunk.py:39](app/models/chunk.py#L39)) 是刻意設計的可追溯欄位，**不要動它**。

### 3-4. Qdrant 不需要重做、也不要清

preview 階段編輯完全不影響 Qdrant。已 confirmed 的舊 session 也不受任何影響。

---

## 4. 實作 Scope（按順序）

### Step 1：後端 `PATCH /sessions/{session_id}/chunks/{chunk_id}`

**位置建議**：放在 [app/routers/sessions.py](app/routers/sessions.py)（與 `get_session_chunks`、`confirm_session` 同檔），或拆到 [app/routers/preview.py](app/routers/preview.py)（已存在）也可。

**規格**：

- Method: `PATCH`
- Path: `/sessions/{session_id}/chunks/{chunk_id}`
- Auth: JWT，權限同 `confirm_session`（superadmin / company_admin 限自家公司 / field_user 拒絕）—— 可以共用 [sessions.py:_confirm_allowed](app/routers/sessions.py)
- **前置檢查（重要）**：
  - session 必須存在
  - `session.status == "pending_preview"` —— 其他狀態（uploading / processing / confirmed / failed / rejected）一律 409 Conflict，訊息「僅能在預覽階段編輯 chunk」
  - chunk 必須屬於該 session（透過 `doc_id` 反查）
  - chunk 的 `company_id` 必須等於使用者的 `company_id`（superadmin 例外）
- **允許編輯的欄位**（其他一律拒）：
  ```
  product_name, product_id, material, dimensions, specs,
  situation, action, reason, applies_to, case_id, doc_type,
  face, embed_text
  ```
- **禁止編輯**：`chunk_id`, `doc_id`, `company_id`, `rule_version`, `created_at`, `chunk_index`, `code_gcs_path`, `drawing_gcs_path`
- **驗證**：
  - `embed_text` 若有給，不可為空字串、不可超過 Text 上限
  - 其他欄位若給空字串視為 `null`
- **回傳**：更新後完整的 chunk 物件（同 `get_session_chunks` 內單個 chunk 的 shape）

**Schema 新增位置**：[app/schemas/upload.py](app/schemas/upload.py) 或新開 [app/schemas/chunk.py](app/schemas/chunk.py)。建議用 `ChunkPatch(BaseModel)` 所有欄位都 `Optional`，配合 `model_dump(exclude_unset=True)` 只更新有給的欄位。

**Acceptance**：
- [ ] curl 對 pending_preview 的 chunk PATCH 成功，回傳更新後物件
- [ ] curl 對 confirmed 的 chunk PATCH 回 409
- [ ] field_user PATCH 回 403
- [ ] 嘗試改 `rule_version` 被 422 拒絕（或 silently ignore，看實作風格選一個）
- [ ] DB 中 chunk 真的更新了

---

### Step 2：前端 preview inline 編輯

**關鍵檔案**：
- 主元件：[web/src/app/features/preview/preview.component.ts](web/src/app/features/preview/preview.component.ts)
- 卡片元件：`web/src/app/features/preview/components/` 下（看實際 chunk 卡片 component）
- Service：[web/src/app/core/services/preview.service.ts](web/src/app/core/services/preview.service.ts)
- Model：[web/src/app/shared/models/](web/src/app/shared/models/)（看 chunk / session 既有 type）

**UX 規格**：
- 卡片上的可編輯欄位（先做：`product_name`, `material`, `dimensions`, `situation`, `action`, `reason`, `embed_text`）顯示為文字
- 點欄位 → 變成 input / textarea
- blur 或按「儲存」→ 呼叫 `PATCH /sessions/{id}/chunks/{chunk_id}`，body 只帶有改的欄位
- 成功：toast 「已更新」+ 本地 signal 替換掉該 chunk
- 失敗：toast 顯示錯誤、欄位回復原值
- **只有 session.status === 'pending_preview' 時才可編輯**，confirmed / processing 顯示唯讀

**Service 端**：在 `preview.service.ts` 加 `patchChunk(sessionId, chunkId, patch)`，回傳 `Promise<Chunk>` 或 Observable，內部呼叫 `http.patch`。

**Acceptance**：
- [ ] 點 `product_name` 變成可編輯 input
- [ ] 改完按 enter 或失焦觸發 PATCH，UI 顯示新值
- [ ] 改 `embed_text` 也能更新（用 textarea）
- [ ] 已 confirm 的 session 進到 preview 頁時，欄位是純文字，無法編輯
- [ ] 錯誤狀況有 toast 提示

---

### Step 3：Admin 公司規則設定頁

**新路由**：`/admin/rules`（在 `app.routes.ts` 加，受 `role.guard`，限 `superadmin` / `company_admin`）

**Service**：在 [web/src/app/core/services/admin.service.ts](web/src/app/core/services/admin.service.ts) 加三個方法：

```ts
getCompanyRules(companyId: string): Promise<CompanyRulesResponse | null>;
// 404 要 catch 起來轉成 null（代表還沒設定，回空表單）

createCompanyRules(companyId: string, body: CompanyRulesCreate): Promise<CompanyRulesResponse>;

getCompanyRulesHistory(companyId: string): Promise<CompanyRulesHistoryItem[]>;
```

對應後端 schema（已存在）：[app/schemas/rules.py](app/schemas/rules.py)

```ts
interface CompanyRulesCreate {
  terminology_mapping: Record<string, string>;
  doc_type_hints: string[];
  field_exclusions: string[];
  extra_instructions: string[];
}
```

**頁面結構**：
- 上方：公司選擇器（superadmin 才顯示；company_admin 鎖死成自家公司）
- 中間：四個區塊
  - **術語對照（terminology_mapping）**：key-value 動態列表（左：公司術語 / 右：標準欄位下拉選單）
    - 標準欄位下拉選項必須是這 11 個：`product_name, product_id, material, dimensions, specs, situation, action, reason, applies_to, case_id, doc_type`（[app/schemas/rules.py:13-16](app/schemas/rules.py#L13-L16)）
  - **文件理解提示（doc_type_hints）**：可新增 / 刪除的字串陣列
  - **欄位排除（field_exclusions）**：可新增 / 刪除的字串陣列
  - **額外指令（extra_instructions）**：可新增 / 刪除的 textarea 陣列
- 下方：
  - 「儲存（產生新版本）」按鈕 → POST，成功 toast 顯示 `rule_version`
  - 「歷史版本」摺疊區 → GET history，列 `rule_version` + `created_at`

**載入時行為**：
- 先 GET latest，有 → 預填表單
- 404 → 表單空白，提示「此公司尚未設定規則，將使用通用 prompt」

**Acceptance**：
- [ ] superadmin 可以選任何公司、編輯、儲存
- [ ] company_admin 進來只能看到自己公司
- [ ] 儲存後 DB `company_rules` 真的多一筆，`rule_version` 不同
- [ ] 重新進頁面，看到剛存的內容
- [ ] 上傳新文件，session 的 `rule_version_used` 對應到剛存的版本
- [ ] 術語對照填了非法欄位（例如 `xxx`）會被後端 422 擋，前端要顯示錯誤訊息

---

### Step 4：preview 頁加「更新公司規則」快捷入口

純導向連結，**不做任何自動推斷**。

- 位置：preview 頁面標頭區（或側欄底部），顯示 superadmin / company_admin 才看得到
- 文案範例：「發現分類錯誤？→ [更新公司規則](/admin/rules)」
- 點下去就 `router.navigate(['/admin/rules'])`

**Acceptance**：
- [ ] field_user 看不到此連結
- [ ] 點擊正確導向 admin rules 頁

---

## 5. 不要動的東西（紅線）

| 項目 | 為什麼 |
|------|--------|
| Alembic migration | 本次完全不需要改 schema |
| Qdrant collection / 既有向量 | preview 編輯不影響 Qdrant；舊 confirmed session 不受影響 |
| `chunks.rule_version` 欄位 / 語意 | 是刻意設計的可追溯欄位 |
| `company_rules` INSERT-only 機制 | 不要改成 UPDATE，舊版本保留是設計需求 |
| `_build_company_context()` 邏輯 | 上傳路徑不要塞 INSERT，職責分離 |
| 上傳 / 確認 / Cloud Tasks 流程 | 本次只動 preview 期間 PATCH，不碰 ingest 路徑 |

---

## 6. 既有可直接複用的東西

| 用途 | 位置 |
|------|------|
| chunk 既有讀取 endpoint（response shape 參考） | [app/routers/sessions.py get_session_chunks](app/routers/sessions.py) |
| 權限檢查模板 | [app/routers/rules.py:32-40 _check_company_access](app/routers/rules.py#L32-L40) |
| 公司清單 API（給 superadmin 選擇器） | [admin.service.ts getCompanies](web/src/app/core/services/admin.service.ts) |
| Pydantic rules schema | [app/schemas/rules.py](app/schemas/rules.py)（不用改） |
| Qdrant `set_payload` / `delete_chunks_by_ids`（**v3 才會用到，本次別碰**） | [app/services/ai/qdrant_service.py](app/services/ai/qdrant_service.py) |

---

## 7. 驗收完整流程（一次跑完證明 v2 通了）

1. 用 superadmin 登入。
2. 進 `/admin/rules`，選一家公司，填：
   - terminology_mapping: `{"閥體編號": "product_id"}`
   - extra_instructions: `["embed_text 必須包含案件編號"]`
   - 儲存 → 拿到新 `rule_version`，例如 `v1-260601-1430`
3. 切到該公司的帳號（或 superadmin 代上傳），上傳一份測試文件。
4. 等到 preview 頁開出來，確認 chunk 卡片右上某處顯示 `rule_version = v1-260601-1430`。
5. 在預覽頁挑一個 chunk，把 `product_name` 改成正確的值，blur 觸發 PATCH，UI 立刻更新。
6. 重新整理 preview 頁，看到改完的值仍在（DB 真的有寫入）。
7. 點「確認」→ Phase 4 ingest-chunks 派送 → Qdrant 收到的是修正後的 embed_text + payload。
8. 切回 `/admin/rules`，看歷史版本至少有 2 筆（剛存的 + 之前可能有的）。
9. 確認 chat 查詢能命中剛上傳的 chunk。

---

## 8. 目前未提交的本地變更（接手前先處理）

`git status` 顯示這些檔案有未提交修改（與本任務無關，但會干擾）：

```
M app/models/session.py            ← company_id String→UUID + FK
M app/routers/sessions.py          ← confirm 加入 Cloud Tasks retry + BackgroundTask fallback
M app/routers/upload.py
M web/src/app/core/services/preview.service.ts
M web/src/app/features/preview/preview.component.ts
```

接手對話請：
1. 先跟使用者確認這些變更要不要先 commit 或 stash
2. **特別注意 `app/models/session.py`** 把 `company_id` 從 `String(100)` 改成 `UUID + FK`，這需要一支 alembic migration 才能上線。若 DB 還沒套用此變更，本地測試會 schema 不一致
3. 確認過再開始 Step 1

---

## 9. 範圍外（如果使用者問起，提醒是 v3）

- confirm 後仍可編輯 chunk（要碰 Qdrant `set_payload` / 重新 embed）
- 「以新 rules 重新切舊文件」的 re-ingest 按鈕
- 自動從 chunk 編輯推斷要修哪條 rule
- chunk 編輯稽核（誰改的、何時改的）

這些不要主動加進來，先把 v2 四步做完。
