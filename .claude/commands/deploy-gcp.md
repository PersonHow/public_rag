部署 FastAPI 後端（+ 可選前端）到 GCP Cloud Run，並自動確認所有前置條件。

在開始任何操作前，先詢問使用者以下參數（沒有預設值的必填，有預設值的可直接 Enter 略過）：

## 必填參數

1. **GCP Project ID** — 例如 `shaped-totem-468106-g3`
2. **Region** — 例如 `asia-east1`（預設 `asia-east1`）
3. **後端 Cloud Run 服務名稱** — 例如 `public-rag-backend`
4. **後端 Service Account email** — 若留空則使用 Cloud Run 預設的 Compute SA

## 選填模組（詢問是否需要，需要才繼續）

### Cloud Tasks
- 是否使用 Cloud Tasks？（y/n）
- Queue 名稱 — 例如 `onceagain-rag-ingestion`
- max-attempts（預設 3）
- WORKER_BASE_URL — 後端對外 URL，例如 `https://xxx.run.app`
- INTERNAL_TOKEN — 任意固定字串

### 前端
- 是否有前端服務？（y/n）
- 前端 Cloud Run 服務名稱
- 前端原始碼路徑（預設 `web`）
- 前端 build 指令（預設 `ng build --configuration production`）

### Cloud SQL
- 是否連接 Cloud SQL？（y/n）
- Cloud SQL instance connection name — 例如 `project:region:instance`
- DATABASE_URL

### Qdrant
- 是否使用 Qdrant？（y/n）
- Qdrant VM IP
- Qdrant gRPC port（預設 6334）
- Qdrant API Key（可留空）
- Collection name（預設 `public_rag_chunks`）

---

收集完所有參數後，依序執行以下步驟，每個步驟執行前先告知使用者正在做什麼，執行後顯示結果：

## Step 1：確認 gcloud 登入與專案

```bash
gcloud auth list
gcloud config get-value project
```

若目前專案不符，執行：
```bash
gcloud config set project {PROJECT_ID}
```

## Step 2：確認並建立 Service Account（若使用者有指定）

```bash
gcloud iam service-accounts describe {SERVICE_ACCOUNT_EMAIL}
```

若不存在，詢問是否建立，並根據勾選的模組自動加上對應角色：

| 模組 | 需要的角色 |
|---|---|
| Cloud Tasks | `roles/cloudtasks.enqueuer` |
| GCS 上傳 | `roles/storage.objectAdmin` |
| Cloud SQL | `roles/cloudsql.client` |
| Gemini / Vertex AI | `roles/aiplatform.user` |
| Cloud Run 自我呼叫 | `roles/run.invoker` |

## Step 3：確認並建立 Cloud Tasks 佇列（若啟用）

```bash
gcloud tasks queues describe {QUEUE_NAME} --location={REGION}
```

若不存在，詢問是否建立：
```bash
gcloud tasks queues create {QUEUE_NAME} \
  --location={REGION} \
  --max-attempts={MAX_ATTEMPTS} \
  --min-backoff=10s \
  --max-backoff=300s
```

## Step 4：部署後端

```bash
gcloud run deploy {BACKEND_SERVICE} \
  --source . \
  --region {REGION} \
  --service-account={SERVICE_ACCOUNT_EMAIL}
```

若未指定 Service Account，省略 `--service-account` 參數。

部署成功後顯示服務 URL。

## Step 5：部署前端（若啟用）

```bash
cd {FRONTEND_PATH}
{FRONTEND_BUILD_CMD}
cd ..

gcloud run deploy {FRONTEND_SERVICE} \
  --source {FRONTEND_PATH} \
  --region {REGION}
```

## Step 6：部署後驗證

### 後端 health check
```bash
curl {BACKEND_URL}/health
```

### Cloud Tasks 狀態（若啟用）
```bash
gcloud tasks queues describe {QUEUE_NAME} --location={REGION}
```
確認 `state: RUNNING`

### 查看最近 logs
```bash
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name={BACKEND_SERVICE}" \
  --limit=20 \
  --format="table(timestamp,textPayload)"
```

---

## 常見問題排查（部署失敗時主動提示）

| 症狀 | 可能原因 | 建議動作 |
|---|---|---|
| Cloud Tasks 排程失敗 | 佇列不存在或 SA 無權限 | 檢查 Step 2-3，確認 `cloudtasks.enqueuer` |
| 上傳後卡在解析中 | Gemini API 無法呼叫 | 確認 SA 有 `aiplatform.user` |
| confirm 後卡在 confirmed | Cloud Tasks 無法送達 | 查 log `ingest-chunks Cloud Tasks 3 次全部失敗`，BackgroundTask 應已接手 |
| GCS 上傳 500 | SA 無 GCS 權限 | 確認 SA 有 `storage.objectAdmin` |
| DB 連線失敗 | Cloud SQL 未授權 | 確認 SA 有 `cloudsql.client`，DATABASE_URL 格式正確 |
