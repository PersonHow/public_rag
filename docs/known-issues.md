# 已知問題與擴展性追蹤

最後更新：2026-10-01

這份文件記錄正式站 https://ai-agent.onceagain.tw 目前已知的問題、風險和待辦。處理完一項就把狀態改掉，不要刪除，保留脈絡。

狀態說明：`待執行`：方案已確定，等人動手 ／ `待規劃`：還沒決定做法 ／ `待部署`：程式已改好，還沒上線 ／ `已完成`

---

## 一、正式環境現況（2026-10-01 以 gcloud 唯讀查詢）

| 項目 | 設定 |
|---|---|
| 後端 Cloud Run `public-rag-backend` | 最多 20 個實例、每實例併發 80、1 vCPU / 512Mi |
| 文件處理 worker | `WORKER_BASE_URL` 指回後端自己，跟對話請求共用實例 |
| Cloud SQL `first-postgre-sql` | `db-g1-small`（共享 CPU、1.7GB），單一可用區，預設 `max_connections` 50 |
| 共用這台 DB 的服務 | `public-rag-backend`、`survey`、`dynamic-test` |
| Cloud Tasks `onceagain-rag-ingestion` | 同時 1000、每秒 500（GCP 預設值，等於沒有限流） |
| Qdrant VM `qdrant-normal-vm` | `e2-standard-2`（8GB），collection `chunks` 只有 395 個 point |
| Vertex AI | `gemini-2.5-flash`、`gemini-embedding-001`，`us-central1` |

---

## 二、擴展性與容量

### S1. Cloud Tasks 佇列沒有限流｜`待執行`｜高
- **問題**：一次批次上傳會讓所有解析任務同時打進後端，造成後端擴展、DB 連線被用完，Gemini 也會回 429。任務只重試 3 次，用完就會標成 failed。
- **影響**：所有租戶的登入和對話失敗，同一台 DB 上的 `survey`、`dynamic-test` 也會受影響。跟租戶數量無關，現在就可能發生。
- **方案**：
  ```bash
  gcloud tasks queues update onceagain-rag-ingestion --location asia-east1 \
    --max-concurrent-dispatches=5 --max-dispatches-per-second=2
  ```
  還原時把數值改回 `1000` / `500`。
- **取捨**：300 份文件會改成大約 15–30 分鐘逐步處理完。

### S2. 每個實例的 DB 連線數過多｜`待執行`（repo 預設值已改）｜高
- **問題**：每個實例最多 20 條連線，20 個實例就是 400 條，但 DB 上限只有 50。
- **已完成**：`app/core/config.py`、`.env.example`、`README.md` 的預設值已從 5／20 改成 2／5。
- **待執行**：正式環境有明確設定這兩個環境變數，要另外更新：
  ```bash
  gcloud run services update public-rag-backend --region asia-east1 \
    --update-env-vars DB_POOL_SIZE_MIN=2,DB_POOL_SIZE_MAX=5
  ```
  一定要用 `--update-env-vars`，用 `--set-env-vars` 會清空其他環境變數。
- **注意**：
  - 最壞情況是 20 × 5 = 100 條，還是超過 50。要完全保證不超過，就把最大實例數降到 8 左右，或是升級 Cloud SQL（S3）。
  - 對話時，連線會一直佔到 Gemini 回答完，所以每個實例同時只能服務 5 個對話。

### S3. Cloud SQL 規格太小、又跟其他服務共用｜`待規劃`｜高（接正式付費租戶前）
- **問題**：
  - `db-g1-small` 是共享 CPU，沒有 SLA，連線上限 50，而且是單一可用區。
  - 跟 `survey`、`dynamic-test` 共用同一台，任何一個服務出問題都會互相拖累。
- **方案**：
  - 升級到有專屬 CPU 的規格，例如 1 vCPU / 3.75GB，連線上限 100。
  - 評估要不要把 `rag_db` 獨立到自己的 instance。
  - 升級需要短暫停機，費用也會增加，要先決定。
- **剩下的擴展性問題，大多都是這一項造成的。**

### S4. worker 跟對話共用後端服務｜`待規劃`｜中
- **問題**：文件解析和使用者對話搶同一批實例和連線池。
- **方案**：把 worker 拆成獨立的 Cloud Run 服務，設定較低的最大實例數，跟對話服務分開擴展。

### S5. 沒有依租戶公平排隊或限流｜`待規劃`｜中
- **問題**：所有租戶共用 Vertex AI 配額和同一條佇列，先進先出。A 家上傳 300 份時，B 家上傳 1 份也要排在後面；A 家大量使用時，B 家的對話也可能收到 429。
- **方案**：依 `company_id` 限制同時處理的文件數，上傳和對話分開計算。

