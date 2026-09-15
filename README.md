# 多租戶 RAG 生產助理系統

工業生產知識管理平台。操作員可上傳加工文件（PDF / DOCX），系統自動解析、向量化後，提供自然語言查詢介面，即時回答加工參數、品質標準、工序規範等問題。

---

## 目錄

- [系統架構](#系統架構)
- [技術棧](#技術棧)
- [專案目錄結構](#專案目錄結構)
- [GCP 專案說明](#gcp-專案說明)
- [本機開發環境建立](#本機開發環境建立)
- [環境變數說明](#環境變數說明)
- [資料庫遷移](#資料庫遷移)
- [API 端點總覽](#api-端點總覽)
- [文件處理流程](#文件處理流程)
- [多租戶與角色設計](#多租戶與角色設計)
- [GCP 雲端部署](#gcp-雲端部署)

---

## 系統架構

```
使用者（瀏覽器）
      │
      ▼
┌─────────────┐       ┌──────────────────────────────┐
│  Angular 前端 │──────▶│  FastAPI 後端 (Cloud Run)     │
│  (Cloud Run) │       │                              │
└─────────────┘       │  ┌──────────────────────────┐│
                      │  │ POST /upload              ││
                      │  │ POST /query               ││
                      │  │ POST /auth/login          ││
                      │  └──────────────────────────┘│
                      └──────────┬───────────────────┘
                                 │
              ┌──────────────────┼──────────────────────┐
              │                  │                      │
              ▼                  ▼                      ▼
     ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐
     │  Cloud SQL   │  │  Cloud Storage   │  │  Cloud Tasks     │
     │ (PostgreSQL) │  │  (文件儲存)       │  │  (非同步處理)     │
     └──────────────┘  └──────────────────┘  └────────┬─────────┘
                                                       │
                                          ┌────────────┼───────────┐
                                          ▼            ▼           ▼
                                   ┌──────────┐ ┌──────────┐ ┌─────────┐
                                   │  Gemini  │ │ Vertex AI│ │ Qdrant  │
                                   │  Flash   │ │ Embedding│ │ (向量庫) │
                                   └──────────┘ └──────────┘ └─────────┘
```

### 文件處理流程

```
上傳 PDF/DOCX
     │
     ▼
GCS 儲存（raw/）
     │
     ▼
Cloud Tasks：process-document
     │
     ├── PDF  → Gemini Flash 視覺解析
     └── DOCX → 文字提取解析
     │
     ▼
結構化 Chunks 存入 Cloud SQL
     │
     ▼
Cloud Tasks：ingest-chunks
     │
     ▼
Vertex AI Embedding → Qdrant Upsert
     │
     ▼
Session 狀態 → done
```

---

## 技術棧

| 層級 | 技術 |
|------|------|
| 前端 | Angular 18、NgRx Signal Store、nginx |
| 後端 | Python 3.12、FastAPI 0.115、SQLAlchemy 2.0（async） |
| 資料庫 | PostgreSQL 15（Cloud SQL） |
| 向量庫 | Qdrant |
| AI 模型 | Gemini 2.5 Flash（文件解析）、gemini-embedding-001（向量化） |
| 雲端儲存 | Google Cloud Storage |
| 非同步任務 | Google Cloud Tasks |
| 容器化 | Docker、docker-compose |
| 部署 | Google Cloud Run（前後端分開服務） |

---

## 專案目錄結構

```
Skvalves_Demo/
│
├── Dockerfile                  # 後端 Docker image 定義
├── docker-compose.yaml         # 本機一鍵啟動（後端 + 前端）
├── requirements.txt            # Python 依賴
├── pyproject.toml              # pytest / ruff 設定
├── alembic.ini                 # 資料庫遷移工具設定
├── .env                        # 本機環境變數（不入 git）
│
├── app/                        # FastAPI 應用主體
│   ├── main.py                 # 應用入口，掛載 middleware / router
│   │
│   ├── core/                   # 核心設定與共用工具
│   │   ├── config.py           # 所有環境變數集中定義（pydantic-settings）
│   │   ├── database.py         # async SQLAlchemy engine + session factory
│   │   ├── dependencies.py     # FastAPI dependency：JWT 驗證、RBAC、company_id 解析
│   │   └── logging.py          # JSON 格式化 logging 設定
│   │
│   ├── models/                 # SQLAlchemy ORM 模型（對應資料庫表）
│   │   ├── user.py             # users 表：帳號、角色（superadmin/company_admin/field_user）
│   │   ├── company.py          # companies 表：多租戶公司資料
│   │   ├── session.py          # ingestion_sessions 表：文件上傳批次的狀態機
│   │   ├── document.py         # documents 表：單一上傳文件 + GCS 路徑
│   │   ├── chunk.py            # chunks 表：Gemini 解析後的知識片段（含向量化索引）
│   │   ├── company_rule.py     # company_rules 表：公司客製化解析規則（版本管理）
│   │   └── product.py          # products 表：公司產品目錄（canonical name + aliases）
│   │
│   ├── schemas/                # Pydantic 資料驗證 Schema（request / response）
│   │   ├── auth.py             # LoginRequest、TokenResponse、CurrentUser
│   │   ├── user.py             # UserCreate、UserResponse
│   │   ├── company.py          # CompanyCreate、CompanyResponse
│   │   ├── upload.py           # UploadResponse、SessionStatus
│   │   ├── query.py            # QueryRequest、QueryResponse、SourceItem
│   │   ├── rules.py            # CompanyRulesCreate、CompanyRulesResponse
│   │   └── chunk.py            # ChunkResponse
│   │
│   ├── routers/                # FastAPI 路由
│   │   ├── health.py           # GET /health、GET /ready（健康檢查）
│   │   ├── auth.py             # POST /auth/login
│   │   ├── upload.py           # POST /upload
│   │   ├── sessions.py         # GET/POST /sessions（文件批次管理）
│   │   ├── query.py            # POST /query（RAG 查詢）
│   │   ├── preview.py          # GET /sessions/{id}/documents/{id}/full-text
│   │   ├── rules.py            # GET/POST /companies/{id}/rules
│   │   ├── stats.py            # GET /dashboard/stats
│   │   ├── admin/              # 管理員路由
│   │   │   ├── companies.py    # CRUD /companies（superadmin）
│   │   │   ├── users.py        # CRUD /users（superadmin / company_admin）
│   │   │   └── internal_setup.py # POST /internal/init-superadmin
│   │   └── internal/           # Cloud Tasks worker 路由（X-Internal-Token 驗證）
│   │       └── tasks.py        # process-document / ingest-chunks / inject-gcs-paths
│   │
│   ├── services/               # 業務邏輯層
│   │   ├── auth.py             # 密碼雜湊（bcrypt）、JWT 生成與驗證
│   │   ├── rules.py            # 公司規則 CRUD 與版本管理
│   │   ├── ai/
│   │   │   ├── gemini.py       # Gemini Flash：PDF 視覺解析 / DOCX 結構提取
│   │   │   ├── embedding.py    # Vertex AI Embedding API 呼叫（gemini-embedding-001）
│   │   │   └── qdrant_service.py # Qdrant collection 初始化、向量 upsert / 查詢
│   │   ├── document/
│   │   │   ├── detector.py     # 文件類型偵測（python-magic）
│   │   │   ├── parser.py       # DOCX 文字提取（python-docx）
│   │   │   └── ocr.py          # 掃描 PDF 前處理
│   │   └── storage/
│   │       ├── gcs.py          # GCS 上傳 / 下載 / 簽署 URL
│   │       └── tasks.py        # Cloud Tasks 任務派送
│   │
│   └── prompts/
│       └── query_prompt.py     # RAG system prompt + build_rag_prompt()
│
├── migrations/                 # Alembic 資料庫遷移腳本
│   ├── env.py                  # Alembic 執行環境（從 settings 取 DATABASE_URL）
│   └── versions/
│       ├── 001_initial_schema.py       # 初始建表（users, companies, sessions, documents）
│       ├── 002_phase2_multitenant.py   # 多租戶（company_rules, products）
│       ├── 003_phase4_vector.py        # 向量化支援（chunks 欄位擴充）
│       ├── 004_phase4_indexes.py       # 效能索引
│       └── 005_phase5_add_chunk_index.py # chunk 排序索引
│
├── tests/                      # 單元測試
│   ├── test_gemini_parser.py   # Gemini 解析邏輯測試
│   ├── test_detector.py        # 文件類型偵測測試
│   └── test_rule_version.py    # 規則版本邏輯測試
│
├── web/                        # Angular 前端
│   ├── Dockerfile              # 多階段 build（node 建置 + nginx 服務）
│   ├── nginx.conf              # nginx SPA fallback + 靜態快取設定
│   ├── angular.json            # Angular CLI 設定（build / serve / test）
│   ├── package.json            # Node.js 依賴
│   ├── tsconfig.json           # TypeScript 設定
│   └── src/
│       ├── environments/
│       │   ├── environment.ts          # 本機：apiUrl = http://localhost:8000
│       │   └── environment.prod.ts     # 正式：apiUrl = Cloud Run 後端 URL
│       └── app/
│           ├── core/
│           │   ├── services/           # API 呼叫服務（auth, upload, query...）
│           │   └── interceptors/       # auth.interceptor.ts（自動附加 Bearer token）
│           └── features/              # 功能頁面（login, hub, upload, query...）
│
├── dev_trigger.py              # 本機手動觸發 Cloud Tasks worker 的開發工具
└── setup_gcs_lifecycle.py      # GCS lifecycle rule 設定腳本（15 天自動刪除 processed/）
```

---

## GCP 專案說明

| 項目 | 值 |
|------|-----|
| **GCP 專案 ID** | `shaped-totem-468106-g3` |
| **專案號碼** | `550905952099` |
| **部署區域** | `asia-east1`（台灣） |
| **Cloud SQL 實例** | `shaped-totem-468106-g3:asia-east1:first-postgre-sql` |
| **GCS Bucket** | `onceagain-rag-docs` |
| **Cloud Tasks Queue** | `onceagain-rag-ingestion` |
| **Qdrant 主機** | `34.81.227.217:6333`（GCE VM） |
| **Artifact Registry** | `asia-east1-docker.pkg.dev/shaped-totem-468106-g3/public-rag/` |
| **後端 Cloud Run 服務** | `public-rag-backend` |
| **前端 Cloud Run 服務** | `public-rag-frontend` |

### 使用的 GCP 服務

- **Cloud Run** — 無伺服器容器部署（前端 + 後端）
- **Cloud SQL (PostgreSQL 15)** — 關聯式資料庫
- **Cloud Storage** — 文件儲存（raw / processed / converted 前綴）
- **Cloud Tasks** — 非同步文件處理任務佇列
- **Vertex AI** — Gemini Flash 文件解析 + gemini-embedding-001 向量化
- **Artifact Registry** — Docker image 儲存庫

---

## 本機開發環境建立

### 前置需求

| 工具 | 版本需求 | 說明 |
|------|----------|------|
| Docker Desktop | 4.x+ | 容器化執行環境 |
| Docker Compose | v2.x+ | 多容器編排（通常隨 Docker Desktop 安裝） |
| Google Cloud SDK | 最新版 | GCP 服務存取工具 |
| Python | 3.12+ | 本機執行 migration 用 |

---

### 1. 安裝 Google Cloud SDK

```bash
# macOS（Homebrew）
brew install --cask google-cloud-sdk

# 或官方安裝腳本
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

安裝後確認版本：

```bash
gcloud --version
```

---

### 2. 安裝 GCP 必要組件

```bash
# 更新 gcloud 並安裝 Cloud SQL Proxy 與相關組件
gcloud components update
gcloud components install beta
gcloud components install cloud-sql-proxy
```

---

### 3. 本機 GCP 認證

本機開發時，後端 Docker container 需要存取 GCS、Cloud Tasks、Vertex AI，透過 Application Default Credentials (ADC) 認證：

```bash
# 登入 GCP 帳號
gcloud auth login

# 設定預設專案
gcloud config set project shaped-totem-468106-g3

# 產生 Application Default Credentials（本機開發用）
gcloud auth application-default login
```

執行成功後，credentials 檔案會存在：

```
~/.config/gcloud/application_default_credentials.json
```

`docker-compose.yaml` 會自動將此檔案掛載進容器，不需要額外設定。

---

### 4. 設定環境變數

在專案根目錄建立 `.env` 檔案（**不要 commit 進 git**）：

```bash
cp .env.example .env   # 如果沒有 example，手動建立
```

`.env` 內容範本：

```dotenv
# ── App ──────────────────────────────────────────────
app_env=development

# ── JWT（openssl rand -hex 32 產生）─────────────────
JWT_SECRET_KEY=your-jwt-secret-key-at-least-32-chars
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=24

# ── Internal Token（Cloud Tasks worker 驗證用）───────
INTERNAL_TOKEN=your-internal-token

# ── Database（本機 PostgreSQL）───────────────────────
# 本機直連（如果有本機 PostgreSQL）
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/rag_db

# ── GCS ──────────────────────────────────────────────
GCS_BUCKET_NAME=onceagain-rag-docs
GCS_PROJECT=shaped-totem-468106-g3

# ── Cloud Tasks ──────────────────────────────────────
CLOUD_TASKS_PROJECT=shaped-totem-468106-g3
CLOUD_TASKS_LOCATION=asia-east1
CLOUD_TASKS_QUEUE=onceagain-rag-ingestion
CLOUD_TASKS_MAX_RETRIES=3
WORKER_BASE_URL=http://localhost:8000

# ── Vertex AI / Gemini ───────────────────────────────
VERTEX_AI_PROJECT=shaped-totem-468106-g3
VERTEX_AI_LOCATION=us-central1
GEMINI_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001

# ── Qdrant ───────────────────────────────────────────
QDRANT_HOST=34.81.227.217
QDRANT_PORT=6333
QDRANT_API_KEY=
QDRANT_COLLECTION_NAME=public_rag_chunks

# ── CORS ─────────────────────────────────────────────
CORS_ORIGINS=*
```

> **重要：** `JWT_SECRET_KEY` 和 `INTERNAL_TOKEN` 必須自行產生，勿使用預設值。
> ```bash
> openssl rand -hex 32   # 產生隨機 secret key
> ```

---

### 5. 啟動本機環境

```bash
# 確認 Docker Desktop 正在執行
docker compose up --build
```

首次啟動會 build image，約需 2-3 分鐘。

| 服務 | 本機網址 |
|------|----------|
| 後端 API | http://localhost:8000 |
| 後端 API 文件（Swagger） | http://localhost:8000/docs |
| 前端介面 | http://localhost:4200 |

---

### 6. 資料庫遷移

首次啟動或有新 migration 時，需要執行 Alembic 遷移。

**方法一：在 container 內執行（推薦）**

```bash
# 進入後端 container
docker compose exec api_center bash

# 執行所有待處理 migration
alembic upgrade head
```

**方法二：本機直接執行**

```bash
# 安裝 Python 依賴
pip install -r requirements.txt

# 設定環境變數後執行
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/rag_db \
alembic upgrade head
```

---

### 7. 初始化 Superadmin 帳號

資料庫遷移完成後，呼叫內部 API 建立第一個 superadmin：

```bash
curl -X POST http://localhost:8000/internal/init-superadmin \
  -H "X-Internal-Token: your-internal-token" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "your-password",
    "display_name": "Super Admin"
  }'
```

---

### 8. 健康檢查

```bash
# 後端健康檢查
curl http://localhost:8000/health

# GCS + Vertex AI 連線檢查
curl http://localhost:8000/ready
```

---

## 環境變數說明

| 變數名稱 | 說明 | 預設值 | 必填（Production） |
|----------|------|--------|--------------------|
| `app_env` | 執行環境（development / production） | `development` | 是 |
| `JWT_SECRET_KEY` | JWT 簽名金鑰（至少 32 字元） | 無 | 是 |
| `JWT_ALGORITHM` | JWT 演算法 | `HS256` | 否 |
| `JWT_EXPIRE_HOURS` | JWT 有效期（小時） | `24` | 否 |
| `INTERNAL_TOKEN` | Cloud Tasks worker 驗證 token | 無 | 是 |
| `DATABASE_URL` | PostgreSQL 連線字串（asyncpg 格式） | localhost | 是 |
| `DB_POOL_SIZE_MIN` | 連線池最小連線數 | `5` | 否 |
| `DB_POOL_SIZE_MAX` | 連線池最大連線數 | `20` | 否 |
| `GCS_BUCKET_NAME` | GCS bucket 名稱 | `your-rag-bucket` | 是 |
| `GCS_PROJECT` | GCP 專案 ID | 空 | 是 |
| `CLOUD_TASKS_PROJECT` | Cloud Tasks GCP 專案 ID | 空 | 是 |
| `CLOUD_TASKS_LOCATION` | Cloud Tasks 區域 | `asia-east1` | 否 |
| `CLOUD_TASKS_QUEUE` | Cloud Tasks 佇列名稱 | `onceagain-rag-ingestion` | 否 |
| `WORKER_BASE_URL` | worker 端點 base URL | `http://localhost:8000` | 是 |
| `VERTEX_AI_PROJECT` | Vertex AI GCP 專案 ID | 空 | 是 |
| `VERTEX_AI_LOCATION` | Vertex AI 區域 | `us-central1` | 否 |
| `GEMINI_MODEL` | Gemini 模型名稱 | `gemini-2.5-flash` | 否 |
| `GEMINI_EMBEDDING_MODEL` | Embedding 模型名稱 | `gemini-embedding-001` | 否 |
| `QDRANT_HOST` | Qdrant 主機 IP | 空 | 是 |
| `QDRANT_PORT` | Qdrant 連接埠 | `6333` | 否 |
| `QDRANT_API_KEY` | Qdrant API Key（無則留空） | 空 | 否 |
| `QDRANT_COLLECTION_NAME` | Qdrant collection 名稱 | 空 | 是 |
| `CORS_ORIGINS` | 允許的前端 origin（逗號分隔） | `*` | 建議設定 |

---

## API 端點總覽

### 公開端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/health` | 後端 + 資料庫健康檢查 |
| `GET` | `/ready` | GCS + Vertex AI 連線檢查 |
| `POST` | `/auth/login` | 登入，回傳 JWT token |

### 需要驗證的端點

| 方法 | 路徑 | 說明 | 角色 |
|------|------|------|------|
| `POST` | `/upload` | 上傳文件 | superadmin, company_admin |
| `GET` | `/sessions` | 列出上傳批次 | superadmin, company_admin |
| `GET` | `/sessions/{id}` | 查詢批次狀態 | 已登入 |
| `POST` | `/sessions/{id}/confirm` | 確認批次（進入處理） | superadmin, company_admin |
| `POST` | `/query` | RAG 自然語言查詢 | 已登入 |
| `GET` | `/companies/{id}/rules` | 取最新解析規則 | superadmin, company_admin |
| `POST` | `/companies/{id}/rules` | 建立新規則版本 | superadmin, company_admin |
| `GET` | `/dashboard/stats` | 儀表板統計 | 已登入 |

### 管理員端點（superadmin）

| 方法 | 路徑 | 說明 |
|------|------|------|
| `POST` | `/companies` | 建立公司 |
| `GET` | `/companies` | 列出所有公司 |
| `POST` | `/users` | 建立使用者 |
| `GET` | `/users` | 列出使用者 |

### Internal 端點（Cloud Tasks 呼叫）

需帶 `X-Internal-Token` header。

| 方法 | 路徑 | 說明 |
|------|------|------|
| `POST` | `/internal/init-superadmin` | 初始化 superadmin |
| `POST` | `/internal/tasks/process-document` | 文件解析 worker |
| `POST` | `/internal/tasks/ingest-chunks` | 向量化 worker |
| `POST` | `/internal/tasks/inject-gcs-paths` | GCS 路徑注入 |

---

## 多租戶與角色設計

### 角色說明

| 角色 | 說明 | 可見資料範圍 |
|------|------|-------------|
| `superadmin` | 系統管理員 | 所有公司的所有資料 |
| `company_admin` | 公司管理員 | 自己公司的資料 |
| `field_user` | 現場操作員 | 自己公司的資料（唯讀查詢） |

### Session 狀態機

```
pending_preview  →  confirmed  →  processing  →  done
                                      ↓
                                   failed
```

- `pending_preview`：文件上傳完成，等待管理員確認
- `confirmed`：管理員確認，進入 Cloud Tasks 處理佇列
- `processing`：Gemini 解析 + 向量化進行中
- `done`：全部完成，可查詢

---

## GCP 雲端部署

### 後端部署

```bash
# 進入專案根目錄

# 1. 設定 GCP 專案
gcloud config set project shaped-totem-468106-g3

# 2. Build & Push Docker image
gcloud builds submit --tag asia-east1-docker.pkg.dev/shaped-totem-468106-g3/public-rag/backend

# 3. 部署到 Cloud Run
gcloud run deploy public-rag-backend \
  --image asia-east1-docker.pkg.dev/shaped-totem-468106-g3/public-rag/backend \
  --region asia-east1 \
  --platform managed \
  --add-cloudsql-instances shaped-totem-468106-g3:asia-east1:first-postgre-sql \
  --set-env-vars app_env=production,...
```

### 前端部署

```bash
# 進入 web/ 目錄
cd web

# Build & Push
gcloud builds submit --tag asia-east1-docker.pkg.dev/shaped-totem-468106-g3/public-rag/frontend

# 部署
gcloud run deploy public-rag-frontend \
  --image asia-east1-docker.pkg.dev/shaped-totem-468106-g3/public-rag/frontend \
  --region asia-east1 \
  --platform managed \
  --allow-unauthenticated
```

### Cloud Run 後端必要環境變數

| 變數 | 說明 |
|------|------|
| `app_env` | `production` |
| `JWT_SECRET_KEY` | 正式 JWT secret |
| `INTERNAL_TOKEN` | worker 驗證 token |
| `DATABASE_URL` | Cloud SQL socket 格式：`postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/專案:區域:實例` |
| `GCS_PROJECT` | `shaped-totem-468106-g3` |
| `GCS_BUCKET_NAME` | `onceagain-rag-docs` |
| `CLOUD_TASKS_PROJECT` | `shaped-totem-468106-g3` |
| `WORKER_BASE_URL` | 後端 Cloud Run URL |
| `VERTEX_AI_PROJECT` | `shaped-totem-468106-g3` |
| `QDRANT_HOST` | `34.81.227.217` |
| `QDRANT_COLLECTION_NAME` | `public_rag_chunks` |
| `CORS_ORIGINS` | 前端 Cloud Run URL（例：`https://public-rag-frontend-550905952099.asia-east1.run.app`） |

> **注意：** `CORS_ORIGINS` 為逗號分隔字串，可填多個 origin。

---

## 常見問題

### Q: 本機啟動後 GCS 或 Vertex AI 無法連線

確認 ADC credentials 已正確產生且掛載：

```bash
# 確認 credentials 檔案存在
ls ~/.config/gcloud/application_default_credentials.json

# 重新產生
gcloud auth application-default login
```

### Q: Cloud Run 部署後 CORS 錯誤（OPTIONS 405）

確認後端 Cloud Run 服務的 `CORS_ORIGINS` 環境變數已設定為前端 URL：

```
CORS_ORIGINS = https://your-frontend-url.a.run.app
```

### Q: 資料庫連線失敗

本機開發確認 PostgreSQL 已啟動。Cloud Run 環境確認 `DATABASE_URL` 使用 Cloud SQL socket 格式，且服務帳號有 `Cloud SQL Client` 角色。

### Q: Qdrant 初始化失敗（本機開發）

本機若無 Qdrant 服務，會在 startup 印出警告但不影響其他功能。若需完整功能，可用 Docker 啟動 Qdrant：

```bash
docker run -p 6333:6333 qdrant/qdrant
```

並將 `.env` 中 `QDRANT_HOST=localhost` 設定。