### S6. 後台列表沒有分頁｜`待規劃`｜中（大約 10–20 家租戶後）
- **問題**：
  - `GET /sessions` 寫死 `limit(100)`，全局視角看不到較舊的資料。
  - `GET /users`、`GET /companies` 一次全部載入。
  - 頂部 TENANT 下拉選單不能搜尋。
- **方案**：後端加上 `limit/offset` 或 cursor，前端加分頁和選單搜尋。

### S7. 沒有統計各租戶的用量｜`待規劃`｜低（要收費時）
- **問題**：沒有記錄各租戶的 token 用量和文件數，無法計費，也抓不到濫用。

### S8. Qdrant 容量｜`暫不處理`
- 原始向量和 INT8 量化向量都放在 RAM，每 100 萬個 chunk 約需 4GB。目前只有 395 個 point，離上限還非常遠。
- 租戶很多時，可以把 `company_id` 的 payload index 設成 `is_tenant=True`。

### S9. 後端記憶體 512Mi｜`待確認`｜低
- 每個實例併發 80，同時還在處理 PDF 解析，批次上傳時可能記憶體不足（OOM）。S1 限流後風險會降低。可以到 Cloud Run 的監控查記憶體峰值確認。

---

## 三、帳號與資安

### A1. 超級管理員還是測試帳號 `admin@test.com`｜`待執行`｜高
- **步驟**：
  1. 用 `admin@test.com` 登入「使用者」頁，新增正式的 superadmin。建議用公司共用信箱，密碼要符合新規則。
  2. 用新帳號登入，確認可以正常使用。
  3. 用新帳號停用 `admin@test.com`。
- 建議至少保留兩個正式 superadmin，避免唯一的帳號被鎖住。
- 新的密碼規則（B1）上線後，新帳號的密碼必須符合規則。

### A2. 沒有重新啟用帳號、修改密碼的功能｜`待規劃`｜中
- 停用帳號後無法從介面恢復。密碼外洩或忘記時，只能另外建一個新帳號。

### A3. 資料庫密碼可能已外洩｜`待執行`｜高
- 2026-10-01 排查時，本機 `.env` 的 `DATABASE_URL` 密碼有一部分出現在對話紀錄裡。
- 這台 Cloud SQL 是公開 IP，有 4 組允許連線的 IP，建議換掉密碼，並同步更新 Cloud Run 的 `DATABASE_URL` 和本機 `.env`。

### A4. 本機 `.env` 直接指向正式資料庫｜`待規劃`｜中
- 照 README 在本機啟動後端，會直接讀寫正式的 `rag_db`。在本機測試建帳號或刪資料，都會影響正式站。
- **安全的本機做法**：另外起一個本機 Postgres，用環境變數覆蓋 `DATABASE_URL`，再跑 `alembic upgrade head`。Qdrant 指向連不到的位址，後端在 development 模式下只會印警告，照常啟動。
- **建議**：把本機 Postgres 加進 `docker-compose.yaml`，讓 `.env` 預設指向本機。

---

## 四、程式品質

### Q1. `tests/test_login_log.py` 有 4 個測試失敗｜`待規劃`｜低
- 測試的 mock 缺少 `.one()`（錯誤發生在 `app/services/auth.py:108`）。改動前就會失敗，跟 2026-10-01 的修改無關。

### Q2. 有兩種 icon 做法並存｜`待規劃`｜低
- `package.json` 裝了 `lucide-angular`，但程式碼都沒用到。目前的 icon（登出、密碼切換）都是 inline SVG。
- 應該二選一：icon 很少就移除這個套件；之後 icon 會變多，就全部改用 lucide-angular。

---

## 五、已完成，待部署（2026-10-01）

| 項目 | 主要檔案 |
|---|---|
| 新增使用者的密碼強度規則：12 碼以上，含大小寫英文、數字、符號，前後端都檢查 | `app/schemas/user.py`、`tests/test_user_password.py` |
| 新增使用者改成彈出視窗，角色改用分段按鈕，選 superadmin 時隱藏 Company ID | `web/.../admin/users/` |
| 密碼欄的眼睛 icon 顯示／隱藏切換（共用元件） | `web/.../shared/components/password-toggle/` |
| 登入頁移除四個角落的裝飾文字，加上密碼切換 | `web/.../auth/login/` |
| Sessions 管理依租戶分組，切換 TENANT 時自動重新載入 | `app/routers/sessions.py`、`web/.../admin/sessions/` |
| 斜紋 loading 動畫 | `web/src/styles/_global.scss`、`web/.../shared/components/empty-state/` |
| 連線池預設值改成 2／5 | `app/core/config.py`、`.env.example`、`README.md` |
